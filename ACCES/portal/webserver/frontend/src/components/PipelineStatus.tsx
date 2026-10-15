import type { BottomTab } from "../pages/ProjectWorkspace";

interface Step {
  key: BottomTab;
  label: string;
  isDone: (status: string) => boolean;
  isActive: (status: string) => boolean;
}

const STEPS: Step[] = [
  {
    key: "terminal",
    label: "1. Subir",
    isDone: (s) => !["CREATED"].includes(s),
    isActive: (s) => s === "CREATED" || s === "UPLOADED",
  },
  {
    key: "terminal",
    label: "2. Decodificar",
    isDone: (s) => !["CREATED", "UPLOADED", "DECODING"].includes(s),
    isActive: (s) => s === "DECODING",
  },
  {
    key: "analysis",
    label: "3. Analizar",
    isDone: (s) => ["ANALYZED", "BUILDING", "BUILT", "SIGNED"].includes(s),
    isActive: (s) => s === "ANALYZING" || s === "DECODED",
  },
  {
    key: "changes",
    label: "4. Modificar",
    isDone: (s) => ["BUILDING", "BUILT", "SIGNED"].includes(s),
    isActive: (s) => s === "ANALYZED",
  },
  {
    key: "compare",
    label: "5. Reconstruir y firmar",
    isDone: (s) => s === "SIGNED",
    isActive: (s) => s === "BUILDING" || s === "BUILT",
  },
];

interface Props {
  status: string;
  activeTab: BottomTab;
  onJump: (tab: BottomTab) => void;
}

export default function PipelineStatus({ status, activeTab, onJump }: Props) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 4,
        padding: "8px 14px",
        borderBottom: "1px solid var(--border)",
        background: "var(--bg-0)",
        overflowX: "auto",
      }}
    >
      {STEPS.map((step, i) => {
        const done = status === "FAILED" ? false : step.isDone(status);
        const active = status !== "FAILED" && step.isActive(status);
        const isTabOpen = activeTab === step.key;
        return (
          <div key={step.label} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <button
              onClick={() => onJump(step.key)}
              title={active ? "En curso" : done ? "Completado" : "Todavía no"}
              style={{
                padding: "4px 10px",
                fontSize: 12,
                fontWeight: active || isTabOpen ? 600 : 500,
                color: done ? "var(--accent)" : active ? "var(--text)" : "var(--text-dim)",
                background: isTabOpen ? "var(--bg-2)" : "transparent",
                border: active ? "1px solid var(--accent)" : "1px solid transparent",
                borderRadius: 999,
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              {done && <span style={{ color: "var(--accent)" }}>✓</span>}
              {active && <span className="pill pill-hypothesis" style={{ padding: "1px 6px" }}>ahora</span>}
              {step.label}
            </button>
            {i < STEPS.length - 1 && <span style={{ color: "var(--border-strong)" }}>→</span>}
          </div>
        );
      })}
    </div>
  );
}
