// Central API layer - 1:1 mapping to backend endpoints
import type {
  ScanListResponse,
  ScanStatus,
  ScanResult,
  ScanHistoryResponse,
  ScanProgress,
  TriggerResponse,
  ConfigReloadResponse,
  StorageStats,
  FoldersResponse,
  CleanupPreview,
  CleanupResponse,
} from "@/types/api";

const API_BASE = '/api';

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = new Error(`HTTP error! status: ${response.status}`);
    (error as any).status = response.status;
    throw error;
  }

  return response.json();
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
