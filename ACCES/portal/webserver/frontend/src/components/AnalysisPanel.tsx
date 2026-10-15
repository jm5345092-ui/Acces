import { useState } from "react";
import type { AnalysisReport } from "../types";
import { api } from "../services/api";
import { pollJobUntilDone } from "../services/jobStream";

interface Props {
  projectId: string;
  report: AnalysisReport | null;
  onRefresh: () => void;
}

export default function AnalysisPanel({ projectId, report, onRefresh }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const { job_id } = await api.runAnalysis(projectId);
      await pollJobUntilDone(job_id, { timeoutMs: 180_000 });
      onRefresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ padding: 12, overflow: "auto", height: "100%" }}>
      <button className="primary" onClick={run} disabled={busy}>
        {busy ? "Analizando..." : report ? "Volver a analizar" : "Analizar APK"}
      </button>
      {!report && !busy && (
        <p style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 8 }}>
          Esto lee el Manifest, cuenta clases/métodos y recursos, y muestra el certificado — no modifica nada.
        </p>
      )}
      {error && <p style={{ color: "var(--danger)" }}>{error}</p>}

      {report && (
        <div style={{ marginTop: 12, display: "grid", gap: 16, fontSize: 13 }}>
          <section>
            <h3>Manifest</h3>
            <p>Package: <span className="monospace">{report.manifest.package}</span></p>
            <p>Versión: {report.manifest.version_name} ({report.manifest.version_code})</p>
            <p>
              SDK: mínimo {report.manifest.min_sdk || "?"} / objetivo {report.manifest.target_sdk || "?"}
              {report.manifest.compile_sdk ? ` / compilado con ${report.manifest.compile_sdk}` : ""}
            </p>
            {report.manifest.apktool_version && (
              <p style={{ color: "var(--text-dim)", fontSize: 11 }}>
                Decodificado con apktool {report.manifest.apktool_version}
              </p>
            )}
            <p>Activities: {report.manifest.activities.length} · Services: {report.manifest.services.length} ·
              Receivers: {report.manifest.receivers.length} · Providers: {report.manifest.providers.length}</p>
            <p>Permisos: {report.manifest.permissions.length}</p>
          </section>

          <section>
            <h3>DEX / Smali</h3>
            <p>Clases: {report.dex.total_classes} · Métodos: {report.dex.total_methods} · Paquetes: {report.dex.package_count}</p>
            <ul>
              {Object.entries(report.dex.per_dex).map(([name, stats]) => (
                <li key={name} className="monospace">
                  {name}: {stats.classes} clases, {stats.methods} métodos
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h3>Recursos / Assets / Nativas</h3>
            <p>Recursos: {report.resources.count} · Assets: {report.assets.count} · Librerías nativas: {report.native_libs.length}</p>
          </section>

          <section>
            <h3>Certificado</h3>
            <pre className="monospace" style={{ whiteSpace: "pre-wrap", fontSize: 11 }}>{report.certificate}</pre>
          </section>
        </div>
      )}
    </div>
  );
}
