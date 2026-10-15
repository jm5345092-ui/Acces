import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../services/api";
import { streamJobLog } from "../services/jobStream";

export default function GeneratorNew() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [color, setColor] = useState("#22e35f");
  const [icon, setIcon] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const logRef = useRef<HTMLDivElement>(null);

  const appendLog = (line: string) => {
    setLog((prev) => [...prev, line]);
    requestAnimationFrame(() => logRef.current?.scrollTo(0, logRef.current.scrollHeight));
  };

  const submit = async () => {
    if (!name || !url || !icon) {
      setError("Nombre, URL e icono son obligatorios.");
      return;
    }
    setBusy(true);
    setError(null);
    setLog([]);
    try {
      const { job_id, slug } = await api.createGeneratorApk(name, url, color, icon);
      appendLog(`--- compilando "${name}" (job ${job_id}) ---`);
      await new Promise<void>((resolve, reject) => {
        const stop = streamJobLog(job_id, (line) => {
          appendLog(line);
          if (line === "[job completed]") {
            stop();
            resolve();
          }
          if (line === "[job failed]") {
            stop();
            reject(new Error("La compilación falló — revisa el log arriba."));
          }
        });
      });
      appendLog(`--- listo: ${slug}.apk ---`);
      setTimeout(() => navigate("/"), 1200);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ padding: "32px 24px", maxWidth: 560, margin: "0 auto", width: "100%" }}>
      <h1 style={{ fontSize: 24, marginBottom: 4 }}>Generar app desde una URL</h1>
      <p style={{ color: "var(--text-dim)", fontSize: 13, marginBottom: 24 }}>
        Crea un APK que envuelve un sitio web en una app nativa (WebView), firmado con la
        misma llave que usa el resto del proyecto. La primera compilación tarda varios
        minutos; las siguientes son más rápidas.
      </p>

      <div className="card" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
        <label style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 13 }}>
          Nombre de la app
          <input
            placeholder="Panadería La Espiga"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={busy}
            maxLength={40}
          />
        </label>

        <label style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 13 }}>
          URL del sitio
          <input
            type="url"
            placeholder="https://laespiga.com"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={busy}
          />
        </label>

        <label style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
          Color de marca
          <input
            type="color"
            value={color}
            onChange={(e) => setColor(e.target.value)}
            disabled={busy}
            style={{ width: 44, height: 32, padding: 2 }}
          />
          <span className="monospace" style={{ color: "var(--text-dim)" }}>{color}</span>
        </label>

        <label style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 13 }}>
          Icono (PNG o JPG, mínimo 192×192)
          <input
            type="file"
            accept="image/png,image/jpeg"
            onChange={(e) => setIcon(e.target.files?.[0] ?? null)}
            disabled={busy}
          />
        </label>

        {error && <p style={{ color: "var(--danger)", fontSize: 13, margin: 0 }}>{error}</p>}

        <button className="primary" onClick={submit} disabled={busy} style={{ padding: "9px 0" }}>
          {busy ? "Compilando..." : "Generar APK"}
        </button>

        {log.length > 0 && (
          <div
            ref={logRef}
            className="monospace"
            style={{
              maxHeight: 260,
              overflowY: "auto",
              background: "var(--bg-0)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)",
              padding: 10,
              fontSize: 11.5,
              lineHeight: 1.5,
              color: "var(--text-dim)",
              whiteSpace: "pre-wrap",
            }}
          >
            {log.map((line, i) => (
              <div key={i}>{line}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
