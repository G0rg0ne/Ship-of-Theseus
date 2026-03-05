const getBaseUrl = () =>
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

function getHeaders(token?: string): HeadersInit {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = 'Bearer ' + token;
  return headers;
}

async function handleResponse<T>(res: Response): Promise<T> {
  const text = await res.text();
  let data: unknown = null;
  try { data = text ? JSON.parse(text) : null; } catch {}
  if (!res.ok) {
    const d = data as { detail?: string | string[] };
    const detail = typeof d?.detail === 'string' ? d.detail : d?.detail ? String(d.detail) : res.statusText;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

export interface UserResponse {
  id: string;
  username: string;
  email: string;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export async function register(username: string, email: string, password: string): Promise<void> {
  const res = await fetch(getBaseUrl() + '/api/auth/register', {
    method: 'POST', headers: getHeaders(), body: JSON.stringify({ username, email, password }),
  });
  await handleResponse(res);
}

export async function login(username: string, password: string): Promise<{ token: string; user: UserResponse }> {
  const res = await fetch(getBaseUrl() + '/api/auth/login', {
    method: 'POST', headers: getHeaders(), body: JSON.stringify({ username, password }),
  });
  const data = await handleResponse<TokenResponse>(res);
  const userRes = await fetch(getBaseUrl() + '/api/auth/me', { headers: getHeaders(data.access_token) });
  const user = await handleResponse<UserResponse>(userRes);
  return { token: data.access_token, user };
}

export async function getMe(token: string): Promise<UserResponse> {
  const res = await fetch(getBaseUrl() + '/api/auth/me', { headers: getHeaders(token) });
  return handleResponse<UserResponse>(res);
}

export async function verifyToken(token: string): Promise<boolean> {
  const res = await fetch(getBaseUrl() + '/api/auth/verify', { headers: getHeaders(token) });
  return res.ok;
}

export interface DocumentCurrent {
  filename?: string;
  chunk_count?: number;
  [key: string]: unknown;
}

export async function uploadPdf(file: File, token: string): Promise<DocumentCurrent> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(getBaseUrl() + "/api/documents/upload", {
    method: "POST", headers: { Authorization: "Bearer " + token }, body: form,
  });
  return handleResponse<DocumentCurrent>(res);
}

export async function getCurrentDocument(token: string): Promise<DocumentCurrent | null> {
  const res = await fetch(getBaseUrl() + "/api/documents/current", { headers: getHeaders(token) });
  if (res.status === 404) return null;
  return handleResponse<DocumentCurrent>(res);
}

export async function clearCurrentDocument(token: string): Promise<void> {
  const res = await fetch(getBaseUrl() + "/api/documents/current", {
    method: "DELETE", headers: getHeaders(token),
  });
  await handleResponse(res);
}

export interface ExtractionJobStarted { job_id: string; message?: string; }
export interface ExtractionJobStatus {
  job_id: string; status: string; total_chunks: number; completed_chunks: number;
  filename?: string; created_at?: string; error?: string;
}

export interface GraphNode { id: string; label: string; type: string; properties?: Record<string, unknown>; }
export interface GraphEdge { source: string; target: string; relation_type: string; properties?: Record<string, unknown>; }
export interface DocumentGraph {
  filename: string; nodes: GraphNode[]; edges: GraphEdge[];
  extracted_at: string; entity_count: number; relationship_count: number;
}

export async function startEntityExtraction(token: string): Promise<ExtractionJobStarted> {
  const res = await fetch(getBaseUrl() + "/api/entities/extract", {
    method: "POST", headers: getHeaders(token),
  });
  return handleResponse<ExtractionJobStarted>(res);
}

export async function getExtractionStatus(jobId: string, token: string): Promise<ExtractionJobStatus> {
  const res = await fetch(getBaseUrl() + "/api/entities/extract/status/" + jobId, { headers: getHeaders(token) });
  return handleResponse<ExtractionJobStatus>(res);
}

export async function getExtractionGraph(jobId: string, token: string): Promise<DocumentGraph | null> {
  const res = await fetch(getBaseUrl() + "/api/entities/extract/graph/" + jobId, { headers: getHeaders(token) });
  if (res.status === 202) return null;
  return handleResponse<DocumentGraph>(res);
}

export async function saveGraphToNeo4j(jobId: string, token: string): Promise<{ ok: boolean; document_name: string }> {
  const res = await fetch(getBaseUrl() + "/api/graph/save/" + jobId, {
    method: "POST", headers: getHeaders(token),
  });
  return handleResponse(res);
}

export interface DocumentListItem { document_name: string; node_count: number; edge_count: number; }
export async function listNeo4jDocuments(token: string): Promise<DocumentListItem[]> {
  const res = await fetch(getBaseUrl() + "/api/graph/list", { headers: getHeaders(token) });
  const data = await handleResponse<{ documents: DocumentListItem[] }>(res);
  return data.documents;
}

export async function getGraphFromNeo4j(documentName: string, token: string): Promise<DocumentGraph> {
  const res = await fetch(getBaseUrl() + "/api/graph/" + encodeURIComponent(documentName), { headers: getHeaders(token) });
  return handleResponse<DocumentGraph>(res);
}

export async function deleteGraphFromNeo4j(documentName: string, token: string): Promise<void> {
  const res = await fetch(getBaseUrl() + "/api/graph/" + encodeURIComponent(documentName), {
    method: "DELETE", headers: getHeaders(token),
  });
  await handleResponse(res);
}

export interface CommunityInfo {
  community_id: string; node_count: number; top_entities: string[]; keywords: string[]; document_sources: string[];
}
export interface UserBrain {
  user_id: string; document_count: number; total_nodes: number; total_edges: number;
  community_count: number; communities: CommunityInfo[]; last_updated: string; status: string;
}

export async function getUserBrain(token: string): Promise<UserBrain | null> {
  const res = await fetch(getBaseUrl() + "/api/community/brain", { headers: getHeaders(token) });
  if (res.status === 404) return null;
  return handleResponse<UserBrain>(res);
}

export async function triggerCommunityDetection(token: string): Promise<UserBrain> {
  const res = await fetch(getBaseUrl() + "/api/community/detect", {
    method: "POST", headers: getHeaders(token),
  });
  return handleResponse<UserBrain>(res);
}

export async function deleteUserBrain(token: string): Promise<void> {
  const res = await fetch(getBaseUrl() + "/api/community/brain", {
    method: "DELETE", headers: getHeaders(token),
  });
  await handleResponse(res);
}
