import type {
  AnalysisReport,
  AssistantAskResponse,
  AssistantEvent,
  AssistantFinding,
  AssistantMessage,
  ComparisonReport,
  GeneratorApk,
  JobStatus,
  Modification,
  Project,
  ToolStatusEntry,
  TreeNode,
} from "../types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    const body = await res.text();
    let detail: string | null = null;
    try {
      const parsed = JSON.parse(body);
      if (typeof parsed.detail === "string") detail = parsed.detail;
    } catch {
      // not JSON — fall through to the raw-body error below
    }
    throw new Error(detail ?? `${res.status} ${res.statusText}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  // --- Projects ---
  createProject: (name: string) =>
    request<Project>("/api/projects", { method: "POST", body: JSON.stringify({ name }) }),
  listProjects: () => request<Project[]>("/api/projects"),
  getProject: (id: string) => request<Project>(`/api/projects/${id}`),
  deleteProject: (id: string) => request<{ deleted: boolean }>(`/api/projects/${id}`, { method: "DELETE" }),
  getTree: (id: string, subdir = "decoded") =>
    request<TreeNode>(`/api/projects/${id}/tree?subdir=${subdir}`),
  readFile: (id: string, path: string, subdir = "decoded") =>
    request<{ path: string; content: string }>(
      `/api/projects/${id}/file?path=${encodeURIComponent(path)}&subdir=${subdir}`
    ),
  deleteTreeEntry: (id: string, path: string, subdir = "decoded") =>
    request<{ deleted: boolean }>(
      `/api/projects/${id}/tree?path=${encodeURIComponent(path)}&subdir=${subdir}`,
      { method: "DELETE" }
    ),
  renameTreeEntry: (id: string, path: string, newName: string, subdir = "decoded") =>
    request<{ renamed: boolean; name: string }>(`/api/projects/${id}/tree/rename`, {
      method: "POST",
      body: JSON.stringify({ path, new_name: newName, subdir }),
    }),
  copyTreeEntry: (id: string, sourcePath: string, destDir: string, subdir = "decoded") =>
    request<{ copied: boolean }>(`/api/projects/${id}/tree/copy`, {
      method: "POST",
      body: JSON.stringify({ source_path: sourcePath, dest_dir: destDir, subdir }),
    }),
  moveTreeEntry: (id: string, sourcePath: string, destDir: string, subdir = "decoded") =>
    request<{ moved: boolean }>(`/api/projects/${id}/tree/move`, {
      method: "POST",
      body: JSON.stringify({ source_path: sourcePath, dest_dir: destDir, subdir }),
    }),

  // --- Upload ---
  uploadApk: async (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE_URL}/api/projects/${id}/upload`, { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<{ project_id: string; metadata: unknown; decode_job_id: string }>;
  },

  // --- Analysis ---
  runAnalysis: (id: string) => request<{ job_id: string }>(`/api/projects/${id}/analysis/run`, { method: "POST" }),
  getAnalysis: (id: string) => request<AnalysisReport>(`/api/projects/${id}/analysis`),

  // --- Modifications ---
  proposeModification: (id: string, body: Record<string, unknown>) =>
    request<Modification>(`/api/projects/${id}/modifications`, { method: "POST", body: JSON.stringify(body) }),
  listModifications: (id: string) => request<Modification[]>(`/api/projects/${id}/modifications`),
  getModification: (id: string, modId: string) =>
    request<Modification>(`/api/projects/${id}/modifications/${modId}`),
  applyModification: (id: string, modId: string) =>
    request<Modification>(`/api/projects/${id}/modifications/${modId}/apply`, { method: "POST" }),
  revertModification: (id: string, modId: string) =>
    request<Modification>(`/api/projects/${id}/modifications/${modId}/revert`, { method: "POST" }),
  applyAllPending: (id: string) =>
    request<{ applied: string[]; failed: { id: string; file: string; error: string }[] }>(
      `/api/projects/${id}/modifications/apply-pending`,
      { method: "POST" }
    ),

  // --- AI ---
  aiPlan: (id: string, instruction: string) =>
    request<{ summary: string; proposed: unknown[]; errors: unknown[] }>(`/api/projects/${id}/ai/plan`, {
      method: "POST",
      body: JSON.stringify({ instruction }),
    }),

  // --- Build pipeline ---
  triggerBuild: (id: string) =>
    request<{ job_id: string }>(`/api/projects/${id}/build`, { method: "POST", body: JSON.stringify({}) }),
  getComparison: (id: string) => request<ComparisonReport>(`/api/projects/${id}/compare`),
  downloadUrl: (id: string) => `${BASE_URL}/api/projects/${id}/download`,

  // --- Jobs ---
  getJob: (jobId: string) => request<JobStatus>(`/api/jobs/${jobId}`),
  getLatestJob: (projectId: string, type: string) =>
    request<{ id: string; type: string; status: string; progress: number }>(
      `/api/projects/${projectId}/jobs/latest?type=${type}`
    ),

  // --- Devices ---
  checkDevices: () => request<{ job_id: string }>("/api/devices/check", { method: "POST" }),
  installOnDevice: (id: string, serial: string) =>
    request<{ job_id: string }>(`/api/projects/${id}/devices/${serial}/install`, { method: "POST" }),
  launchOnDevice: (id: string, serial: string) =>
    request<{ job_id: string }>(`/api/projects/${id}/devices/${serial}/launch`, { method: "POST" }),
  logcatFromDevice: (id: string, serial: string) =>
    request<{ job_id: string }>(`/api/projects/${id}/devices/${serial}/logcat`, { method: "POST" }),

  // --- Tooling ---
  checkTools: () => request<{ job_id: string }>("/api/settings/tools/check", { method: "POST" }),
  getToolStatus: () =>
    request<{ tools: ToolStatusEntry[]; checked_at: number | null }>("/api/settings/tools"),
  getServerInfo: () =>
    request<{
      ok: boolean;
      ip: string;
      country: string;
      country_code: string;
      region: string;
      city: string;
      isp: string;
    }>("/api/settings/server-info"),

  // --- App generator (builds a signed WebView-wrapper APK from a URL) ---
  listGeneratorApks: () => request<GeneratorApk[]>("/api/settings/generator-apks"),
  createGeneratorApk: async (name: string, url: string, color: string, icon: File) => {
    const form = new FormData();
    form.append("name", name);
    form.append("url", url);
    form.append("color", color);
    form.append("icon", icon);
    const res = await fetch(`${BASE_URL}/api/settings/generator-apks/create`, { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<{ slug: string; job_id: string }>;
  },
  importGeneratorApk: (slug: string, name?: string) =>
    request<{ project: Project; decode_job_id: string }>(`/api/settings/generator-apks/${slug}/import`, {
      method: "POST",
      body: JSON.stringify(name ? { name } : {}),
    }),
  generatorIconUrl: (slug: string) => `${BASE_URL}/api/settings/generator-apks/${slug}/icon`,
  generatorApkDownloadUrl: (slug: string) => `${BASE_URL}/api/settings/generator-apks/${slug}/download`,

  // --- Assistant (read-only copilot: see backend/app/assistant/) ---
  getAssistantAnalysis: (id: string) => request<AssistantFinding[]>(`/api/projects/${id}/assistant/analysis`),
  getAssistantEvents: (id: string) => request<AssistantEvent[]>(`/api/projects/${id}/assistant/events`),
  getAssistantMessages: (id: string) => request<AssistantMessage[]>(`/api/projects/${id}/assistant/messages`),
  assistantAsk: (id: string, question: string) =>
    request<AssistantAskResponse>(`/api/projects/${id}/assistant/ask`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
};

export { BASE_URL };
