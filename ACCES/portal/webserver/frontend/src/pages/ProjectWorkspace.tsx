import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import AnalysisPanel from "../components/AnalysisPanel";
import AssistantPanel from "../components/AssistantPanel";
import AssistantWarningBadge from "../components/AssistantWarningBadge";
import ChangesPanel from "../components/ChangesPanel";
import ComparatorPanel from "../components/ComparatorPanel";
import FileExplorer from "../components/FileExplorer";
import JobProgressBar from "../components/JobProgressBar";
import Modal from "../components/Modal";
import MonacoSmaliEditor from "../components/MonacoSmaliEditor";
import PipelineStatus from "../components/PipelineStatus";
import TerminalLogPanel from "../components/TerminalLogPanel";
import { api } from "../services/api";
import { streamJobLog } from "../services/jobStream";
import { useProjectStore } from "../stores/projectStore";
import type { AnalysisReport, ComparisonReport, Modification, Project } from "../types";

export type BottomTab = "terminal" | "changes" | "analysis" | "compare" | "assistant";

const TAB_LABELS: Record<BottomTab, string> = {
  terminal: "Consola",
  changes: "Cambios",
  analysis: "Análisis",
  compare: "Comparar",
  assistant: "Asistente",
};

function TerminalTabIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <polyline points="7 9 10 12 7 15" />
      <line x1="12" y1="15" x2="17" y2="15" />
    </svg>
  );
}

function ChangesTabIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  );
}

function AnalysisTabIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <line x1="5" y1="20" x2="5" y2="12" />
      <line x1="12" y1="20" x2="12" y2="5" />
      <line x1="19" y1="20" x2="19" y2="15" />
    </svg>
  );
}

function CompareTabIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="3" width="12" height="12" rx="1.5" />
      <rect x="9" y="9" width="12" height="12" rx="1.5" />
    </svg>
  );
}

function AssistantTabIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
    </svg>
  );
}

function EntryPointIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="11" cy="11" r="7" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
      <path d="M9 11l1.5 1.5L14 9" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

const TAB_ICONS: Record<BottomTab, () => JSX.Element> = {
  terminal: TerminalTabIcon,
  changes: ChangesTabIcon,
  analysis: AnalysisTabIcon,
  compare: CompareTabIcon,
  assistant: AssistantTabIcon,
};

const STATUS_MESSAGES: Record<string, string> = {
  CREATED: "Proyecto creado. Sube un APK para empezar.",
  UPLOADED: "APK subido — decodificándolo automáticamente, un momento...",
  DECODING: "Decodificando el APK con apktool, un momento...",
  DECODED: "Decodificado. Puedes explorar los archivos o ir a Análisis.",
  ANALYZING: "Analizando el Manifest, clases y recursos...",
  ANALYZED: "Análisis listo. Ahora puedes hacer cambios en la pestaña Cambios.",
  BUILDING: "Reconstruyendo y firmando el APK, un momento...",
  BUILT: "Reconstrucción lista.",
  SIGNED: "APK firmado — ya puedes descargarlo.",
  FAILED: "Algo falló. Revisa la pestaña Actividad para ver el detalle.",
};

const TRANSIENT_STATUSES = new Set(["UPLOADED", "DECODING", "ANALYZING", "BUILDING"]);
const DECODED_OR_LATER = new Set(["DECODED", "ANALYZING", "ANALYZED", "BUILDING", "BUILT", "SIGNED"]);

const STATUS_TO_JOB: Record<string, { type: string; label: string }> = {
  UPLOADED: { type: "DECODE", label: "Decodificando con apktool..." },
  DECODING: { type: "DECODE", label: "Decodificando con apktool..." },
  ANALYZING: { type: "ANALYZE", label: "Analizando Manifest, clases y recursos..." },
  BUILDING: { type: "BUILD_PIPELINE", label: "Compilando, alineando y firmando..." },
};

const DEFAULT_TOP_HEIGHT = 220; // modest by default so the tabs/console below are visible without scrolling
const MIN_PANE_HEIGHT = 80;

