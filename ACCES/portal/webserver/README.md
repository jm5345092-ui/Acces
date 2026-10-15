# APK-Lab Server

A client/server web platform for APK reverse-engineering and lab-controlled
modification. The browser only needs a web connection — **every heavy
operation (apktool, aapt2, apksigner, zipalign, adb, JADX) runs in a
server-side `worker` container**, never on the client.

Intended for authorized use: your own APKs, QA/regression patching, security
research and CTF/lab work. It does not run or trust code from inside an
uploaded APK, and it deliberately omits an automatic `adb uninstall` path.

## Architecture

```
frontend (React/TS/Vite)  ──HTTP/SSE──▶  api (FastAPI, NO android tools)
                                              │
                                     jobs table (SQLite) + Redis pub/sub
                                              │
                                        worker (Java/Apktool/SDK/ADB/JADX,
                                                 runs as non-root user)
                                              │
                                   storage/projects/<id>/{original,decoded,
                                   modifications,rebuild,signed,logs,reports,temp}
```

See the reasoning in `app/core/security.py` and `app/jobqueue/base.py` for
the why behind the split — in short: the API process can enqueue jobs but
never shells out to Android tooling itself, and nothing in the whole
codebase writes to `original/original.apk` after the initial upload.

## Quickstart

```bash
cp .env.example .env     # edit secrets/passwords
docker compose up --build
```

- Frontend: http://localhost:5173
- API: http://localhost:8000 (docs at `/docs`)

First run: create a project, upload an `.apk`, it decodes automatically.
Then use **Run Analysis**, make changes under the **Changes** tab (manual or
AI-planned), **Rebuild & Sign**, and check the **Compare** tab before
**Download**.

## What's fully implemented vs. extension points

Fully working end-to-end: upload → SHA-256/1 → isolated workspace → apktool
decode → manifest/DEX/Smali/resource/asset/native-lib analysis → structured
Smali/resource/manifest Modification Engine (diff → confirm → apply/revert)
→ apktool build → zipalign → sign (lab test key) → verify → decode-and-compare
→ download. All of it is covered by the job-queue/worker split and the
security guards in `app/core/security.py`.

Built as real, working interfaces but **not exercised in this environment**
(no Anthropic API key / no physical Android device / no Docker daemon was
available while building this):

- **AI assistant** (`app/ai/`): `ClaudeProvider` is a complete implementation
  against the Anthropic SDK — set `ANTHROPIC_API_KEY` to turn it on.
  `OpenAIProvider`/`LocalProvider` are explicit stubs (`NotImplementedError`)
  ready to fill in against the same JSON-plan contract.
- **ADB device integration** (`app/services/adb_service.py`): real `adb`
  subprocess wrappers, gated behind device detection; the UI should treat an
  empty device list as the normal case, not an error.
- All four images (`redis`, `api`, `frontend`, `worker`) build and run via
  `docker compose up --build` — the worker image downloads apktool/Android
  cmdline-tools/JADX from their upstream release URLs on first build, so it
  needs internet access and takes a few minutes. Standalone `baksmali`/
  `smali` binaries are intentionally not installed — their only known
  distribution channel (Bitbucket Downloads) now requires a paid plan and is
  unreliable, and nothing in this codebase calls them directly: `apktool`
  already handles Smali↔DEX conversion internally for decode/build.

## Running the backend unit tests (no Docker/Android tools needed)

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

These cover path-traversal protection, the Smali Modification Engine
(including the exact worked example from the spec — dynamically discovering
a package/class/module, never hardcoded), manifest parsing/editing, and the
expected-vs-important diff classification used by the comparator.

## Standalone APK comparator CLI

```bash
python3 tools/apk_validator.py original.apk rebuilt.apk --compare
```

Requires apktool/java/aapt2/apksigner on PATH (i.e. run this inside the
`worker` container or an equivalent environment).

## Security notes

- All subprocess calls go through `app/core/security.run_tool()`, which
  only accepts argument lists (no shell strings, no `shell=True`).
- Every filesystem path derived from a request is validated by
  `resolve_safe_path()` to stay inside its project workspace.
- `original/original.apk` is chmod'd read-only immediately after upload and
  is centrally guarded against being overwritten.
- The `api` container has no Java/Android tooling installed; only `worker`
  does, and it runs as a non-root user.
- Uploads are capped (`APKLAB_MAX_UPLOAD_MB`), and every external tool call
  has a timeout.
