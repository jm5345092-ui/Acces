import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../services/api";
import type { GeneratorApk, Project } from "../types";

const STATUS_TONE: Record<string, string> = {
  CREATED: "pill-suggestion",
  UPLOADED: "pill-user",
  DECODING: "pill-hypothesis",
  DECODED: "pill-user",
  ANALYZING: "pill-hypothesis",
  ANALYZED: "pill-confirmed",
  BUILDING: "pill-hypothesis",
  BUILT: "pill-confirmed",
  SIGNED: "pill-confirmed",
  FAILED: "pill-hypothesis",
};

function formatSize(bytes: number): string {
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

export default function ProjectList() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [generatorApks, setGeneratorApks] = useState<GeneratorApk[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [importingSlug, setImportingSlug] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.listProjects(), api.listGeneratorApks().catch(() => [])])
      .then(([p, g]) => {
        setProjects(p);
        setGeneratorApks(g);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const remove = async (id: string) => {
    if (!confirm("¿Eliminar este proyecto y todos sus datos de workspace?")) return;
    await api.deleteProject(id);
    setProjects((prev) => prev.filter((p) => p.id !== id));
  };

  const createProjectFromGenerator = async (slug: string) => {
    setImportingSlug(slug);
    setImportError(null);
    try {
      const { project } = await api.importGeneratorApk(slug);
      setProjects((prev) => [project, ...prev]);
    } catch (e) {
      setImportError(String(e));
    } finally {
      setImportingSlug(null);
    }
  };

  const signedProjects = projects.filter((p) => p.status === "SIGNED");

  return (
    <div style={{ padding: "32px 24px", maxWidth: 1400, margin: "0 auto", width: "100%" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26 }}>Proyectos</h1>
          <p style={{ margin: "4px 0 0", color: "var(--text-dim)", fontSize: 13 }}>
            Tu laboratorio de análisis y modificación de APKs.
          </p>
        </div>
        <Link to="/new">
          <button className="primary">+ Nuevo proyecto</button>
        </Link>
      </header>

      {error && <p style={{ color: "var(--danger)" }}>{error}</p>}
      {importError && <p style={{ color: "var(--danger)" }}>{importError}</p>}

      {!loading && (
        <div className="dash-grid">
          {/* --- Left: APKs built by the generador de apks --- */}
          <section className="dash-panel">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h2 className="dash-panel__title">APKs generadas</h2>
              <Link to="/generator/new">
                <button style={{ fontSize: 11, padding: "5px 10px" }}>+ Generar app</button>
              </Link>
            </div>
            {generatorApks.length === 0 && (
              <div className="dash-panel__empty">
                No hay APKs del generador disponibles en este servidor.
              </div>
            )}
            {generatorApks.map((g) => (
              <div key={g.slug} className="dash-card">
                <div className="dash-card__head">
                  {g.has_icon ? (
                    <img src={api.generatorIconUrl(g.slug)} alt="" className="dash-card__icon" />
                  ) : (
                    <div className="dash-card__icon-fallback">{g.name.charAt(0).toUpperCase()}</div>
                  )}
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div className="dash-card__name" title={g.name}>{g.name}</div>
                    <div className="monospace dash-card__meta">{g.package || "—"}</div>
                  </div>
                </div>
                <div className="dash-card__meta">{formatSize(g.size_bytes)}</div>
                <div className="dash-card__actions">
                  <button
                    className="primary"
                    disabled={importingSlug === g.slug}
                    onClick={() => createProjectFromGenerator(g.slug)}
                  >
                    {importingSlug === g.slug ? "Creando..." : "Crear proyecto"}
                  </button>
                  <a href={api.generatorApkDownloadUrl(g.slug)} download>
                    Descargar
                  </a>
                </div>
              </div>
            ))}
          </section>

          {/* --- Middle: APK-Lab projects --- */}
          <section className="dash-panel">
            <h2 className="dash-panel__title">Proyectos</h2>
            {projects.length === 0 && (
              <div className="dash-panel__empty">
                Todavía no hay proyectos. Crea uno manualmente o desde una APK generada.
              </div>
            )}
            {projects.map((p) => (
              <div key={p.id} className="dash-card">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                  <Link to={`/projects/${p.id}`} style={{ color: "var(--text)", fontWeight: 600, fontSize: 13.5 }}>
                    {p.name}
                  </Link>
                  <span className={`pill ${STATUS_TONE[p.status] ?? "pill-suggestion"}`}>{p.status}</span>
                </div>
                <div className="monospace dash-card__meta">{p.package_name || "sin analizar todavía"}</div>
                <div className="dash-card__meta">{new Date(p.created_at).toLocaleString()}</div>
                <div className="dash-card__actions">
                  <Link to={`/projects/${p.id}`} style={{ flex: 1 }}>
                    <button style={{ width: "100%" }}>Abrir</button>
                  </Link>
                  <button onClick={() => remove(p.id)} title="Eliminar proyecto">
                    Eliminar
                  </button>
                </div>
              </div>
            ))}
          </section>

          {/* --- Right: latest signed APK per project --- */}
          <section className="dash-panel">
            <h2 className="dash-panel__title">APKs firmadas</h2>
            {signedProjects.length === 0 && (
              <div className="dash-panel__empty">
                Ninguna todavía — compila y firma un proyecto para verlo aquí.
              </div>
            )}
            {signedProjects.map((p) => (
              <div key={p.id} className="dash-card">
                <div className="dash-card__name" title={p.name}>{p.name}</div>
                <div className="monospace dash-card__meta">{p.package_name || "—"}</div>
                <div className="dash-card__meta">{new Date(p.created_at).toLocaleString()}</div>
                <div className="dash-card__actions">
                  <a href={api.downloadUrl(p.id)} download>
                    Descargar
                  </a>
                </div>
              </div>
            ))}
          </section>
        </div>
      )}
    </div>
  );
}
