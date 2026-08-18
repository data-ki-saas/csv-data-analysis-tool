import { createClient } from "@/lib/supabase/client";
import type { ColorTheme, ThemeMode } from "@/lib/theme";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// Logged once per page load so a misconfigured/stale-baked NEXT_PUBLIC_API_BASE_URL
// (a build-time value on Vercel -- see CLAUDE.md) is visible in the browser console
// without having to dig through the Network tab first.
console.info(`[api] backend base URL: ${API_BASE_URL}`);

async function authHeader(): Promise<HeadersInit> {
  const supabase = createClient();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Thin wrapper around fetch() that distinguishes a network-level failure
 * (CORS block, DNS/connection failure, offline -- fetch() rejects) from a
 * valid HTTP error response (fetch() resolves fine; handleResponse below
 * deals with that). Without this, both looked identical to the user: a
 * generic "Failed to fetch" with no indication it was a deployment/CORS
 * problem rather than something wrong with their upload. */
async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch (err) {
    console.error(`[api] network error calling ${input} (backend base URL: ${API_BASE_URL})`, err);
    const detail = err instanceof Error ? err.message : String(err);
    throw new Error(
      `Could not reach the API at ${API_BASE_URL} -- this usually means a CORS or network ` +
        `configuration issue, not a problem with your file. (${detail})`
    );
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    console.error(`[api] request to ${response.url} failed: HTTP ${response.status}`, body);
    throw new Error(body.detail ?? `Request failed (HTTP ${response.status})`);
  }
  return response.json();
}

export async function uploadDataset(file: File) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await apiFetch(`${API_BASE_URL}/api/datasets/upload`, {
    method: "POST",
    headers: await authHeader(),
    body: formData,
  });
  return handleResponse<UploadResponse>(response);
}

export async function listDatasets() {
  const response = await apiFetch(`${API_BASE_URL}/api/datasets`, {
    headers: await authHeader(),
  });
  return handleResponse<DatasetInfo[]>(response);
}

export async function deleteDataset(datasetId: string) {
  const response = await apiFetch(`${API_BASE_URL}/api/datasets/${datasetId}`, {
    method: "DELETE",
    headers: await authHeader(),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (HTTP ${response.status})`);
  }
}

export async function queryDataset(datasetId: string, sql: string) {
  const response = await apiFetch(`${API_BASE_URL}/api/datasets/${datasetId}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeader()) },
    body: JSON.stringify({ sql }),
  });
  return handleResponse<QueryResponse>(response);
}

export type ColumnCategory = "datetime" | "continuous_numerical" | "categorical" | "free_text";
export type CategorySource = "rule" | "ai" | "user";

export interface ColumnInfo {
  name: string;
  type: string;
  alias: string;
  category: ColumnCategory;
  category_source: CategorySource;
  confidence: number;
  needs_review: boolean;
  rationale: string | null;
  null_count: number;
  null_percentage: number;
  distinct_count: number;
  health_score: number;
  conversion_warning: string | null;
}

export interface DatasetInfo {
  dataset_id: string;
  filename: string;
  name: string;
  description: string | null;
  notes: string | null;
  row_count: number;
  health_score: number;
  schema: ColumnInfo[];
}

export interface UploadResponse extends DatasetInfo {
  preview: { columns: string[]; rows: unknown[][] };
}

export interface UpdateDatasetInput {
  name?: string;
  description?: string;
  notes?: string;
}

export async function updateDataset(datasetId: string, input: UpdateDatasetInput) {
  const response = await apiFetch(`${API_BASE_URL}/api/datasets/${datasetId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...(await authHeader()) },
    body: JSON.stringify(input),
  });
  return handleResponse<DatasetInfo>(response);
}

export interface DatasetSchema {
  dataset_id: string;
  filename: string;
  name: string;
  description: string | null;
  notes: string | null;
  row_count: number;
  created_at: string;
  health_score: number;
  columns: ColumnInfo[];
  preview: { columns: string[]; rows: unknown[][] };
  has_report_strategy: boolean;
}

export async function getDatasetSchema(datasetId: string) {
  const response = await apiFetch(`${API_BASE_URL}/api/datasets/${datasetId}/schema`, {
    headers: await authHeader(),
  });
  return handleResponse<DatasetSchema>(response);
}

export async function reviewColumnTypes(datasetId: string, columns?: string[]) {
  const response = await apiFetch(`${API_BASE_URL}/api/datasets/${datasetId}/schema/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeader()) },
    body: JSON.stringify({ columns: columns ?? null }),
  });
  return handleResponse<DatasetSchema>(response);
}

