import { useEffect, useState } from "react";
import { api } from "../services/api";
import { pollJobUntilDone } from "../services/jobStream";
import type { ToolStatusEntry } from "../types";

function countryCodeToFlag(code: string): string {
  if (!code || code.length !== 2) return "";
  return String.fromCodePoint(...[...code.toUpperCase()].map((c) => 127397 + c.charCodeAt(0)));
}

export default function ToolStatusBanner() {
  const [tools, setTools] = useState<ToolStatusEntry[] | null>(null);
  const [checking, setChecking] = useState(false);
  const [open, setOpen] = useState(false);
  const [serverInfo, setServerInfo] = useState<{
    ok: boolean;
    ip: string;
    country: string;
    country_code: string;
    region: string;
    city: string;
    isp: string;
  } | null>(null);

  useEffect(() => {
    api.getServerInfo().then(setServerInfo).catch(() => {});
  }, []);

  const check = async () => {
    setChecking(true);
    try {
      const { job_id } = await api.checkTools();
      await pollJobUntilDone(job_id, { timeoutMs: 30_000 });
      const status = await api.getToolStatus();
      setTools(status.tools);
    } catch {
      // Tool check genuinely requires the worker container; surface as unknown rather than crash.
      setTools(null);
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    api.getToolStatus().then((s) => setTools(s.tools.length ? s.tools : null)).catch(() => {});
  }, []);

  const allOk = tools?.every((t) => t.ok) ?? null;

  return (
    <div style={{ borderBottom: "1px solid var(--border)", fontSize: 12 }}>
      <div
        style={{ padding: "4px 12px", cursor: "pointer", display: "flex", gap: 8, alignItems: "center" }}
        onClick={() => setOpen((o) => !o)}
      >
        <span>{open ? "▾" : "▸"}</span>
        <span>Entorno del servidor:</span>
        <span style={{ color: allOk === null ? "var(--text-dim)" : allOk ? "var(--success)" : "var(--warn)" }}>
          {allOk === null ? "sin verificar — haz clic para comprobar" : allOk ? "todas las herramientas listas" : "faltan herramientas"}
        </span>
        {serverInfo?.ok && (
          <span
            className="monospace"
            title={`Servidor alojado en ${serverInfo.city}, ${serverInfo.region}, ${serverInfo.country} — IP ${serverInfo.ip} — ${serverInfo.isp}`}
            style={{ marginLeft: "auto", color: "var(--text-dim)", display: "flex", alignItems: "center", gap: 6 }}
          >
            <span style={{ fontSize: 15 }}>{countryCodeToFlag(serverInfo.country_code)}</span>
            {serverInfo.city}, {serverInfo.country} · {serverInfo.ip}
          </span>
        )}
        <button
          onClick={(e) => { e.stopPropagation(); check(); }}
          disabled={checking}
          style={{ marginLeft: serverInfo?.ok ? 0 : "auto" }}
        >
          {checking ? "Verificando..." : "Verificar"}
        </button>
      </div>
      {open && tools && (
        <table className="monospace" style={{ width: "100%", fontSize: 12 }}>
          <tbody>
            {tools.map((t) => (
              <tr key={t.name}>
                <td style={{ padding: "2px 12px" }}>{t.name}</td>
                <td style={{ color: t.ok ? "var(--success)" : "var(--danger)" }}>{t.ok ? "OK" : "falta"}</td>
                <td style={{ color: "var(--text-dim)" }}>{t.version}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
