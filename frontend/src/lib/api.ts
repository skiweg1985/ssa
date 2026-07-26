// Central API layer - 1:1 mapping to backend endpoints
import type {
  ScanListResponse,
  ScanStatus,
  ScanResult,
  ScanHistoryResponse,
  ScanProgress,
  TriggerResponse,
  CancelResponse,
  ConfigReloadResponse,
  StorageStats,
  FoldersResponse,
  CleanupPreview,
  CleanupResponse,
  LoginResponse,
  NASConnectionPublic,
  NASConnectionPayload,
  NASMetrics,
  TestConnectionResponse,
  BrowseResponse,
  ScanJobPayload,
  ScanJobPublic,
  ApiTokenPublic,
  ApiTokenCreated,
  SetupStatus,
} from "@/types/api";

const API_BASE = '/api';

// --- Auth token handling (localStorage) ---
const TOKEN_KEY = 'syno-space-analyzer-auth-token';

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // localStorage nicht verfügbar - Session gilt nur für diesen Tab
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    // ignore
  }
}

/** Fehler einer API-Antwort - traegt den HTTP-Status typisiert mit */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const token = getToken();
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  });

  if (!response.ok) {
    // Bei abgelaufener/ungültiger Sitzung global ausloggen (außer beim Login selbst)
    if (response.status === 401 && !endpoint.startsWith('/auth/login')) {
      clearToken();
      window.dispatchEvent(new Event('ssa:unauthorized'));
    }
    let detail = '';
    try {
      const body = await response.json();
      if (body && typeof body.detail === 'string') detail = body.detail;
    } catch {
      // Response ohne JSON-Body
    }
    throw new ApiError(
      detail || `HTTP error! status: ${response.status}`,
      response.status
    );
  }

  // 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