export interface UpdateColumnInput {
  category?: ColumnCategory;
  alias?: string;
}

export async function updateColumn(datasetId: string, column: string, update: UpdateColumnInput) {
  const response = await apiFetch(
    `${API_BASE_URL}/api/datasets/${datasetId}/schema/columns/${encodeURIComponent(column)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...(await authHeader()) },
      body: JSON.stringify(update),
    }
  );
  return handleResponse<DatasetSchema>(response);
}

export interface QueryResponse {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
}

export type PartitionType = "datetime" | "numerical_bins" | "categorical";
export type ChartType = "line" | "bar" | "pie" | "histogram" | "bell_curve";

export interface ChartRecommendation {
  id: string;
  source: "auto" | "custom";
  column: string;
  partition_type: PartitionType;
  chart_type: ChartType;
  title: string;
  rationale: string;
  sql: string;
  result: QueryResponse | null;
  error: string | null;
}

export interface ReportStrategy {
  dataset_id: string;
  filename: string;
  recommendations: ChartRecommendation[];
}

export async function generateReportStrategy(datasetId: string, force = false) {
  const response = await apiFetch(`${API_BASE_URL}/api/datasets/${datasetId}/report-strategy`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeader()) },
    body: JSON.stringify({ force }),
  });
  return handleResponse<ReportStrategy>(response);
}

export async function addCustomChart(datasetId: string, prompt: string) {
  const response = await apiFetch(`${API_BASE_URL}/api/datasets/${datasetId}/report-strategy/custom`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeader()) },
    body: JSON.stringify({ prompt }),
  });
  return handleResponse<ChartRecommendation>(response);
}

export async function deleteChart(datasetId: string, chartId: string) {
  const response = await apiFetch(
    `${API_BASE_URL}/api/datasets/${datasetId}/report-strategy/${encodeURIComponent(chartId)}`,
    { method: "DELETE", headers: await authHeader() }
  );
  return handleResponse<ReportStrategy>(response);
}

export interface UpdateChartInput {
  title?: string;
  rationale?: string;
}

export async function updateChart(datasetId: string, chartId: string, input: UpdateChartInput) {
  const response = await apiFetch(
    `${API_BASE_URL}/api/datasets/${datasetId}/report-strategy/${encodeURIComponent(chartId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...(await authHeader()) },
      body: JSON.stringify(input),
    }
  );
  return handleResponse<ChartRecommendation>(response);
}

export async function reorderCharts(datasetId: string, chartIds: string[]) {
  const response = await apiFetch(`${API_BASE_URL}/api/datasets/${datasetId}/report-strategy/order`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...(await authHeader()) },
    body: JSON.stringify({ chart_ids: chartIds }),
  });
  return handleResponse<ReportStrategy>(response);
}

export interface GenerateInsightsInput {
  title: string;
  chart_type: ChartType;
  partition_type: PartitionType;
  column: string;
  result: QueryResponse;
  // Unused by generateInsights() itself -- only relevant when this same
  // shape is reused for createChartShare() below, which snapshots it.
  rationale?: string;
}

export async function generateInsights(datasetId: string, input: GenerateInsightsInput) {
  const response = await apiFetch(`${API_BASE_URL}/api/datasets/${datasetId}/insights`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeader()) },
    body: JSON.stringify(input),
  });
  return handleResponse<{ insights: string[] }>(response);
}

export interface HeaderPreset {
  id: string;
  title: string;
  logo: string | null;
  enabled: boolean;
}

export interface FooterPreset {
  id: string;
  html: string;
  enabled: boolean;
}

export interface ChartShare {
  token: string;
  title: string;
  rationale: string;
  chart_type: ChartType;
  partition_type: PartitionType;
  column: string;
  result: QueryResponse;
  created_at: string;
  header_snapshot: HeaderPreset | null;
  footer_snapshot: FooterPreset | null;
  dataset_name: string | null;
  dataset_description: string | null;
}

// Reuses GenerateInsightsInput's shape -- the backend's create-share request
// body is literally the same {title, chart_type, partition_type, column,
// result} the insights endpoint already takes.
export async function createChartShare(datasetId: string, input: GenerateInsightsInput) {
  const response = await apiFetch(`${API_BASE_URL}/api/datasets/${datasetId}/shares`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeader()) },
    body: JSON.stringify(input),
  });
  return handleResponse<ChartShare>(response);
}

