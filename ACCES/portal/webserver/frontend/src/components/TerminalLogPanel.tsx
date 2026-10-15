import { useEffect, useRef } from "react";
import { useProjectStore } from "../stores/projectStore";

export default function TerminalLogPanel() {
  const logLines = useProjectStore((s) => s.logLines);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight });
  }, [logLines]);

  return (
    <div
      ref={ref}
      className="monospace"
      style={{
        height: "100%",
        overflow: "auto",
        padding: 8,
        fontSize: 12,
        whiteSpace: "pre-wrap",
        color: "var(--text)",
      }}
    >
      {logLines.length === 0 ? (
        <span style={{ color: "var(--text-dim)" }}>
          Todavía no hay actividad. Sube un APK o inicia una reconstrucción para ver el log en vivo aquí.
        </span>
      ) : (
        logLines.map((line, i) => <div key={i}>{line}</div>)
      )}
    </div>
  );
}
