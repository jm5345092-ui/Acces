"""Security primitives used by every service that touches the filesystem or
spawns a subprocess on behalf of an uploaded (untrusted) APK.

Rules enforced here, and only here, so every call site gets them for free:
  1. No path derived from user/request input may resolve outside its project
     workspace ("path traversal" protection).
  2. All external tools are invoked via argument lists, never shell strings.
  3. Every subprocess has a hard timeout.
  4. The pristine original APK can never be opened for writing.
"""
from __future__ import annotations

import re
import select
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

DEFAULT_TIMEOUT_SECONDS = 300

_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
_SAFE_JAVA_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SAFE_PACKAGE_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$")


class PathTraversalError(Exception):
    """Raised whenever a request-derived path would escape its workspace."""


class ReadOnlyViolationError(Exception):
    """Raised on any attempt to write to the immutable original APK."""


class InvalidIdentifierError(Exception):
    """Raised when a package/class/file name fails validation."""


def new_project_id() -> str:
    """Project IDs are server-generated UUIDs; the client's filename never
    becomes part of any filesystem path."""
    return uuid.uuid4().hex


def safe_filename(original_name: str) -> str:
    """Strip an uploaded filename down to a safe basename-only token, purely
    for display/metadata — it is NEVER used to build a storage path."""
    base = Path(original_name).name
    base = re.sub(r"[^A-Za-z0-9_.\-]", "_", base)
    return base[:255] or "upload.apk"


def resolve_safe_path(root: Path, *parts: str) -> Path:
    """Join `parts` onto `root` and guarantee the result is still inside
    `root`. Raises PathTraversalError otherwise. This is the single gate
    every file-open/write in the services layer must pass through for any
    path component that came from a request."""
    root_resolved = root.resolve()
    candidate = root_resolved
    for part in parts:
        if part in ("", ".", None):
            continue
        # Reject absolute paths and drive letters outright — a part must be
        # a relative segment, never an escape hatch.
        if Path(part).is_absolute() or ".." in Path(part).parts:
            raise PathTraversalError(f"Unsafe path segment: {part!r}")
        candidate = candidate / part

    resolved = candidate.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        raise PathTraversalError(
            f"Resolved path {resolved} escapes workspace root {root_resolved}"
        )
    return resolved


def assert_not_original(path: Path, original_path: Path) -> None:
    if path.resolve() == original_path.resolve():
        raise ReadOnlyViolationError("The original APK must never be modified or overwritten.")


def validate_package_name(package: str) -> str:
    if not package or not _SAFE_PACKAGE_RE.match(package) or len(package) > 255:
        raise InvalidIdentifierError(f"Invalid Java package name: {package!r}")
    return package


def validate_class_name(name: str) -> str:
    if not name or not _SAFE_JAVA_IDENT_RE.match(name) or len(name) > 255:
        raise InvalidIdentifierError(f"Invalid Java class name: {name!r}")
    return name


def validate_simple_name(name: str) -> str:
    """For method names, file basenames, etc. — conservative allowlist."""
    if not name or not _SAFE_NAME_RE.match(name) or len(name) > 255:
        raise InvalidIdentifierError(f"Invalid identifier: {name!r}")
    return name


@dataclass
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str


def run_tool(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    env: dict[str, str] | None = None,
) -> ProcessResult:
    """The ONLY sanctioned way to invoke an external binary (apktool, aapt2,
    apksigner, zipalign, adb, jadx, keytool, ...).

    `args` MUST already be a list (never a pre-joined string) — this
    function refuses anything else, which also forbids shell=True by
    construction.
    """
    if isinstance(args, str):
        raise TypeError("run_tool() requires a list of arguments, never a shell string")
    args = list(args)
    if not args:
        raise ValueError("run_tool() requires at least one argument (the executable)")

    try:
        completed = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"Tool timed out after {timeout}s: {' '.join(args)}") from exc

    return ProcessResult(completed.returncode, completed.stdout, completed.stderr)


def run_tool_streaming(
    args: Sequence[str],
    on_line: Callable[[str], None],
    *,
    cwd: Path | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    env: dict[str, str] | None = None,
) -> ProcessResult:
    """Same contract and safety properties as `run_tool()` (argument-list
    only, no shell, hard timeout) but calls `on_line(line)` as each line of
    output arrives, for tools that run long enough to need live progress
    (apktool decode/build). Only ever runs inside the Linux `worker`
    container — relies on `select` against a pipe, which Windows doesn't
    support for non-socket file objects.
    """
    if isinstance(args, str):
        raise TypeError("run_tool_streaming() requires a list of arguments, never a shell string")
    args = list(args)
    if not args:
        raise ValueError("run_tool_streaming() requires at least one argument (the executable)")

    process = subprocess.Popen(
        args,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        shell=False,
        env=env,
    )
    collected: list[str] = []
    deadline = time.monotonic() + timeout
    try:
        assert process.stdout is not None
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.wait()
                raise TimeoutError(f"Tool timed out after {timeout}s: {' '.join(args)}")
            ready, _, _ = select.select([process.stdout], [], [], min(remaining, 1.0))
            if ready:
                line = process.stdout.readline()
                if line == "":
                    break  # EOF — process finished producing output
                collected.append(line)
                on_line(line.rstrip("\n"))
            elif process.poll() is not None:
                break
        process.wait(timeout=max(deadline - time.monotonic(), 0) + 5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()

    returncode = process.returncode if process.returncode is not None else -1
    return ProcessResult(returncode, "".join(collected), "")