export async function revokeChartShare(datasetId: string, token: string) {
  const response = await apiFetch(
    `${API_BASE_URL}/api/datasets/${datasetId}/shares/${encodeURIComponent(token)}`,
    { method: "DELETE", headers: await authHeader() }
  );
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (HTTP ${response.status})`);
  }
}

// Public route -- no auth required, but attaching whatever session header
// exists anyway is harmless (the backend route never checks it) and keeps
// this call consistent with every other one in this file.
export async function getPublicChartShare(token: string) {
  const response = await apiFetch(`${API_BASE_URL}/api/shares/${encodeURIComponent(token)}`, {
    headers: await authHeader(),
  });
  return handleResponse<ChartShare>(response);
}

// Server-safe variant for Server Components / route handlers (share page's
// generateMetadata, opengraph-image) -- authHeader() calls createClient()
// from lib/supabase/client.ts, the *browser* Supabase client, which isn't
// usable outside a browser context. The share route ignores auth anyway (see
// above), so this just skips that call and swallows failures into `null`
// rather than throwing, since a broken/revoked link should still render a
// fallback OG preview instead of a failed page render.
export async function getPublicChartShareServer(token: string): Promise<ChartShare | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/shares/${encodeURIComponent(token)}`);
    if (!response.ok) return null;
    return (await response.json()) as ChartShare;
  } catch {
    return null;
  }
}

export interface ChartBlock {
  type: "chart";
  id: string;
  title: string;
  chart_type: ChartType;
  partition_type: PartitionType;
  column: string;
  result: QueryResponse;
}

export interface InsightsBlock {
  type: "insights";
  id: string;
  chart_title: string;
  bullets: string[];
}

export interface TextBlock {
  type: "text";
  id: string;
  text: string;
}

export type PresentationBlock = ChartBlock | InsightsBlock | TextBlock;

export interface PresentationPageData {
  id: string;
  title: string;
  blocks: PresentationBlock[];
}

export interface Presentation {
  dataset_id: string;
  title: string;
  pages: PresentationPageData[];
  updated_at: string | null;
}

export async function getPresentation(datasetId: string) {
  const response = await apiFetch(`${API_BASE_URL}/api/datasets/${datasetId}/presentation`, {
    headers: await authHeader(),
  });
  return handleResponse<Presentation>(response);
}

export async function updatePresentation(
  datasetId: string,
  input: { title: string; pages: PresentationPageData[] }
) {
  const response = await apiFetch(`${API_BASE_URL}/api/datasets/${datasetId}/presentation`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...(await authHeader()) },
    body: JSON.stringify(input),
  });
  return handleResponse<Presentation>(response);
}

export async function pinBlock(
  datasetId: string,
  input: { chart: Omit<ChartBlock, "type">; insights?: string[] | null }
) {
  const response = await apiFetch(`${API_BASE_URL}/api/datasets/${datasetId}/presentation/pin`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeader()) },
    body: JSON.stringify(input),
  });
  return handleResponse<Presentation>(response);
}

export interface UserSettings {
  theme_mode: ThemeMode;
  color_theme: ColorTheme;
  header_presets: HeaderPreset[];
  footer_presets: FooterPreset[];
}

export async function getSettings() {
  const response = await apiFetch(`${API_BASE_URL}/api/settings`, {
    headers: await authHeader(),
  });
  return handleResponse<UserSettings>(response);
}

export async function updateSettings(input: { theme_mode: ThemeMode; color_theme: ColorTheme }) {
  const response = await apiFetch(`${API_BASE_URL}/api/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...(await authHeader()) },
    body: JSON.stringify(input),
  });
  return handleResponse<UserSettings>(response);
}

export async function updateHeaderPresets(presets: HeaderPreset[]) {
  const response = await apiFetch(`${API_BASE_URL}/api/settings/header-presets`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...(await authHeader()) },
    body: JSON.stringify({ presets }),
  });
  return handleResponse<UserSettings>(response);
}

export async function updateFooterPresets(presets: FooterPreset[]) {
  const response = await apiFetch(`${API_BASE_URL}/api/settings/footer-presets`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...(await authHeader()) },
    body: JSON.stringify({ presets }),
  });
  return handleResponse<UserSettings>(response);
}
