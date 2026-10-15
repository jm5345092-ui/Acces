import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { TreeNode } from "../types";
import { api } from "../services/api";

function SearchIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="11" cy="11" r="7" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function FolderPlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M4 5a1 1 0 0 1 1-1h4l2 2h8a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5z" />
      <line x1="12" y1="12" x2="12" y2="16" />
      <line x1="10" y1="14" x2="14" y2="14" />
    </svg>
  );
}

function FolderUploadIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M4 5a1 1 0 0 1 1-1h4l2 2h8a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5z" />
      <line x1="12" y1="16" x2="12" y2="10" />
      <polyline points="9.5 12.5 12 10 14.5 12.5" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  );
}

function ScissorsIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="6" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <line x1="20" y1="4" x2="8.12" y2="15.88" />
      <line x1="14.47" y1="14.48" x2="20" y2="20" />
      <line x1="8.12" y1="8.12" x2="12" y2="12" />
    </svg>
  );
}

function CopyIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="9" y="9" width="12" height="12" rx="1.5" />
      <path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1" />
    </svg>
  );
}

function PasteIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="6" y="4" width="12" height="17" rx="1.5" />
      <rect x="9" y="2" width="6" height="4" rx="1" />
    </svg>
  );
}

function RenameIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  );
}

interface Props {
  projectId: string;
  onSelect: (path: string) => void;
  selectedPath: string | null;
  projectStatus?: string;
  /** Called after an upload/folder-creation is applied to disk, so the
   * parent can refresh anything else that depends on project state
   * (the "revert last change" button, the assistant badge, etc.). */
  onContentChanged?: () => void;
}

const WAITING_STATUSES = new Set(["CREATED", "UPLOADED", "DECODING"]);
const MAX_FILE_BYTES = 8 * 1024 * 1024; // 8MB per file — keeps JSON POST bodies and the SQLite row sane
const SAFE_NAME_RE = /^[A-Za-z0-9_.-]+$/;

function joinPath(base: string, rel: string): string {
  if (!base || base === ".") return rel;
  return `${base}/${rel}`;
}

function displayDir(path: string): string {
  return !path || path === "." ? "/ (raíz)" : `/${path}`;
}

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string; // "data:<mime>;base64,<data>"
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

