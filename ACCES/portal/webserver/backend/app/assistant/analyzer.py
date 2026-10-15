"""ProjectAnalyzer — deterministic, LLM-free (plan §0/§3/§11/§12).

Every method here only reads through `ReadOnlyProjectContext`. No network
call, no subprocess, no LLM. This is intentionally cheap enough to run on
every poll of `GET /assistant/analysis` (e.g. to drive a UI warning badge)
without burning an API call.

Confidence rule, enforced by construction here (not just by convention):
a Finding about a possibly-missing class is always HYPOTHESIS (there are
several plausible explanations, see `_MISSING_CLASS_CAUSES`); a Finding
about a Job that actually failed is CONFIRMED_FACT (the stderr is a literal
fact); a Finding linking a recent Modification to that failure is always
phrased as "podría estar relacionada", never "causó" — see
`_RELATED_MODIFICATION_TEMPLATE`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.assistant.context import ReadOnlyProjectContext
from app.models.assistant import AssistantConfidence
from app.services import manifest_service

_MISSING_CLASS_CAUSES = (
    "El nombre de la clase no coincide con el declarado en el Manifest.",
    "El package no coincide.",
    "La clase todavía no existe en el árbol Smali analizado.",
    "La modificación que la crearía está incompleta o no se ha aplicado todavía.",
)

_COMPONENT_KINDS = ("activities", "services", "receivers", "providers")


@dataclass
class Finding:
    observation: str
    analysis: str
    possible_problem: str
    evidence: str
    suggestion: str
    confidence: str  # AssistantConfidence value
    related_modification_ids: list[str] = field(default_factory=list)


class ProjectAnalyzer:
    def __init__(self, context: ReadOnlyProjectContext) -> None:
        self._ctx = context

    def analyze(self) -> list[Finding]:
        findings: list[Finding] = []
        findings.extend(self._check_manifest_component_classes())
        findings.extend(self._check_last_failed_job())
        findings.extend(self._check_last_comparison())
        return findings

    # --- 1. Manifest component <-> Smali class correlation --------------
    def _check_manifest_component_classes(self) -> list[Finding]:
        manifest = self._ctx.get_manifest()
        if not manifest or not self._ctx.has_decoded_project():
            return []

        package = manifest.get("package", "")
        findings: list[Finding] = []
        modules = self._ctx.list_smali_modules()

        for kind in _COMPONENT_KINDS:
            for component in manifest.get(kind, []):
                name = component.get("name", "")
                if not name:
                    continue
                fqcn = manifest_service.resolve_activity_class(package, name)
                if self._ctx.class_exists(fqcn):
                    continue
                findings.append(
                    Finding(
                        observation=(
                            f"El AndroidManifest.xml declara un(a) {kind[:-1]} llamado "
                            f"'{name}' (resuelto a '{fqcn}')."
                        ),
                        analysis=(
                            "No se encontró un archivo .smali correspondiente a esa clase "
                            f"en ninguno de los módulos analizados ({', '.join(modules) or 'ninguno'})."
                        ),
                        possible_problem="\n".join(f"- {c}" for c in _MISSING_CLASS_CAUSES),
                        evidence=f"Manifest -> {fqcn}; Smali tree -> no encontrada",
                        suggestion=(
                            "Verifica el nombre completo de la clase y su package, y confirma "
                            "que la modificación que la crea (si la hay) se haya aplicado."
                        ),
                        confidence=AssistantConfidence.HYPOTHESIS.value,
                    )
                )
        return findings

    # --- 2. Most recent failed Job (build/decode/analyze) ---------------
    def _check_last_failed_job(self) -> list[Finding]:
        job = self._ctx.get_last_failed_job()
        if not job:
            return []

        log_tail = self._ctx.get_job_log_tail(job.id)
        related = [
            m.id
            for m in self._ctx.list_modifications(limit=5)
            if m.status == "APPLIED" and m.timestamp <= job.created_at
        ]

        return [
            Finding(
                observation=f"El Job {job.id} ({job.type}) terminó en estado FAILED.",
                analysis="Esto es un hecho confirmado: el proceso correspondiente devolvió un error.",
                possible_problem=log_tail or "(sin detalle de log disponible)",
                evidence=f"job:{job.id}",
                suggestion=(
                    "Revisa el mensaje de error anterior. Si coincide con un archivo tocado por una "
                    "modificación reciente, esa modificación podría estar relacionada (no se afirma "
                    "que la haya causado sin evidencia directa)."
                ),
                confidence=AssistantConfidence.CONFIRMED_FACT.value,
                related_modification_ids=related,
            )
        ]

    # --- 3. Last persisted comparison report -----------------------------
    def _check_last_comparison(self) -> list[Finding]:
        report = self._ctx.get_comparison_report()
        if not report or report.get("compatible", True):
            return []

        important = report.get("important_differences", [])
        return [
            Finding(
                observation="La última comparación original-vs-reconstruida encontró diferencias importantes.",
                analysis="Estos datos ya fueron calculados por el pipeline de build; no se recalculan aquí.",
                possible_problem="\n".join(f"- {d}" for d in important),
                evidence="reports/comparison.json",
                suggestion="Revisa cada diferencia listada antes de distribuir el APK reconstruido.",
                confidence=AssistantConfidence.CONFIRMED_FACT.value,
            )
        ]
