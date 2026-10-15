import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../services/api";

export default function NewProject() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!name || !file) {
      setError("El nombre y un archivo .apk son obligatorios.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const project = await api.createProject(name);
      await api.uploadApk(project.id, file);
      navigate(`/projects/${project.id}`);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ padding: "32px 24px", maxWidth: 520, margin: "0 auto", width: "100%" }}>
      <h1 style={{ fontSize: 24, marginBottom: 4 }}>Nuevo proyecto</h1>
      <p style={{ color: "var(--text-dim)", fontSize: 13, marginBottom: 24 }}>
        El APK se sube tal cual y se guarda como solo lectura; la decodificación ocurre
        automáticamente en el servidor (contenedor worker) justo después de subirlo.
      </p>

      <div className="card" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
        <label style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 13 }}>
          Nombre del proyecto
          <input
            style={{ width: "100%" }}
            placeholder="mi-apk-de-prueba"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>

        <label
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            const dropped = e.dataTransfer.files?.[0];
            if (dropped) setFile(dropped);
          }}
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 6,
            padding: "28px 16px",
            borderRadius: "var(--radius)",
            border: `1.5px dashed ${dragOver ? "var(--accent)" : "var(--border-strong)"}`,
            background: dragOver ? "var(--accent-soft)" : "var(--bg-2)",
            cursor: "pointer",
            textAlign: "center",
            transition: "border-color 0.15s ease, background-color 0.15s ease",
          }}
        >
          <input
            type="file"
            accept=".apk"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            style={{ display: "none" }}
          />
          <span style={{ fontSize: 13 }}>
            {file ? <span className="monospace">{file.name}</span> : "Arrastra un .apk aquí o haz clic para elegirlo"}
          </span>
          {file && (
            <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
              {(file.size / 1024 / 1024).toFixed(2)} MB
            </span>
          )}
        </label>

        {error && <p style={{ color: "var(--danger)", fontSize: 13, margin: 0 }}>{error}</p>}

        <button className="primary" onClick={submit} disabled={busy} style={{ padding: "9px 0" }}>
          {busy ? "Subiendo..." : "Crear y subir"}
        </button>
      </div>
    </div>
  );
}
