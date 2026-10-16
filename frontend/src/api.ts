/** API client — all requests go to the FastAPI backend. */

export interface LogLineModel {
  line_number: number;
  text: string;
}

export interface FailureClusterModel {
  start_line: number;
  end_line: number;
  lines: LogLineModel[];
}

export interface RootCauseModel {
  line_number: number;
  text: string;
  category: string;
  priority_score: number;
  score_reasons: string[];
  explanation: string;
}

export interface RedactionStats {
  applied: boolean;
  replacement_count: number;
  matched_rules: string[];
}

export interface AnalysisResponse {
  status: string;
  source_name: string;
  total_lines: number;
  error_count: number;
  warning_count: number;
  failure_clusters: FailureClusterModel[];
  root_cause: RootCauseModel | null;
  primary_evidence: LogLineModel[];
  supporting_evidence: LogLineModel[];
  cascading_failures: LogLineModel[];
  relevant_context: LogLineModel[];
  debugging_suggestions: string[];
  redaction: RedactionStats | null;
  analysis_notes: string[];
}

export interface SampleInfo {
  id: string;
  name: string;
  description: string;
  filename: string;
}

const BASE = '';   // same-origin; Vite proxies /api in dev

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function fetchSamples(): Promise<SampleInfo[]> {
  const res = await fetch(`${BASE}/api/samples`);
  return handleResponse<SampleInfo[]>(res);
}

export async function analyzeDemo(sampleId: string): Promise<AnalysisResponse> {
  const res = await fetch(`${BASE}/api/demo/${encodeURIComponent(sampleId)}`);
  return handleResponse<AnalysisResponse>(res);
}

export async function analyzeUpload(file: File): Promise<AnalysisResponse> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/api/analyze`, { method: 'POST', body: form });
  return handleResponse<AnalysisResponse>(res);
}

export async function fetchHealth(): Promise<{ status: string }> {
  const res = await fetch(`${BASE}/health`);
  return handleResponse<{ status: string }>(res);
}
