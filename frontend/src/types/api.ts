// TypeScript interfaces matching the backend Pydantic models

export interface NASConfigPublic {
  host: string;
  username: string;
  port?: number;
  use_https: boolean;
  verify_ssl: boolean;
}

export interface TotalSize {
  bytes: number;
  formatted: number;
  unit: string;
}

export interface ScanResultItem {
  folder_name: string;
  success: boolean;
  num_dir?: number;
  num_file?: number;
  total_size?: TotalSize;
  elapsed_time_ms?: number;
  error?: string;
}

export interface ScanResult {
  scan_slug: string;
  scan_name: string;
  timestamp: string; // ISO 8601 datetime string
  status: 'running' | 'completed' | 'failed';
  results: ScanResultItem[];
  error?: string;
}

export interface ScanStatus {
  scan_slug: string;
  scan_name: string;
  status: 'running' | 'completed' | 'failed' | 'pending';
  last_run?: string; // ISO 8601 datetime string
  next_run?: string; // ISO 8601 datetime string
  enabled: boolean;
  shares?: string[];
  folders?: string[];
  paths?: string[];
  nas?: NASConfigPublic;
  interval?: string;
  nas_connection_id?: number;
}

// --- Auth ---
export interface LoginResponse {
  token: string;
  username: string;
  expires_at: string;
}

// --- NAS-Verbindungen ---
export interface NASConnectionPublic {
  id: number;
  name: string;
  host: string;
  port?: number | null;
  use_https: boolean;
  verify_ssl: boolean;
  username: string;
  job_count: number;
  created_at: string;
  updated_at: string;
}

export interface NASConnectionPayload {
  name: string;
  host: string;
  username: string;
  // Bei Update: leer/undefined = gespeichertes Passwort behalten
  password?: string;
  port?: number | null;
  use_https: boolean;
  verify_ssl: boolean;
}

export interface TestConnectionResponse {
  success: boolean;
  message: string;
}

export interface BrowseEntry {
  name: string;
  path: string;
  is_dir: boolean;
}

export interface BrowseResponse {
  path?: string | null;
  entries: BrowseEntry[];
}

// --- API-Tokens (Monitoring) ---
export interface ApiTokenPublic {
  id: number;
  name: string;
  created_at: string;
  last_used_at?: string | null;
}

export interface ApiTokenCreated extends ApiTokenPublic {
  // Klartext-Token: nur einmalig in der Erstellungs-Response enthalten
  token: string;
}

// --- Scan-Jobs (Verwaltung) ---
export interface ScanJobPayload {
  name: string;
  nas_connection_id: number;
  interval: string;
  enabled: boolean;
  paths?: string[] | null;
  shares?: string[] | null;
  folders?: string[] | null;
}

export interface ScanJobPublic extends ScanJobPayload {
  slug: string;
  created_at: string;
  updated_at: string;
}

export interface ScanListResponse {
  scans: ScanStatus[];
}

export interface TriggerResponse {
  scan_slug: string;
  message: string;
  triggered: boolean;
}

export interface ScanHistoryResponse {
  scan_slug: string;
  results: ScanResult[];
  total_count: number;
}

export interface ScanProgress {
  scan_slug?: string;
  scan_name?: string;
  status: 'running' | 'completed';
  progress: {
    num_dir: number;
    num_file: number;
    total_size: number; // Bytes as number, not TotalSize object
    waited: number;
    finished: boolean;
    current_path?: string;
    progress_percent?: number | null; // Prozentwert basierend auf historischem Scan (0-100) oder null wenn keine Historie vorhanden
  };
}

export interface StorageStats {
  scan_count: number;
  nas_count: number;
  folder_count: number;
  total_results_db: number;
  db_size_mb: number;
  db_path: string;
  oldest_entry?: string;
  newest_entry?: string;
  auto_cleanup_enabled: boolean;
  auto_cleanup_days: number;
}

export interface Folder {
  nas_host: string;
  folder_path: string;
}

export interface FoldersResponse {
  folders: Folder[];
  count: number;
}

export interface CleanupPreview {
  total_results: number;
  results_to_delete: number;
  results_to_keep: number;
  oldest_to_delete?: string;
  newest_to_keep?: string;
}

export interface CleanupResponse {
  success: boolean;
  message: string;
  stats?: CleanupPreview;
}

export interface ConfigReloadResponse {
  success: boolean;
  message: string;
  added_scans?: string[];
  updated_scans?: string[];
  removed_scans?: string[];
  total_scans?: number;
}
