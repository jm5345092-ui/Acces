import type { ComparisonReport } from "../types";

interface Props {
  report: ComparisonReport | null;
}

export default function ComparatorPanel({ report }: Props) {
  if (!report) {
    return (
      <div style={{ padding: 12, color: "var(--text-dim)", fontSize: 13 }}>
        Todavía no hay comparación. Usa "Reconstruir y firmar" para generar ORIGINAL vs MODIFICADO.
      </div>
    );
  }

  return (
    <div style={{ padding: 12, overflow: "auto", height: "100%", fontSize: 13 }}>
      <h2 style={{ color: report.compatible ? "var(--success)" : "var(--warn)" }}>
        {report.compatible ? "✓ MODIFICACIÓN COMPATIBLE — sin pérdidas detectadas" : "⚠ diferencias detectadas"}
      </h2>

      <h3>Resumen</h3>
      <pre className="monospace" style={{ whiteSpace: "pre-wrap" }}>
        {JSON.stringify(report.summary, null, 2)}
      </pre>

      {report.expected_differences.length > 0 && (
        <>
          <h3>Diferencias esperadas</h3>
          <ul>
            {report.expected_differences.map((d) => (
              <li key={d} style={{ color: "var(--text-dim)" }}>{d}</li>
            ))}
          </ul>
        </>
      )}

      {report.important_differences.length > 0 && (
        <>
          <h3 style={{ color: "var(--warn)" }}>Diferencias importantes</h3>
          <ul>
            {report.important_differences.map((d) => (
              <li key={d} style={{ color: "var(--warn)" }}>{d}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
