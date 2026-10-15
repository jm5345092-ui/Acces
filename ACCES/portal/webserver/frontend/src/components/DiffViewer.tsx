import { DiffEditor } from "@monaco-editor/react";
import type { Modification } from "../types";

interface Props {
  modification: Modification;
  onApply: () => void;
  onRevert: () => void;
  onCancel?: () => void;
}

export default function DiffViewer({ modification, onApply, onRevert, onCancel }: Props) {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: 8, borderBottom: "1px solid var(--border)" }}>
        <div className="monospace" style={{ fontWeight: "bold" }}>
          {modification.file}
        </div>
        <div style={{ fontSize: 12, color: "var(--text-dim)" }}>{modification.description}</div>
        <div style={{ fontSize: 12 }}>
          {modification.operation} — estado: <b>{modification.status}</b>
        </div>
      </div>
      <div style={{ flex: 1, minHeight: 200 }}>
        {modification.is_binary ? (
          <div style={{ padding: 16, color: "var(--text-dim)", fontSize: 13 }}>
            Archivo binario (imagen, audio, etc.) — no se muestra un diff de texto.
            {modification.after_content && (
              <> Tamaño nuevo: ~{Math.round((modification.after_content.length * 3) / 4 / 1024)} KB.</>
            )}
          </div>
        ) : (
          <DiffEditor
            height="100%"
            theme="vs-dark"
            original={modification.before_content}
            modified={modification.after_content}
            options={{ readOnly: true, minimap: { enabled: false }, fontSize: 12 }}
          />
        )}
      </div>
      <div style={{ display: "flex", gap: 8, padding: 8, borderTop: "1px solid var(--border)" }}>
        {modification.status === "PENDING" && (
          <>
            <button onClick={onApply}>Aplicar</button>
            {onCancel && <button onClick={onCancel}>Cancelar</button>}
          </>
        )}
        {modification.status === "APPLIED" && <button onClick={onRevert}>Revertir</button>}
      </div>
    </div>
  );
}
