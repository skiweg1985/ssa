import { ScanStatus } from "@/types/api";

// Date formatting utilities
export function formatDate(dateString: string | undefined): string {
  if (!dateString) return 'N/A';
  const date = new Date(dateString);
  return date.toLocaleString('de-DE', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
}

export function formatDateShort(dateString: string | undefined): string {
  if (!dateString) return '-';
  const date = new Date(dateString);
  return date.toLocaleString('de-DE', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
}

// Relative time formatting (e.g., "vor 2 Minuten" or "in 2 Minuten")
export function formatRelativeTime(dateString: string | undefined): string {
  if (!dateString) return '-';
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = date.getTime() - now.getTime(); // Positive = future, negative = past
  const absDiffMs = Math.abs(diffMs);
  const absDiffSecs = Math.floor(absDiffMs / 1000);
  const absDiffMins = Math.floor(absDiffSecs / 60);
  const absDiffHours = Math.floor(absDiffMins / 60);
  const absDiffDays = Math.floor(absDiffHours / 24);

  // Future dates
  if (diffMs > 0) {
    if (absDiffSecs < 60) return 'in Kürze';
    if (absDiffMins < 60) return `in ${absDiffMins} ${absDiffMins === 1 ? 'Minute' : 'Minuten'}`;
    if (absDiffHours < 24) return `in ${absDiffHours} ${absDiffHours === 1 ? 'Stunde' : 'Stunden'}`;
    if (absDiffDays < 7) return `in ${absDiffDays} ${absDiffDays === 1 ? 'Tag' : 'Tagen'}`;
    // Fallback to short date format for dates far in the future
    return formatDateShort(dateString);
  }
  
  // Past dates
  if (absDiffSecs < 60) return 'gerade eben';
  if (absDiffMins < 60) return `vor ${absDiffMins} ${absDiffMins === 1 ? 'Minute' : 'Minuten'}`;
  if (absDiffHours < 24) return `vor ${absDiffHours} ${absDiffHours === 1 ? 'Stunde' : 'Stunden'}`;
  if (absDiffDays < 7) return `vor ${absDiffDays} ${absDiffDays === 1 ? 'Tag' : 'Tagen'}`;
  
  // Fallback to short date format for older dates
  return formatDateShort(dateString);
}

export function formatRetryStatus(scan: ScanStatus): string | null {
  const retry = scan.retry;
  if (!retry?.state || !retry.attempt) return null;

  const prefix = `Wiederholung ${retry.attempt}/${retry.max_attempts}`;
  if (retry.state === 'running') return `${prefix} läuft`;
  if (retry.scheduled_at) return `${prefix} ${formatRelativeTime(retry.scheduled_at)}`;
  return `${prefix} geplant`;
}

// Format time ago for last updated
export function formatTimeAgo(date: Date | null): string {
  if (!date) return '';
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  
  if (diffSecs < 5) return 'gerade eben';
  if (diffSecs < 60) return `vor ${diffSecs} Sekunden`;
  
  const diffMins = Math.floor(diffSecs / 60);
  if (diffMins < 60) return `vor ${diffMins} ${diffMins === 1 ? 'Minute' : 'Minuten'}`;
  
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `vor ${diffHours} ${diffHours === 1 ? 'Stunde' : 'Stunden'}`;
  
  return formatDateShort(date.toISOString());
}

// Status configuration
export interface StatusConfig {
  icon: React.ComponentType<{ className?: string }> | null;
  text: string;
  variant: 'success' | 'warning' | 'error' | 'running' | 'pending';
}

export function getStatusConfig(status: string): StatusConfig {
  // Icons will be imported in components that use this
  const statusConfig: Record<string, StatusConfig> = {
    completed: { icon: null, text: 'Abgeschlossen', variant: 'success' },
    running: { icon: null, text: 'Läuft', variant: 'running' },
    failed: { icon: null, text: 'Fehlgeschlagen', variant: 'error' },
    // Abbruch ist kein Fehler, aber auch kein Erfolg. Ohne eigenen Eintrag
    // würde der Fallback unten daraus "Ausstehend" machen - also glatt falsch.
    cancelled: { icon: null, text: 'Abgebrochen', variant: 'warning' },
    pending: { icon: null, text: 'Ausstehend', variant: 'pending' }
  };
  return statusConfig[status] || statusConfig.pending;
}

// Size formatting
export function formatSize(sizeObj: { bytes: number; formatted: number; unit: string } | undefined): string {
  if (!sizeObj) return 'N/A';
  return `${sizeObj.formatted.toFixed(2)} ${sizeObj.unit}`;
}

// Format bytes to human readable size
export function formatBytes(bytes: number | undefined | null): string {
  if (!bytes || bytes === 0) return '0 B';
  
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const value = bytes / Math.pow(k, i);
  
  return `${value.toFixed(1)} ${sizes[i] || 'B'}`;
}

// Format size for progress display (compact)
// Handles both object format {bytes, formatted, unit} and raw number (bytes)
export function formatSizeCompact(sizeObj: { bytes: number; formatted: number; unit: string } | number | undefined | null): string {
  // Handle raw number (bytes) - from progress API
  if (typeof sizeObj === 'number') {
    return formatBytes(sizeObj);
  }
  
  // Handle object format - from other APIs
  if (!sizeObj || sizeObj.formatted === undefined || sizeObj.formatted === null) {
    // Fallback to bytes if available
    if (sizeObj && typeof sizeObj.bytes === 'number') {
      return formatBytes(sizeObj.bytes);
    }
    return '0 B';
  }
  
  if (sizeObj.formatted < 1) {
    return `${(sizeObj.bytes || 0).toLocaleString()} B`;
  }
  return `${sizeObj.formatted.toFixed(1)} ${sizeObj.unit || 'B'}`;
}

// Get all folders from scan (shares, folders, paths combined)
export function getScanFolders(scan: ScanStatus): string[] {
  const folders: string[] = [];
  if (scan.shares && scan.shares.length > 0) folders.push(...scan.shares);
  if (scan.folders && scan.folders.length > 0) folders.push(...scan.folders);
  if (scan.paths && scan.paths.length > 0) folders.push(...scan.paths);
  return folders;
}

// Build tooltip content for scan info
export function buildScanTooltipContent(scan: ScanStatus): string {
  let content = '';
  
  if (scan.interval) {
    content += `Intervall: ${scan.interval}\n`;
  }
  content += `Status: ${scan.enabled ? '✅ Aktiviert' : '❌ Deaktiviert'}\n`;
  const retryStatus = formatRetryStatus(scan);
  if (retryStatus) {
    content += `Retry: ${retryStatus}\n`;
  }
  
  if (scan.nas) {
    const protocol = scan.nas.use_https ? 'HTTPS' : 'HTTP';
    const port = scan.nas.port || (scan.nas.use_https ? 5001 : 5000);
    content += `\nNAS: ${scan.nas.host}:${port}\n`;
    content += `Protokoll: ${protocol}\n`;
    content += `Benutzer: ${scan.nas.username}\n`;
  }
  
  const folders = getScanFolders(scan);
  if (folders.length > 0) {
    content += `\nPfade (${folders.length}):\n`;
    folders.slice(0, 5).forEach(folder => {
      content += `  • ${folder}\n`;
    });
    if (folders.length > 5) {
      content += `  ... und ${folders.length - 5} weitere`;
    }
  }
  
  return content.trim();
}