export default function FileExplorer({ projectId, onSelect, selectedPath, projectStatus, onContentChanged }: Props) {
  const [tree, setTree] = useState<TreeNode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [selectedDir, setSelectedDir] = useState<string>(".");
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    path: string;
    name: string;
    type: "file" | "directory";
  } | null>(null);
  const [clipboard, setClipboard] = useState<{ path: string; name: string; mode: "cut" | "copy" } | null>(null);

  const loadTree = () => api.getTree(projectId).then(setTree).catch((e) => setError(String(e)));

  useEffect(() => {
    loadTree();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const uploadFolder = async (fileList: FileList) => {
    const files = Array.from(fileList);
    if (files.length === 0) return;

    let applied = 0;
    let skipped = 0;
    let failed = 0;

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      // webkitRelativePath preserves the picked folder's internal structure
      // (e.g. "icons/sub/a.png"); falls back to the bare filename only if
      // the browser didn't report it (plain multi-file picks).
      const relPath = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
      const targetPath = joinPath(selectedDir, relPath);
      setUploadStatus(`Subiendo ${i + 1}/${files.length}: ${targetPath}`);

      if (file.size > MAX_FILE_BYTES) {
        skipped++;
        continue;
      }
      try {
        const content = await readFileAsBase64(file);
        // Applied immediately (not left PENDING): this is always a brand
        // new file (add_resource refuses to overwrite an existing one), so
        // there's nothing destructive to review — the point of uploading a
        // folder is to see it in the tree right away and keep building on
        // it, not to hunt for N pending rows in the Cambios tab first.
        const mod = await api.proposeModification(projectId, {
          operation: "add_resource",
          path: targetPath,
          content,
          is_binary: true,
        });
        await api.applyModification(projectId, mod.id);
        applied++;
      } catch {
        failed++;
      }
    }

    setUploadStatus(
      `Listo: ${applied} archivo(s) agregados en "${displayDir(selectedDir)}"` +
        (skipped ? `, ${skipped} omitido(s) por tamaño (> 8MB)` : "") +
        (failed ? `, ${failed} con error (¿ya existían?)` : "")
    );
    loadTree();
    onContentChanged?.();
  };

  const createFolder = async () => {
    const name = window.prompt(`Nombre de la nueva carpeta dentro de "${displayDir(selectedDir)}":`);
    if (!name) return;
    if (!SAFE_NAME_RE.test(name)) {
      setUploadStatus('Nombre inválido — usa solo letras, números, "-", "_" o ".".');
      return;
    }
    const markerPath = joinPath(selectedDir, `${name}/.folder`);
    try {
      const mod = await api.proposeModification(projectId, {
        operation: "add_resource",
        path: markerPath,
        content: "",
        is_binary: false,
      });
      await api.applyModification(projectId, mod.id);
      setUploadStatus(`Carpeta "${name}" creada en "${displayDir(selectedDir)}".`);
      setSelectedDir(joinPath(selectedDir, name));
      loadTree();
      onContentChanged?.();
    } catch (e) {
      setUploadStatus(`No se pudo crear la carpeta: ${String(e)}`);
    }
  };

  const deleteItem = async (path: string, name: string, type: "file" | "directory") => {
    setContextMenu(null);
    const what = type === "directory" ? `la carpeta "${name}" y todo su contenido` : `el archivo "${name}"`;
    if (!window.confirm(`¿Eliminar ${what}? Esta acción no se puede deshacer.`)) return;
    try {
      await api.deleteTreeEntry(projectId, path);
      setUploadStatus(`"${name}" eliminado.`);
      if (selectedDir === path || selectedDir.startsWith(`${path}/`)) setSelectedDir(".");
      loadTree();
      onContentChanged?.();
    } catch (e) {
      setUploadStatus(`No se pudo eliminar: ${String(e)}`);
    }
  };

  const renameItem = async (path: string, name: string) => {
    setContextMenu(null);
    const newName = window.prompt("Nuevo nombre:", name);
    if (!newName || newName === name) return;
    if (!SAFE_NAME_RE.test(newName)) {
      setUploadStatus('Nombre inválido — usa solo letras, números, "-", "_" o ".".');
      return;
    }
    try {
      await api.renameTreeEntry(projectId, path, newName);
      setUploadStatus(`Renombrado a "${newName}".`);
      loadTree();
      onContentChanged?.();
    } catch (e) {
      setUploadStatus(`No se pudo renombrar: ${String(e)}`);
    }
  };

  const cutItem = (path: string, name: string) => {
    setClipboard({ path, name, mode: "cut" });
    setContextMenu(null);
    setUploadStatus(`"${name}" listo para mover — ve a la carpeta destino y elige "Pegar aquí".`);
  };

  const copyItem = (path: string, name: string) => {
    setClipboard({ path, name, mode: "copy" });
    setContextMenu(null);
    setUploadStatus(`"${name}" copiado — ve a la carpeta destino y elige "Pegar aquí".`);
  };

  const pasteInto = async (destDir: string) => {
    if (!clipboard) return;
    setContextMenu(null);
    try {
      if (clipboard.mode === "cut") {
        await api.moveTreeEntry(projectId, clipboard.path, destDir);
        setUploadStatus(`"${clipboard.name}" movido a "${displayDir(destDir)}".`);
      } else {
        await api.copyTreeEntry(projectId, clipboard.path, destDir);
        setUploadStatus(`"${clipboard.name}" copiado a "${displayDir(destDir)}".`);
      }
      setClipboard(null);
      loadTree();
      onContentChanged?.();
    } catch (e) {
      setUploadStatus(`No se pudo pegar: ${String(e)}`);
    }
  };

  if (error) return <div style={{ padding: 8, color: "var(--danger)" }}>{error}</div>;
  if (!tree) return <div style={{ padding: 8, color: "var(--text-dim)", fontSize: 12 }}>Cargando...</div>;

  const isEmpty = !tree.children || tree.children.length === 0;
  const waiting = isEmpty && projectStatus && WAITING_STATUSES.has(projectStatus);

  return (
    <div style={{ height: "100%", overflow: "auto", fontSize: 13, display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", gap: 4, padding: 4, alignItems: "center" }}>
        <div style={{ position: "relative", flex: 1, minWidth: 0 }}>
          <span
            style={{
              position: "absolute",
              left: 7,
              top: "50%",
              transform: "translateY(-50%)",
              color: "var(--text-dim)",
              pointerEvents: "none",
              display: "flex",
            }}
          >
            <SearchIcon />
          </span>
          <input
            placeholder="Buscar archivo..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ width: "100%", paddingLeft: 26 }}
          />
        </div>
        <button
          title="Crear carpeta nueva dentro de la carpeta seleccionada"
          onClick={createFolder}
          style={{ padding: "4px 7px", display: "flex", alignItems: "center" }}
        >
          <FolderPlusIcon />
        </button>
        <button
          title="Subir una carpeta local completa dentro de la carpeta seleccionada — se agrega de inmediato, lista para seguir trabajando en ella"
          onClick={() => document.getElementById(`folder-upload-input-${projectId}`)?.click()}
          style={{ padding: "4px 7px", display: "flex", alignItems: "center" }}
        >
          <FolderUploadIcon />
        </button>
        {clipboard && (
          <button
            title={`Pegar "${clipboard.name}" en "${displayDir(selectedDir)}"`}
            onClick={() => pasteInto(selectedDir)}
            style={{ padding: "4px 7px", display: "flex", alignItems: "center", color: "var(--accent)" }}
          >
            <PasteIcon />
          </button>
        )}
        <input
          id={`folder-upload-input-${projectId}`}
          key={projectId}
          type="file"
          multiple
          style={{ display: "none" }}
          onChange={(e) => {
            if (e.target.files) uploadFolder(e.target.files);
            e.target.value = "";
          }}
          ref={(el) => {
            // webkitdirectory/directory aren't in React's typed HTML input
            // attributes, and setting them in a separate useEffect proved
            // unreliable (the input can remount — e.g. when the parent key
            // changes — before the effect re-runs, briefly leaving a plain
            // file picker instead of a folder picker). Setting them here,
            // directly in the ref callback, applies the instant this exact
            // DOM node is created, every time, with no timing gap.
            if (el) {
              el.setAttribute("webkitdirectory", "");
              el.setAttribute("directory", "");
            }
          }}
        />
      </div>

      <div
        className="monospace"
        style={{ padding: "2px 8px 6px", fontSize: 11, color: "var(--text-dim)" }}
        title="Las carpetas nuevas y los archivos subidos van aquí dentro. Haz clic en una carpeta del árbol para cambiarla."
      >
        Carpeta destino: <span style={{ color: "var(--accent)" }}>{displayDir(selectedDir)}</span>
      </div>

      {uploadStatus && (
        <div style={{ padding: "4px 8px", fontSize: 11, color: "var(--text-dim)", borderBottom: "1px solid var(--border)" }}>
          {uploadStatus}
        </div>
      )}

      {waiting ? (
        <div style={{ padding: 12, fontSize: 12, color: "var(--text-dim)" }}>
          {projectStatus === "DECODING"
            ? "Decodificando el APK... los archivos aparecerán aquí en cuanto termine."
            : "Todavía no se decodificó el APK. Esto empieza automáticamente justo después de subirlo."}
        </div>
      ) : (
        <TreeView
          node={tree}
          depth={0}
          onSelect={onSelect}
          selectedPath={selectedPath}
          selectedDir={selectedDir}
          onSelectDir={setSelectedDir}
          filter={filter}
          onContextMenuItem={(x, y, path, name, type) => setContextMenu({ x, y, path, name, type })}
        />
      )}

      {contextMenu && (
        <>
          <div
            onClick={() => setContextMenu(null)}
            onContextMenu={(e) => {
              e.preventDefault();
              setContextMenu(null);
            }}
            style={{ position: "fixed", inset: 0, zIndex: 99 }}
          />
          <div
            style={{
              position: "fixed",
              left: contextMenu.x,
              top: contextMenu.y,
              zIndex: 100,
              background: "var(--bg-2)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)",
              boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
              minWidth: 180,
              fontSize: 12,
              overflow: "hidden",
            }}
          >
            <MenuItem icon={<ScissorsIcon />} label="Cortar" onClick={() => cutItem(contextMenu.path, contextMenu.name)} />
            <MenuItem icon={<CopyIcon />} label="Copiar" onClick={() => copyItem(contextMenu.path, contextMenu.name)} />
            {contextMenu.type === "directory" && clipboard && (
              <MenuItem icon={<PasteIcon />} label="Pegar aquí" onClick={() => pasteInto(contextMenu.path)} accent />
            )}
            <MenuItem
              icon={<RenameIcon />}
              label="Renombrar"
              onClick={() => renameItem(contextMenu.path, contextMenu.name)}
            />
            <MenuItem
              icon={<TrashIcon />}
              label={contextMenu.type === "directory" ? "Eliminar carpeta" : "Eliminar archivo"}
              onClick={() => deleteItem(contextMenu.path, contextMenu.name, contextMenu.type)}
              danger
            />
          </div>
        </>
      )}
    </div>
  );
}

function MenuItem({
  icon,
  label,
  onClick,
  danger,
  accent,
}: {
  icon: ReactNode;
  label: string;
  onClick: () => void;
  danger?: boolean;
  accent?: boolean;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        padding: "7px 10px",
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        gap: 6,
        color: danger ? "var(--danger)" : accent ? "var(--accent)" : "var(--text)",
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-3, rgba(255,255,255,0.06))")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
    >
      {icon} {label}
    </div>
  );
}

function TreeView({
  node,
  depth,
  onSelect,
  selectedPath,
  selectedDir,
  onSelectDir,
  filter,
  onContextMenuItem,
}: {
  node: TreeNode;
  depth: number;
  onSelect: (path: string) => void;
  selectedPath: string | null;
  selectedDir: string;
  onSelectDir: (path: string) => void;
  filter: string;
  onContextMenuItem: (x: number, y: number, path: string, name: string, type: "file" | "directory") => void;
}) {
  const [open, setOpen] = useState(depth < 1);

  if (node.type === "file") {
    if (filter && !node.name.toLowerCase().includes(filter.toLowerCase())) return null;
    return (
      <div
        className="monospace"
        onClick={() => onSelect(node.path)}
        onContextMenu={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onContextMenuItem(e.clientX, e.clientY, node.path, node.name, "file");
        }}
        title="Clic: abrir. Clic derecho: más opciones."
        style={{
          paddingLeft: depth * 14 + 8,
          cursor: "pointer",
          background: node.path === selectedPath ? "var(--bg-2)" : "transparent",
          whiteSpace: "nowrap",
        }}
      >
        {node.name}
      </div>
    );
  }

  const children = node.children ?? [];
  const visibleChildren = filter
    ? children // keep directories expanded while filtering so matches are reachable
    : children;
  const isSelectedDir = node.path === selectedDir;
  const isRoot = node.path === "." || node.path === "";

  return (
    <div>
      <div
        className="monospace"
        onClick={() => {
          setOpen((o) => !o);
          onSelectDir(node.path);
        }}
        onContextMenu={(e) => {
          if (isRoot) return; // never offer to cut/rename/delete the project root
          e.preventDefault();
          e.stopPropagation();
          onContextMenuItem(e.clientX, e.clientY, node.path, node.name || "/", "directory");
        }}
        title="Clic: expande/colapsa y la marca como carpeta destino para subir/crear archivos. Clic derecho: más opciones."
        style={{
          paddingLeft: depth * 14 + 8,
          cursor: "pointer",
          color: "var(--accent)",
          whiteSpace: "nowrap",
          background: isSelectedDir ? "var(--accent-soft)" : "transparent",
          borderRadius: "var(--radius-sm)",
        }}
      >
        {open || filter ? "▾" : "▸"} {node.name || "/"}
      </div>
      {(open || filter) &&
        visibleChildren.map((child) => (
          <TreeView
            key={child.path}
            node={child}
            depth={depth + 1}
            onSelect={onSelect}
            selectedPath={selectedPath}
            selectedDir={selectedDir}
            onSelectDir={onSelectDir}
            filter={filter}
            onContextMenuItem={onContextMenuItem}
          />
        ))}
    </div>
  );
}