export default function ProjectWorkspace() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [tab, setTab] = useState<BottomTab>("terminal");
  const [analysis, setAnalysis] = useState<AnalysisReport | null>(null);
  const [comparison, setComparison] = useState<ComparisonReport | null>(null);
  const [buildBusy, setBuildBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [treeVersion, setTreeVersion] = useState(0);
  const [topHeight, setTopHeight] = useState(DEFAULT_TOP_HEIGHT);
  const [resizing, setResizing] = useState(false);
  const [lastApplied, setLastApplied] = useState<Modification | null>(null);
  const [revertBusy, setRevertBusy] = useState(false);
  const [bottomOpen, setBottomOpen] = useState(true);
  const [findingEntry, setFindingEntry] = useState(false);
  const [changesModalOpen, setChangesModalOpen] = useState(false);

  const selectedFilePath = useProjectStore((s) => s.selectedFilePath);
  const selectedLine = useProjectStore((s) => s.selectedLine);
  const setSelectedFilePath = useProjectStore((s) => s.setSelectedFilePath);
  const appendLog = useProjectStore((s) => s.appendLog);

  const prevStatus = useRef<string | null>(null);
  const splitRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!resizing) return;
    const onMove = (e: MouseEvent) => {
      const top = splitRef.current?.getBoundingClientRect().top ?? 0;
      const total = splitRef.current?.clientHeight ?? 600;
      const next = e.clientY - top;
      setTopHeight(Math.min(Math.max(next, MIN_PANE_HEIGHT), total - MIN_PANE_HEIGHT));
    };
    const onUp = () => setResizing(false);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [resizing]);

  const refreshProject = () => {
    if (!id) return;
    api.getProject(id).then((p) => {
      setProject(p);
      if (prevStatus.current && prevStatus.current !== p.status) {
        // Something advanced on its own (decode/analyze/build finished) —
        // refresh the bits of the UI that depend on it automatically,
        // instead of making the user remember to click refresh.
        setTreeVersion((v) => v + 1);
        if (p.status === "ANALYZED") refreshAnalysis();
      }
      prevStatus.current = p.status;
    }).catch((e) => setError(String(e)));
  };

  const refreshLastApplied = () => {
    if (!id) return;
    api
      .listModifications(id)
      .then((mods) => {
        const applied = mods
          .filter((m) => m.status === "APPLIED")
          .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
        setLastApplied(applied[0] ?? null);
      })
      .catch(() => {});
  };

  useEffect(() => {
    if (!id) return;
    refreshProject();
    refreshLastApplied();
    api.getAnalysis(id).then(setAnalysis).catch(() => {});
    api.getComparison(id).then(setComparison).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    if (!id || !project) return;
    if (!TRANSIENT_STATUSES.has(project.status)) return;
    const interval = setInterval(refreshProject, 3000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, project?.status]);

  if (!id) return null;

  const refreshAnalysis = () => api.getAnalysis(id).then(setAnalysis).catch(() => {});
  const refreshComparison = () => api.getComparison(id).then(setComparison).catch(() => {});

  const findEntryPoint = async () => {
    setFindingEntry(true);
    setError(null);
    try {
      let report = analysis;
      if (!report) {
        report = await api.getAnalysis(id);
        setAnalysis(report);
      }
      const ep = report.entry_point;
      const path = ep?.application_smali_path || ep?.main_activity_smali_path;
      const line = ep?.application_smali_path ? ep.application_smali_line : ep?.main_activity_smali_line;
      if (!path) {
        setError(
          "No se pudo localizar el archivo .smali del punto de inicio (Application o Activity principal). " +
            "Puede que el Manifest no declare ninguno, o que la clase no exista en el árbol decodificado."
        );
        return;
      }
      setSelectedFilePath(path, line ?? null);
    } catch {
      setError("Todavía no hay un análisis para este proyecto. Ve a la pestaña Análisis y ejecútalo primero.");
    } finally {
      setFindingEntry(false);
    }
  };

  const runBuild = async () => {
    setBuildBusy(true);
    setError(null);
    setTab("terminal");
    try {
      const { job_id } = await api.triggerBuild(id);
      appendLog(`--- proceso de reconstrucción iniciado (job ${job_id}) ---`);
      await new Promise<void>((resolve, reject) => {
        const stop = streamJobLog(job_id, (line) => {
          appendLog(line);
          if (line === "[job completed]") {
            stop();
            resolve();
          }
          if (line === "[job failed]") {
            stop();
            reject(new Error("La reconstrucción falló — revisa el log."));
          }
        });
      });
      await refreshComparison();
      refreshProject();
      setTab("compare");
    } catch (e) {
      setError(String(e));
    } finally {
      setBuildBusy(false);
    }
  };

  const revertLastChange = async () => {
    if (!lastApplied) return;
    const ok = window.confirm(
      `¿Revertir el último cambio aplicado?\n\n${lastApplied.operation} en ${lastApplied.file}\n\n"${lastApplied.description}"`
    );
    if (!ok) return;
    setRevertBusy(true);
    setError(null);
    try {
      await api.revertModification(id, lastApplied.id);
      setTreeVersion((v) => v + 1);
      refreshLastApplied();
    } catch (e) {
      setError(String(e));
    } finally {
      setRevertBusy(false);
    }
  };

  const status = project?.status ?? "CREATED";
  const canBuild = DECODED_OR_LATER.has(status) && !buildBusy;
  const canDownload = status === "SIGNED";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
          padding: "4px 12px",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-0)",
        }}
      >
        <button
          onClick={() => setChangesModalOpen(true)}
          title="Abre la ventana con todos los cambios que ha recibido este APK"
          style={{ fontSize: 12, padding: "4px 10px" }}
        >
          📋 Cambios realizados
        </button>
      </div>
      {changesModalOpen && (
        <Modal title="Cambios realizados" onClose={() => setChangesModalOpen(false)}>
          <ChangesPanel
            projectId={id}
            onApplied={() => {
              setTreeVersion((v) => v + 1);
              refreshLastApplied();
            }}
          />
        </Modal>
      )}
      <PipelineStatus status={status} activeTab={tab} onJump={setTab} />
      <JobProgressBar
        projectId={id}
        jobType={STATUS_TO_JOB[status]?.type ?? ""}
        active={!!STATUS_TO_JOB[status]}
        label={STATUS_TO_JOB[status]?.label ?? ""}
      />

      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "8px 14px",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-1)",
        }}
      >
        <Link to="/" title="Salir de este proyecto y volver a la lista">
          <button style={{ padding: "5px 10px", fontSize: 12 }}>← Salir</button>
        </Link>
        <strong>{project?.name ?? id}</strong>
        <span className="monospace" style={{ color: "var(--text-dim)", fontSize: 12 }}>
          {project?.package_name}
        </span>
        <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
          {STATUS_MESSAGES[status] ?? status}
        </span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
          <AssistantWarningBadge projectId={id} onOpen={() => { setTab("assistant"); setBottomOpen(true); }} />
          <div style={{ display: "flex", gap: 2, borderRight: "1px solid var(--border)", paddingRight: 8, marginRight: 2 }}>
            {(Object.keys(TAB_LABELS) as BottomTab[]).map((t) => {
              const Icon = TAB_ICONS[t];
              const isCurrent = bottomOpen && tab === t;
              return (
                <button
                  key={t}
                  onClick={() => {
                    setTab(t);
                    setBottomOpen(true);
                  }}
                  title={TAB_LABELS[t]}
                  style={{
                    padding: "5px 7px",
                    display: "flex",
                    alignItems: "center",
                    background: isCurrent ? "var(--accent-soft)" : "transparent",
                    border: isCurrent ? "1px solid var(--accent)" : "1px solid transparent",
                    color: isCurrent ? "var(--accent)" : "var(--text-dim)",
                  }}
                >
                  <Icon />
                </button>
              );
            })}
            <button
              onClick={findEntryPoint}
              disabled={findingEntry}
              title="Buscar el punto de inicio del APK — lo que ocurre apenas se abre la app (Application/Activity principal) — y abrir ese archivo"
              style={{
                padding: "5px 7px",
                display: "flex",
                alignItems: "center",
                background: "transparent",
                border: "1px solid transparent",
                color: "var(--text-dim)",
              }}
            >
              <EntryPointIcon />
            </button>
          </div>
          <button
            onClick={revertLastChange}
            disabled={!lastApplied || revertBusy}
            title={
              lastApplied
                ? `Revertir: ${lastApplied.operation} en ${lastApplied.file}`
                : "No hay cambios aplicados para revertir"
            }
          >
            {revertBusy ? "Revirtiendo..." : "↩ Revertir último cambio"}
          </button>
          <button
            className="primary"
            onClick={runBuild}
            disabled={!canBuild}
            title={canBuild ? "" : "Primero espera a que termine la decodificación"}
          >
            {buildBusy ? "Reconstruyendo..." : "Reconstruir y firmar"}
          </button>
          <a href={canDownload ? api.downloadUrl(id) : undefined} aria-disabled={!canDownload}>
            <button disabled={!canDownload} title={canDownload ? "" : "Todavía no hay un APK firmado"}>
              Descargar APK firmado
            </button>
          </a>
        </div>
      </header>

      {error && <p style={{ color: "var(--danger)", padding: "0 12px" }}>{error}</p>}

      <div ref={splitRef} style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
        <div
          style={
            bottomOpen
              ? { height: topHeight, maxHeight: topHeight, flex: "0 0 auto", display: "flex", minHeight: 0 }
              : { flex: "1 1 auto", display: "flex", minHeight: 0 }
          }
        >
          <div
            style={{
              width: 260,
              flex: "0 0 auto",
              borderRight: "1px solid var(--border)",
              background: "var(--bg-1)",
              overflow: "auto",
              minHeight: 0,
              maxHeight: "100%",
            }}
          >
            <FileExplorer
              key={treeVersion}
              projectId={id}
              onSelect={setSelectedFilePath}
              selectedPath={selectedFilePath}
              projectStatus={status}
              onContentChanged={refreshLastApplied}
            />
          </div>
          <div style={{ flex: 1, minWidth: 0, minHeight: 0, maxHeight: "100%", overflow: "auto", padding: 16 }}>
            <MonacoSmaliEditor
              projectId={id}
              path={selectedFilePath}
              highlightLine={selectedLine}
              onSaved={() => {
                setTreeVersion((v) => v + 1);
                refreshLastApplied();
              }}
              onClose={() => setSelectedFilePath(null)}
            />
          </div>
        </div>

        {bottomOpen && (
          <div
            className={`resize-handle${resizing ? " active" : ""}`}
            onMouseDown={() => setResizing(true)}
            title="Arrastra para cambiar el tamaño"
          />
        )}

        {bottomOpen && (
        <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", alignItems: "center", borderBottom: "1px solid var(--border)", background: "var(--bg-1)" }}>
            {(Object.keys(TAB_LABELS) as BottomTab[]).map((t) => (
              <div
                key={t}
                onClick={() => setTab(t)}
                style={{
                  padding: "8px 16px",
                  cursor: "pointer",
                  color: tab === t ? "var(--accent)" : "var(--text)",
                  borderBottom: tab === t ? "2px solid var(--accent)" : "2px solid transparent",
                  marginBottom: -1,
                  fontSize: 13,
                  fontWeight: tab === t ? 600 : 400,
                }}
              >
                {TAB_LABELS[t]}
              </div>
            ))}
            <button
              onClick={() => setBottomOpen(false)}
              title="Ocultar panel inferior"
              style={{
                marginLeft: "auto",
                marginRight: 8,
                padding: "4px 6px",
                display: "flex",
                alignItems: "center",
                background: "transparent",
                border: "1px solid transparent",
                color: "var(--text-dim)",
              }}
            >
              <CloseIcon />
            </button>
          </div>
          <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
            {tab === "terminal" && <TerminalLogPanel />}
            {tab === "changes" && (
              <ChangesPanel
                projectId={id}
                onApplied={() => {
                  setTreeVersion((v) => v + 1);
                  refreshLastApplied();
                }}
              />
            )}
            {tab === "analysis" && <AnalysisPanel projectId={id} report={analysis} onRefresh={refreshAnalysis} />}
            {tab === "compare" && <ComparatorPanel report={comparison} />}
            {tab === "assistant" && <AssistantPanel projectId={id} />}
          </div>
        </div>
        )}
      </div>
    </div>
  );
}
