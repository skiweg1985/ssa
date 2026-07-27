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

export interface RetryInfo {
  state?: 'pending' | 'running' | null;
  attempt?: number | null;
  max_attempts: number;
  scheduled_at?: string | null;
  reason?: 'failed' | 'partial' | null;
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
  retry: RetryInfo;
}

// --- Auth ---
export interface LoginResponse {
  token: string;
  username: string;
  expires_at: string;
}

export interface SetupStatus {
  /** true, solange noch kein Admin-Konto existiert */
  setup_required: boolean;
  /** Vorschlagswert für das Formular */
  username: string;
  /** true, wenn der Server SSA_SETUP_TOKEN verlangt */
  token_required: boolean;
}

// --- NAS-Verbindungen ---

/**
 * SNMP-Zugang für die Systemmetriken (Temperatur, Platten, RAID, USV).
 *
 * SNMP ist der einzige von Synology öffentlich dokumentierte Weg zu diesen
 * Werten; die File-Station-API liefert sie nicht. Am NAS muss der Dienst unter
 * Systemsteuerung → Terminal & SNMP aktiviert sein.
 */
export interface SNMPSettings {
  enabled: boolean;
  version: '2c' | '3';
  port: number;
  // v2c
  community?: string;
  // v3
  v3_user?: string;
  v3_auth_protocol?: 'SHA' | 'MD5';
  v3_auth_key?: string;
  v3_priv_protocol?: 'AES' | 'DES';
  v3_priv_key?: string;
}

export interface NASConnectionPublic {
  id: number;
  name: string;
  host: string;
  port?: number | null;
  use_https: boolean;
  verify_ssl: boolean;
  username: string;
  // Nur der Zustand — Community und v3-Schlüssel gibt die API nie zurück
  snmp_enabled: boolean;
  snmp_version: string;
  snmp_port: number;
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
  // Bei Update: undefined = SNMP-Einstellungen unverändert lassen;
  // gesetzt, aber ohne Zugangsdaten = gespeicherte Zugangsdaten behalten
  snmp?: SNMPSettings;
}

// --- NAS-Systemmetriken ---
export interface NASVolumeMetrics {
  name: string;
  total_bytes: number;
  free_bytes: number;
  used_bytes: number;
  used_percent: number;
  readonly: boolean;
  share_count: number;
}

export interface NASCapacityMetrics {
  volumes: NASVolumeMetrics[];
  share_count: number;
  shares_without_write: number;
  virtual_mounts: number;
  response_seconds: number;
}

export interface NASDiskMetrics {
  name: string;
  model?: string | null;
  status: 'ok' | 'busy' | 'error' | 'unknown';
  status_label: string;
  temperature_celsius?: number | null;
}

export interface NASRaidMetrics {
  name: string;
  status: 'ok' | 'busy' | 'error' | 'unknown';
  status_label: string;
  total_bytes?: number | null;
  free_bytes?: number | null;
  used_percent?: number | null;
}

export interface NASHealthMetrics {
  system: {
    model_name?: string | null;
    dsm_version?: string | null;
    system_status?: string | null;
    power_status?: string | null;
    system_fan_status?: string | null;
    cpu_fan_status?: string | null;
    temperature_celsius?: number | null;
    upgrade_available?: boolean | null;
    cpu_percent?: number | null;
    memory_total_bytes?: number | null;
    memory_available_bytes?: number | null;
    memory_used_percent?: number | null;
  };
  disks: NASDiskMetrics[];
  raids: NASRaidMetrics[];
  ups?: {
    status?: string | null;
    battery_charge_percent?: number | null;
    load_percent?: number | null;
  } | null;
  response_seconds: number;
}

/** Jede Quelle trägt ihren eigenen Status — eine ausgefallene reißt die andere nicht mit */
export interface NASMetricsSource<T> {
  available: boolean;
  error?: string | null;
  data?: T | null;
}

export interface NASMetrics {
  connection_id: number;
  name: string;
  host: string;
  collected_at: string;
  cached: boolean;
  sources: {
    filestation?: NASMetricsSource<NASCapacityMetrics>;
    snmp?: NASMetricsSource<NASHealthMetrics>;
  };
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

export interface CancelResponse {
  scan_slug: string;
  message: string;
  /** Der Abbruch ist kooperativ - der Lauf endet erst beim nächsten Prüfpunkt */
  cancelling: boolean;
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
