import { useEffect, useState } from "react";
import { api } from "../services/api";

interface Props {
  projectId: string;
  onOpen: () => void;
}

/** Polls the strictly read-only, LLM-free analysis endpoint (no API cost)
 * so this can refresh frequently without consequence. */
export default function AssistantWarningBadge({ projectId, onOpen }: Props) {
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    const check = () => {
      api
        .getAssistantAnalysis(projectId)
        .then((findings) => {
          if (!cancelled) setCount(findings.length);
        })
        .catch(() => {
          if (!cancelled) setCount(null);
        });
    };
    check();
    const interval = setInterval(check, 20_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [projectId]);

  if (!count) return null;

  return (
    <button
      onClick={onOpen}
      title="El asistente detectó posibles inconsistencias — solo lectura, no se modificó nada"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "5px 10px",
        borderColor: "var(--warn)",
        color: "var(--warn)",
        background: "rgba(255, 183, 77, 0.1)",
      }}
    >
      ⚠ {count} posible{count === 1 ? "" : "s"} inconsistencia{count === 1 ? "" : "s"}
    </button>
  );
}
