import type { ReactNode } from "react";

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
}

export default function Modal({ title, onClose, children }: Props) {
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 200,
        background: "rgba(0,0,0,0.55)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="card"
        style={{
          width: "min(960px, 100%)",
          height: "min(640px, 100%)",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            padding: "10px 14px",
            borderBottom: "1px solid var(--border)",
            background: "var(--bg-2)",
          }}
        >
          <strong style={{ flex: 1 }}>{title}</strong>
          <button onClick={onClose} title="Cerrar" style={{ padding: "3px 9px", fontSize: 13 }}>
            ✕
          </button>
        </div>
        <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>{children}</div>
      </div>
    </div>
  );
}
