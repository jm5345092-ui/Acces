import Editor, { type Monaco } from "@monaco-editor/react";
import type { editor as MonacoEditorNS } from "monaco-editor";
import { useEffect, useRef, useState } from "react";
import { registerSmaliLanguage } from "../editor/smaliLanguage";
import { api } from "../services/api";

interface Props {
  projectId: string;
  path: string | null;
  /** When set (e.g. by "buscar el punto de inicio"), the editor scrolls to
   * and highlights this 1-based line once the file content has loaded. */
  highlightLine?: number | null;
  /** Called right after a Ctrl+S / "Guardar" save lands as an applied
   * Modification, so the parent can refresh the tree, the "Cambios
   * realizados" window, the revert button, etc. */
  onSaved?: () => void;
  onClose?: () => void;
}

const COMPACT_HEIGHT = 420;
const EXPANDED_HEIGHT = 760;

function languageFor(path: string): string {
  if (path.endsWith(".smali")) return "smali";
  if (path.endsWith(".xml")) return "xml";
  if (path.endsWith(".json")) return "json";
  if (path.endsWith(".html") || path.endsWith(".htm")) return "html";
  if (path.endsWith(".php")) return "php";
  if (path.endsWith(".css")) return "css";
  if (path.endsWith(".js")) return "javascript";
  if (path.endsWith(".ts")) return "typescript";
  if (path.endsWith(".java") || path.endsWith(".kt")) return "java";
  if (path.endsWith(".md")) return "markdown";
  if (path.endsWith(".yml") || path.endsWith(".yaml")) return "yaml";
  return "plaintext";
}

export default function MonacoSmaliEditor({ projectId, path, highlightLine, onSaved, onClose }: Props) {
  const [content, setContent] = useState<string>("");
  const [savedContent, setSavedContent] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [justSaved, setJustSaved] = useState(false);
  const editorRef = useRef<MonacoEditorNS.IStandaloneCodeEditor | null>(null);
  const decorationsRef = useRef<string[]>([]);
  // Tracks which path the entry-point highlight/cursor-jump has already been
  // applied to, so it fires once per navigation — not on every keystroke
  // (content changes on every keystroke via onChange, and re-running
  // setPosition() there was yanking the cursor back to this line after
  // every character typed anywhere else in the file).
  const highlightedForPath = useRef<string | null>(null);

  const dirty = content !== savedContent;

  // Keeps the Ctrl+S command (bound once, at mount) always acting on the
  // latest project/path/content instead of whatever was current when the
  // editor first mounted.
  const saveRef = useRef<() => void>(() => {});

  useEffect(() => {
    if (!path) return;
    setError(null);
    setSaveError(null);
    setExpanded(false);
    api
      .readFile(projectId, path)
      .then((res) => {
        setContent(res.content);
        setSavedContent(res.content);
      })
      .catch((e) => setError(String(e)));
  }, [projectId, path]);

  useEffect(() => {
    const ed = editorRef.current;
    if (!ed) return;
    if (!highlightLine) {
      decorationsRef.current = ed.deltaDecorations(decorationsRef.current, []);
      highlightedForPath.current = null;
      return;
    }
    if (highlightedForPath.current === path) return; // already jumped there for this file — don't fight the user's typing
    highlightedForPath.current = path;
    ed.revealLineInCenter(highlightLine);
    ed.setPosition({ lineNumber: highlightLine, column: 1 });
    decorationsRef.current = ed.deltaDecorations(decorationsRef.current, [
      {
        range: { startLineNumber: highlightLine, startColumn: 1, endLineNumber: highlightLine, endColumn: 1 },
        options: {
          isWholeLine: true,
          className: "entry-point-highlight-line",
          glyphMarginClassName: "entry-point-highlight-glyph",
        },
      },
    ]);
  }, [content, highlightLine, path]);

  const handleSave = async () => {
    if (!path || saving) return;
    if (content === savedContent) return; // nothing to save
    setSaving(true);
    setSaveError(null);
    try {
      const mod = await api.proposeModification(projectId, {
        operation: "modify_resource",
        path,
        content,
        is_binary: false,
      });
      await api.applyModification(projectId, mod.id);
      setSavedContent(content);
      setJustSaved(true);
      setTimeout(() => setJustSaved(false), 1500);
      onSaved?.();
    } catch (e) {
      setSaveError(String(e));
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    saveRef.current = handleSave;
  });

  if (!path) {
    return (
      <div style={{ color: "var(--text-dim)", padding: 16, fontSize: 13, maxWidth: 520 }}>
        Selecciona un archivo del explorador para editarlo. Escribe directamente y guarda con{" "}
        <b>Ctrl+S</b> (o el botón Guardar) — cada guardado queda registrado como un cambio en la ventana{" "}
        <b>Cambios realizados</b> y se puede revertir.
      </div>
    );
  }

  return (
    <div
      className="card"
      style={{
        display: "flex",
        flexDirection: "column",
        maxWidth: 900,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "6px 10px",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-2)",
        }}
      >
        <span className="monospace" style={{ fontSize: 12, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {path}
          {dirty && (
            <span title="Cambios sin guardar" style={{ color: "var(--warn)", marginLeft: 6 }}>
              ●
            </span>
          )}
        </span>
        {saveError && <span style={{ color: "var(--danger)", fontSize: 11 }}>{saveError}</span>}
        {justSaved && !saveError && <span style={{ color: "var(--success)", fontSize: 11 }}>Guardado ✓</span>}
        <button
          onClick={handleSave}
          disabled={!dirty || saving}
          title="Guardar (Ctrl+S)"
          className={dirty ? "primary" : undefined}
          style={{ padding: "3px 8px", fontSize: 12 }}
        >
          {saving ? "Guardando..." : "Guardar"}
        </button>
        <button onClick={() => setExpanded((e) => !e)} style={{ padding: "3px 8px", fontSize: 12 }}>
          {expanded ? "Reducir" : "Expandir"}
        </button>
        {onClose && (
          <button
            onClick={() => {
              if (dirty && !window.confirm("Hay cambios sin guardar en este archivo. ¿Cerrarlo de todas formas?")) {
                return;
              }
              onClose();
            }}
            title="Cerrar archivo"
            style={{ padding: "3px 8px", fontSize: 12 }}
          >
            ✕
          </button>
        )}
      </div>

      {error ? (
        <div style={{ color: "var(--danger)", padding: 16 }}>{error}</div>
      ) : (
        <Editor
          height={expanded ? EXPANDED_HEIGHT : COMPACT_HEIGHT}
          theme="vs-dark"
          path={path}
          language={languageFor(path)}
          value={content}
          onChange={(value) => setContent(value ?? "")}
          beforeMount={(monaco: Monaco) => registerSmaliLanguage(monaco)}
          onMount={(ed, monacoInstance) => {
            editorRef.current = ed;
            ed.addCommand(monacoInstance.KeyMod.CtrlCmd | monacoInstance.KeyCode.KeyS, () => {
              saveRef.current();
            });
          }}
          options={{ readOnly: false, minimap: { enabled: false }, fontSize: 13, glyphMargin: true }}
        />
      )}
    </div>
  );
}
