import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { Modification } from "../types";
import DiffViewer from "./DiffViewer";

interface Props {
  projectId: string;
  onApplied?: () => void;
}

type OpKind = "create_smali_class" | "insert_smali_instruction" | "modify_manifest";

const STATUS_LABELS: Record<string, string> = {
  PENDING: "Pendiente de aplicar",
  APPLIED: "Aplicado",
  REVERTED: "Revertido",
  FAILED: "Falló",
};

export default function ChangesPanel({ projectId, onApplied }: Props) {
  const [mods, setMods] = useState<Modification[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkResult, setBulkResult] = useState<string | null>(null);

  const [opKind, setOpKind] = useState<OpKind>("create_smali_class");
  const [form, setForm] = useState<Record<string, string>>({});
  const [aiInstruction, setAiInstruction] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [aiSummary, setAiSummary] = useState<string | null>(null);

  const refresh = () => api.listModifications(projectId).then(setMods).catch((e) => setError(String(e)));

  useEffect(() => {
    refresh();
  }, [projectId]);

  const active = mods.find((m) => m.id === activeId) ?? null;
  const pendingCount = mods.filter((m) => m.status === "PENDING").length;

  const propose = async () => {
    setError(null);
    try {
      await api.proposeModification(projectId, { operation: opKind, ...form });
      setForm({});
      refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  const apply = async (id: string) => {
    setError(null);
    try {
      await api.applyModification(projectId, id);
      refresh();
      onApplied?.();
    } catch (e) {
      setError(String(e));
    }
  };
  const revert = async (id: string) => {
    setError(null);
    try {
      await api.revertModification(projectId, id);
      refresh();
      onApplied?.();
    } catch (e) {
      setError(String(e));
    }
  };

  const applyAllPending = async () => {
    setBulkBusy(true);
    setBulkResult(null);
    try {
      const res = await api.applyAllPending(projectId);
      setBulkResult(
        `${res.applied.length} aplicado(s)` + (res.failed.length ? `, ${res.failed.length} con error` : "")
      );
      refresh();
      onApplied?.();
    } catch (e) {
      setError(String(e));
    } finally {
      setBulkBusy(false);
    }
  };

  const runAi = async () => {
    if (!aiInstruction.trim()) return;
    setAiBusy(true);
    setAiSummary(null);
    setError(null);
    try {
      const result = await api.aiPlan(projectId, aiInstruction);
      setAiSummary(result.summary || "Plan generado — revisa los cambios propuestos en el historial.");
      refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setAiBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", height: "100%" }}>
      <div style={{ width: 340, borderRight: "1px solid var(--border)", overflow: "auto", padding: 10 }}>
        <section style={{ marginBottom: 14 }}>
          <h4 style={{ margin: "4px 0" }}>Describe el cambio que quieres</h4>
          <p style={{ fontSize: 12, color: "var(--text-dim)", margin: "0 0 8px" }}>
            Escribe en lenguaje natural qué quieres hacer. Se genera una propuesta con su diff — nada se
            aplica hasta que tú lo confirmes abajo.
          </p>
          <textarea
            style={{ width: "100%", height: 64 }}
            placeholder="Ej: crea una clase Logger en com.example.app y llámala al iniciar la Activity principal"
            value={aiInstruction}
            onChange={(e) => setAiInstruction(e.target.value)}
          />
          <button className="primary" onClick={runAi} disabled={aiBusy || !aiInstruction.trim()} style={{ marginTop: 6, width: "100%" }}>
            {aiBusy ? "Generando plan..." : "Generar propuesta"}
          </button>
          {aiSummary && <p style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 6 }}>{aiSummary}</p>}
        </section>

        <section style={{ marginBottom: 14 }}>
          <button
            onClick={() => setAdvancedOpen((o) => !o)}
            style={{ width: "100%", textAlign: "left", background: "transparent", border: "1px solid var(--border)" }}
          >
            {advancedOpen ? "▾" : "▸"} Modo avanzado (editar campos Smali manualmente)
          </button>
          {advancedOpen && (
            <div style={{ marginTop: 8 }}>
              <select
                value={opKind}
                onChange={(e) => {
                  setOpKind(e.target.value as OpKind);
                  setForm({});
                }}
                style={{ width: "100%" }}
              >
                <option value="create_smali_class">Crear clase Smali</option>
                <option value="insert_smali_instruction">Insertar instrucción en un método</option>
                <option value="modify_manifest">Modificar atributo del Manifest</option>
              </select>

              {opKind === "create_smali_class" && (
                <>
                  <input placeholder="package (com.example.app)" style={{ width: "100%", marginTop: 6 }}
                    value={form.package ?? ""} onChange={(e) => setForm({ ...form, package: e.target.value })} />
                  <input placeholder="class_name (Logger)" style={{ width: "100%", marginTop: 6 }}
                    value={form.class_name ?? ""} onChange={(e) => setForm({ ...form, class_name: e.target.value })} />
                </>
              )}
              {opKind === "insert_smali_instruction" && (
                <>
                  <input placeholder="target_class (com/example/app/MainActivity)" style={{ width: "100%", marginTop: 6 }}
                    value={form.target_class ?? ""} onChange={(e) => setForm({ ...form, target_class: e.target.value })} />
                  <input placeholder="target_method (onCreate(Landroid/os/Bundle;)V)" style={{ width: "100%", marginTop: 6 }}
                    value={form.target_method ?? ""} onChange={(e) => setForm({ ...form, target_method: e.target.value })} />
                  <input placeholder="instruction" style={{ width: "100%", marginTop: 6 }}
                    value={form.instruction ?? ""} onChange={(e) => setForm({ ...form, instruction: e.target.value })} />
                </>
              )}
              {opKind === "modify_manifest" && (
                <>
                  <input placeholder="xpath (.//activity[@android:name='.Foo'])" style={{ width: "100%", marginTop: 6 }}
                    value={form.xpath ?? ""} onChange={(e) => setForm({ ...form, xpath: e.target.value })} />
                  <input placeholder="attribute (exported)" style={{ width: "100%", marginTop: 6 }}
                    value={form.attribute ?? ""} onChange={(e) => setForm({ ...form, attribute: e.target.value })} />
                  <input placeholder="value (true)" style={{ width: "100%", marginTop: 6 }}
                    value={form.value ?? ""} onChange={(e) => setForm({ ...form, value: e.target.value })} />
                </>
              )}
              <button onClick={propose} style={{ marginTop: 6, width: "100%" }}>Proponer (solo diff)</button>
            </div>
          )}
        </section>

        {error && <p style={{ color: "var(--danger)", fontSize: 12 }}>{error}</p>}

        <section>
          <h4 style={{ margin: "4px 0", display: "flex", alignItems: "center", gap: 8 }}>
            Historial {pendingCount > 0 && <span className="pill pill-hypothesis">{pendingCount} pendiente{pendingCount === 1 ? "" : "s"}</span>}
          </h4>
          {pendingCount > 1 && (
            <button onClick={applyAllPending} disabled={bulkBusy} style={{ width: "100%", marginBottom: 6, fontSize: 12 }}>
              {bulkBusy ? "Aplicando..." : `Aplicar los ${pendingCount} pendientes`}
            </button>
          )}
          {bulkResult && <p style={{ fontSize: 11, color: "var(--text-dim)", margin: "0 0 6px" }}>{bulkResult}</p>}
          {mods.length === 0 && (
            <p style={{ fontSize: 12, color: "var(--text-dim)" }}>
              Todavía no hay cambios propuestos. Usa el cuadro de arriba para crear el primero.
            </p>
          )}
          {mods.map((m) => (
            <div
              key={m.id}
              onClick={() => setActiveId(m.id)}
              style={{
                padding: 8,
                cursor: "pointer",
                background: m.id === activeId ? "var(--bg-2)" : "transparent",
                borderBottom: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                fontSize: 12,
              }}
            >
              <div className="monospace">{m.file}</div>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
                <div style={{ color: "var(--text-dim)", display: "flex", gap: 6, alignItems: "center", flex: 1, minWidth: 0 }}>
                  {m.operation}
                  <span
                    className={`pill ${m.status === "APPLIED" ? "pill-confirmed" : m.status === "FAILED" ? "pill-hypothesis" : "pill-suggestion"}`}
                  >
                    {STATUS_LABELS[m.status] ?? m.status}
                  </span>
                </div>
                {m.status === "PENDING" && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      apply(m.id);
                    }}
                    style={{ padding: "2px 8px", fontSize: 11 }}
                  >
                    Aplicar
                  </button>
                )}
                {m.status === "APPLIED" && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      revert(m.id);
                    }}
                    title="Deja el archivo como estaba antes de este cambio específico (no afecta otros cambios ya aplicados en otros archivos; si hay un cambio más reciente sobre este mismo archivo, revierte primero ese)"
                    style={{ padding: "2px 8px", fontSize: 11 }}
                  >
                    Revertir
                  </button>
                )}
              </div>
            </div>
          ))}
        </section>
      </div>

      <div style={{ flex: 1 }}>
        {active ? (
          <DiffViewer
            modification={active}
            onApply={() => apply(active.id)}
            onRevert={() => revert(active.id)}
          />
        ) : (
          <div style={{ padding: 16, color: "var(--text-dim)", fontSize: 13 }}>
            Selecciona un cambio del historial para ver su diff, o describe uno nuevo a la izquierda.
          </div>
        )}
      </div>
    </div>
  );
}