// --- Auth endpoints ---
export async function login(username: string, password: string): Promise<LoginResponse> {
  return fetchAPI<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

export async function fetchMe(): Promise<{ username: string }> {
  return fetchAPI<{ username: string }>('/auth/me');
}

/** Ersteinrichtung noch offen? Wird beim Boot vor dem Login-Bildschirm geprueft. */
export async function fetchSetupStatus(): Promise<SetupStatus> {
  return fetchAPI<SetupStatus>('/auth/setup-status');
}

/** Legt das Admin-Konto an und meldet direkt an (funktioniert genau einmal) */
export async function setupAdmin(
  username: string,
  password: string,
  setupToken?: string
): Promise<LoginResponse> {
  return fetchAPI<LoginResponse>('/auth/setup', {
    method: 'POST',
    body: JSON.stringify({
      username,
      password,
      ...(setupToken ? { setup_token: setupToken } : {}),
    }),
  });
}

// --- NAS connection endpoints ---
export async function fetchNasConnections(): Promise<NASConnectionPublic[]> {
  return fetchAPI<NASConnectionPublic[]>('/nas-connections');
}

export async function createNasConnection(payload: NASConnectionPayload): Promise<NASConnectionPublic> {
  return fetchAPI<NASConnectionPublic>('/nas-connections', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function updateNasConnection(id: number, payload: NASConnectionPayload): Promise<NASConnectionPublic> {
  return fetchAPI<NASConnectionPublic>(`/nas-connections/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function deleteNasConnection(id: number): Promise<void> {
  return fetchAPI<void>(`/nas-connections/${id}`, { method: 'DELETE' });
}

export async function testNasConnection(payload: Partial<NASConnectionPayload> & { id?: number }): Promise<TestConnectionResponse> {
  return fetchAPI<TestConnectionResponse>('/nas-connections/test', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function browseNas(id: number, path?: string): Promise<BrowseResponse> {
  return fetchAPI<BrowseResponse>(`/nas-connections/${id}/browse`, {
    method: 'POST',
    body: JSON.stringify({ path: path ?? null }),
  });
}

// --- NAS metrics endpoints ---

/** Metriken aller NAS-Systeme; `groups` schränkt auf 'capacity' und/oder 'health' ein */
export async function fetchNasMetrics(params?: {
  connectionId?: number;
  groups?: Array<'capacity' | 'health'>;
}): Promise<NASMetrics[]> {
  const query = new URLSearchParams();
  if (params?.connectionId !== undefined) query.set('connection_id', String(params.connectionId));
  if (params?.groups?.length) query.set('groups', params.groups.join(','));
  const suffix = query.toString() ? `?${query}` : '';
  return fetchAPI<NASMetrics[]>(`/nas-metrics${suffix}`);
}

/** Metriken eines Systems — `identifier` ist die ID oder der Verbindungsname */
export async function fetchNasMetricsFor(
  identifier: number | string,
  groups?: Array<'capacity' | 'health'>,
): Promise<NASMetrics> {
  const suffix = groups?.length ? `?groups=${groups.join(',')}` : '';
  return fetchAPI<NASMetrics>(`/nas-metrics/${encodeURIComponent(String(identifier))}${suffix}`);
}

// --- API token endpoints (Monitoring) ---
export async function fetchApiTokens(): Promise<ApiTokenPublic[]> {
  return fetchAPI<ApiTokenPublic[]>('/api-tokens');
}

export async function createApiToken(name: string): Promise<ApiTokenCreated> {
  return fetchAPI<ApiTokenCreated>('/api-tokens', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export async function deleteApiToken(id: number): Promise<void> {
  return fetchAPI<void>(`/api-tokens/${id}`, { method: 'DELETE' });
}

// --- Scan job endpoints ---
export async function createScanJob(payload: ScanJobPayload): Promise<ScanJobPublic> {
  return fetchAPI<ScanJobPublic>('/scan-jobs', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function updateScanJob(slug: string, payload: ScanJobPayload): Promise<ScanJobPublic> {
  return fetchAPI<ScanJobPublic>(`/scan-jobs/${slug}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function deleteScanJob(slug: string, deleteHistory: boolean = false): Promise<void> {
  return fetchAPI<void>(`/scan-jobs/${slug}?delete_history=${deleteHistory}`, {
    method: 'DELETE',
  });
}

// Scan endpoints
export async function fetchScans(): Promise<ScanListResponse> {
  return fetchAPI<ScanListResponse>('/scans');
}

export async function fetchScan(scanName: string): Promise<ScanStatus> {
  return fetchAPI<ScanStatus>(`/scans/${scanName}`);
}

export async function fetchScanResults(scanName: string, latest: boolean = true): Promise<ScanResult> {
  return fetchAPI<ScanResult>(`/scans/${scanName}/results?latest=${latest}`);
}

export async function fetchScanHistory(scanName: string): Promise<ScanHistoryResponse> {
  return fetchAPI<ScanHistoryResponse>(`/scans/${scanName}/history`);
}

export async function fetchScanProgress(scanName: string): Promise<ScanProgress> {
  return fetchAPI<ScanProgress>(`/scans/${scanName}/progress`);
}

export async function triggerScan(scanName: string): Promise<TriggerResponse> {
  return fetchAPI<TriggerResponse>(`/scans/${scanName}/trigger`, {
    method: 'POST',
  });
}

export async function cancelScan(scanSlug: string): Promise<CancelResponse> {
  return fetchAPI<CancelResponse>(`/scans/${scanSlug}/cancel`, {
    method: 'POST',
  });
}

// Config endpoints
export async function reloadConfig(): Promise<ConfigReloadResponse> {
  return fetchAPI<ConfigReloadResponse>('/config/reload', {
    method: 'POST',
  });
}

// Storage endpoints
export async function fetchStorageStats(): Promise<StorageStats> {
  return fetchAPI<StorageStats>('/storage/stats');
}

export async function fetchFolders(params?: { nas_host?: string; scan_name?: string }): Promise<FoldersResponse> {
  const queryParams = new URLSearchParams();
  if (params?.nas_host) queryParams.append('nas_host', params.nas_host);
  if (params?.scan_name) queryParams.append('scan_name', params.scan_name);
  
  const query = queryParams.toString();
  return fetchAPI<FoldersResponse>(`/storage/folders${query ? `?${query}` : ''}`);
}

export async function previewCleanup(params: {
  days?: number;
  nas_host?: string;
  folder_path?: string;
  scan_name?: string;
}): Promise<CleanupPreview> {
  const queryParams = new URLSearchParams();
  if (params.days !== undefined) queryParams.append('days', params.days.toString());
  if (params.nas_host) queryParams.append('nas_host', params.nas_host);
  if (params.folder_path) queryParams.append('folder_path', params.folder_path);
  if (params.scan_name) queryParams.append('scan_name', params.scan_name);
  
  const query = queryParams.toString();
  return fetchAPI<CleanupPreview>(`/storage/cleanup-preview${query ? `?${query}` : ''}`);
}

export async function executeCleanup(params: {
  days?: number;
  nas_host?: string;
  folder_path?: string;
  scan_name?: string;
}): Promise<CleanupResponse> {
  const queryParams = new URLSearchParams();
  if (params.days !== undefined) queryParams.append('days', params.days.toString());
  if (params.nas_host) queryParams.append('nas_host', params.nas_host);
  if (params.folder_path) queryParams.append('folder_path', params.folder_path);
  if (params.scan_name) queryParams.append('scan_name', params.scan_name);
  
  const query = queryParams.toString();
  return fetchAPI<CleanupResponse>(`/storage/cleanup${query ? `?${query}` : ''}`, {
    method: 'POST',
  });
}

export async function deleteFolderResults(params: {
  nas_host?: string;
  folder_path?: string;
  scan_name?: string;
}): Promise<{ success: boolean; message: string; deleted_count: number }> {
  const queryParams = new URLSearchParams();
  if (params.nas_host) queryParams.append('nas_host', params.nas_host);
  if (params.folder_path) queryParams.append('folder_path', params.folder_path);
  if (params.scan_name) queryParams.append('scan_name', params.scan_name);
  
  const query = queryParams.toString();
  return fetchAPI(`/storage/folders${query ? `?${query}` : ''}`, {
    method: 'DELETE',
  });
}

export async function deleteScanResults(scanName: string): Promise<{ success: boolean; message: string }> {
  return fetchAPI(`/storage/scans/${scanName}`, {
    method: 'DELETE',
  });
}

export async function deleteAllResults(): Promise<{ success: boolean; message: string }> {
  return fetchAPI('/storage/all', {
    method: 'DELETE',
  });
}
