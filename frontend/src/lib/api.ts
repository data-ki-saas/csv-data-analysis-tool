import { createClient } from "@/lib/supabase/client";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function authHeader(): Promise<HeadersInit> {
  const supabase = createClient();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (HTTP ${response.status})`);
  }
  return response.json();
}

export async function uploadDataset(file: File) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/api/datasets/upload`, {
    method: "POST",
    headers: await authHeader(),
    body: formData,
  });
  return handleResponse<UploadResponse>(response);
}

export async function listDatasets() {
  const response = await fetch(`${API_BASE_URL}/api/datasets`, {
    headers: await authHeader(),
  });
  return handleResponse<DatasetInfo[]>(response);
}

export async function queryDataset(datasetId: string, sql: string) {
  const response = await fetch(`${API_BASE_URL}/api/datasets/${datasetId}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeader()) },
    body: JSON.stringify({ sql }),
  });
  return handleResponse<QueryResponse>(response);
}

export interface ColumnInfo {
  name: string;
  type: string;
}

export interface DatasetInfo {
  dataset_id: string;
  filename: string;
  row_count: number;
  schema: ColumnInfo[];
}

export interface UploadResponse extends DatasetInfo {
  preview: { columns: string[]; rows: unknown[][] };
}

export interface QueryResponse {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
}
