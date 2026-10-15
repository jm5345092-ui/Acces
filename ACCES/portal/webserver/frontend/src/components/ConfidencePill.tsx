import type { AssistantConfidence } from "../types";

const LABELS: Record<string, string> = {
  CONFIRMED_FACT: "Hecho confirmado",
  HYPOTHESIS: "Hipótesis",
  SUGGESTION: "Sugerencia",
  USER_ACTION: "Acción del usuario",
};

const CLASSES: Record<string, string> = {
  CONFIRMED_FACT: "pill-confirmed",
  HYPOTHESIS: "pill-hypothesis",
  SUGGESTION: "pill-suggestion",
  USER_ACTION: "pill-user",
};

export default function ConfidencePill({ confidence }: { confidence: AssistantConfidence }) {
  if (!confidence) return null;
  return <span className={`pill ${CLASSES[confidence] ?? "pill-suggestion"}`}>{LABELS[confidence] ?? confidence}</span>;
}
