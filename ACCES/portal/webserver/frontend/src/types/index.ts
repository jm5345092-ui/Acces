export interface Project {
  id: string;
  name: string;
  created_at: string;
  original_filename: string;
  sha256: string;
  sha1: string;
  size_bytes: number;
  package_name: string;
  version_code: string;
  version_name: string;
  min_sdk: string;
  target_sdk: string;
  status: string;
}

export interface GeneratorApk {
  slug: string;
  name: string;
  package: string;
  color: string;
  has_icon: boolean;
  size_bytes: number;
  built_at: number;
}

export interface TreeNode {
  name: string;
  path: string;
  type: "file" | "directory";
  children?: TreeNode[];
}

export interface Modification {
  id: string;
  project_id: string;
  timestamp: string;
  file: string;
  operation: string;
  description: string;
  before_hash: string;
  after_hash: string;
  before_content: string;
  after_content: string;
  is_binary: boolean;
  status: "PENDING" | "APPLIED" | "REVERTED" | "FAILED";
  diff?: string;
}

export interface JobStatus {
  id: string;
  project_id: string | null;
  type: string;
  status: "QUEUED" | "RUNNING" | "SUCCESS" | "FAILED";
  progress: number;
  result: Record<string, unknown>;
}

export interface AnalysisReport {
  manifest: {
    package: string;
    version_code: string;
    version_name: string;
    min_sdk: string;
    target_sdk: string;
    compile_sdk?: string;
    apktool_version?: string;
    activities: { name: string; exported: string }[];
    services: { name: string; exported: string }[];
    receivers: { name: string; exported: string }[];
    providers: { name: string; exported: string }[];
    permissions: string[];
  };
  dex: {
    per_dex: Record<string, { classes: number; methods: number }>;
    total_classes: number;
    total_methods: number;
    packages: string[];
    package_count: number;
  };
  resources: { count: number; by_type: Record<string, number> };
  assets: { count: number; files: string[] };
  native_libs: string[];
  certificate: string;
  entry_point: {
    application_class: string;
    application_smali_path: string;
    application_smali_line: number | null;
    main_activity: string;
    main_activity_class: string;
    main_activity_smali_path: string;
    main_activity_smali_line: number | null;
  };
}

export interface ComparisonReport {
  expected_differences: string[];
  important_differences: string[];
  summary: Record<string, unknown>;
  compatible: boolean;
}

export interface ToolStatusEntry {
  name: string;
  ok: boolean;
  version: string;
  path: string | null;
}

export type AssistantConfidence = "CONFIRMED_FACT" | "HYPOTHESIS" | "SUGGESTION" | "USER_ACTION" | "";

export interface AssistantFinding {
  observation: string;
  analysis: string;
  possible_problem: string;
  evidence: string;
  suggestion: string;
  confidence: AssistantConfidence;
}

export interface AssistantEvent {
  id: string;
  project_id: string;
  kind: string;
  source: string;
  confidence: AssistantConfidence;
  summary: string;
  detail_json: string;
  timestamp: string;
}

export interface AssistantMessage {
  id: string;
  project_id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export interface AssistantAskResponse {
  message: string;
  mode: "finding" | "teaching" | "general";
  findings: AssistantFinding[];
  events: AssistantEvent[];
}
