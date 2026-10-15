import { useEffect, useRef, useState } from "react";
import { api } from "../services/api";
import type { AssistantAskResponse, AssistantFinding, AssistantMessage } from "../types";
import ConfidencePill from "./ConfidencePill";

interface Props {
  projectId: string;
}

interface ChatEntry {
  role: "user" | "assistant";
  content: string;
  findings?: AssistantFinding[];
}

function FindingCard({ finding }: { finding: AssistantFinding }) {
  return (
    <div className="card" style={{ padding: 12, marginTop: 8, fontSize: 13 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <strong>Posible inconsistencia</strong>
        <ConfidencePill confidence={finding.confidence} />
      </div>
      <p><b>Observación:</b> {finding.observation}</p>
      <p><b>Análisis:</b> {finding.analysis}</p>
      {finding.possible_problem && (
        <div>
          <b>Posible problema:</b>
          <pre className="monospace" style={{ whiteSpace: "pre-wrap", margin: "4px 0" }}>{finding.possible_problem}</pre>
        </div>
      )}
      {finding.evidence && <p className="monospace" style={{ color: "var(--text-dim)" }}><b>Evidencia:</b> {finding.evidence}</p>}
      {finding.suggestion && <p><b>Sugerencia:</b> {finding.suggestion}</p>}
    </div>
  );
}

export default function AssistantPanel({ projectId }: Props) {
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .getAssistantMessages(projectId)
      .then((messages: AssistantMessage[]) =>
        setEntries(messages.map((m) => ({ role: m.role, content: m.content })))
      )
      .catch(() => {});
  }, [projectId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [entries]);

  const ask = async () => {
    const q = question.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);
    setEntries((prev) => [...prev, { role: "user", content: q }]);
    setQuestion("");
    try {
      const res: AssistantAskResponse = await api.assistantAsk(projectId, q);
      setEntries((prev) => [...prev, { role: "assistant", content: res.message, findings: res.findings }]);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div
        style={{
          padding: "6px 12px",
          fontSize: 11,
          color: "var(--text-dim)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        Copiloto de solo lectura: observa, analiza y sugiere — nunca modifica archivos, compila, firma
        ni ejecuta nada por sí mismo. Toda acción la decides y ejecutas tú.
      </div>

      <div ref={scrollRef} style={{ flex: 1, overflow: "auto", padding: 12 }}>
        {entries.length === 0 && (
          <p style={{ color: "var(--text-dim)", fontSize: 13 }}>
            Pregunta sobre el Manifest, una clase Smali, un error de build, o pide que te explique algo de
            Android/seguridad móvil.
          </p>
        )}
        {entries.map((entry, i) => (
          <div key={i} style={{ marginBottom: 14, display: "flex", flexDirection: "column", alignItems: entry.role === "user" ? "flex-end" : "flex-start" }}>
            <div
              style={{
                maxWidth: "85%",
                background: entry.role === "user" ? "var(--accent-soft)" : "var(--bg-1)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
                padding: "8px 12px",
                fontSize: 13,
                whiteSpace: "pre-wrap",
              }}
            >
              {entry.content}
            </div>
            {entry.findings?.map((f, j) => (
              <div key={j} style={{ maxWidth: "85%", width: "100%" }}>
                <FindingCard finding={f} />
              </div>
            ))}
          </div>
        ))}
      </div>

      {error && <p style={{ color: "var(--danger)", padding: "0 12px", fontSize: 12 }}>{error}</p>}

      <div style={{ display: "flex", gap: 8, padding: 10, borderTop: "1px solid var(--border)" }}>
        <textarea
          style={{ flex: 1, resize: "none", height: 44 }}
          placeholder="Escribe tu pregunta..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask();
            }
          }}
        />
        <button className="primary" onClick={ask} disabled={busy || !question.trim()}>
          {busy ? "..." : "Preguntar"}
        </button>
      </div>
    </div>
  );
}
