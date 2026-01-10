/**
 * Modal Functions
 */

import { getStatusConfig, formatDate } from './utils.js';
import { triggerScan } from './api.js';
import { showToast } from './utils.js';

let onShowResults, onShowHistory;

export function initModals(callbacks) {
    onShowResults = callbacks.showResults;
    onShowHistory = callbacks.showHistory;
}

export function showDetailModal(scan) {
    const modal = document.getElementById('detail-modal');
    const title = document.getElementById('detail-modal-title');
    const content = document.getElementById('detail-content');
    const statusBadge = document.getElementById('detail-status-badge');
    const triggerBtn = document.getElementById('detail-trigger-btn');
    
    title.textContent = `📋 ${scan.scan_name}`;
    
    const status = getStatusConfig(scan.status);
    
    statusBadge.className = `inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold ${status.class}`;
    statusBadge.innerHTML = `<span>${status.icon}</span><span>${status.text}</span>`;
    
    triggerBtn.disabled = scan.status === 'running' || !scan.enabled;
    triggerBtn.onclick = async () => {
        try {
            await triggerScan(scan.scan_name);
            showToast('Erfolg', `Scan '${scan.scan_name}' wurde gestartet`, 'success');
            closeDetailModal();
            // Reload table after a short delay
            setTimeout(() => {
                if (window.loadScans) window.loadScans(false);
            }, 1000);
        } catch (error) {
            showToast('Fehler', `Fehler beim Starten: ${error.message}`, 'error');
        }
    };
    
    let html = `
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div class="space-y-4">
                <div>
                    <h3 class="text-sm font-semibold text-slate-700 mb-2">📅 Zeitplan</h3>
                    <div class="bg-slate-50 rounded-lg p-4 space-y-2">
                        <div class="flex justify-between">
                            <span class="text-slate-600">Letzter Lauf:</span>
                            <span class="font-medium">${scan.last_run ? formatDate(scan.last_run) : '-'}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-slate-600">Nächster Lauf:</span>
                            <span class="font-medium">${scan.next_run ? formatDate(scan.next_run) : '-'}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-slate-600">Intervall:</span>
                            <span class="font-medium">${scan.interval || '-'}</span>
                        </div>
                    </div>
                </div>
                
                <div>
                    <h3 class="text-sm font-semibold text-slate-700 mb-2">⚙️ Konfiguration</h3>
                    <div class="bg-slate-50 rounded-lg p-4 space-y-2">
                        <div class="flex justify-between">
                            <span class="text-slate-600">Status:</span>
                            <span class="font-medium">${scan.enabled ? '✅ Aktiviert' : '❌ Deaktiviert'}</span>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="space-y-4">
                ${scan.nas ? `
                <div>
                    <h3 class="text-sm font-semibold text-slate-700 mb-2">🖥️ NAS-Verbindung</h3>
                    <div class="bg-slate-50 rounded-lg p-4 space-y-2">
                        <div class="flex justify-between">
                            <span class="text-slate-600">Host:</span>
                            <span class="font-medium">${scan.nas.host}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-slate-600">Port:</span>
                            <span class="font-medium">${scan.nas.port || (scan.nas.use_https ? 5001 : 5000)}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-slate-600">Protokoll:</span>
                            <span class="font-medium">${scan.nas.use_https ? 'HTTPS' : 'HTTP'}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-slate-600">Benutzer:</span>
                            <span class="font-medium">${scan.nas.username}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-slate-600">SSL-Verifizierung:</span>
                            <span class="font-medium">${scan.nas.verify_ssl ? 'Ja' : 'Nein'}</span>
                        </div>
                    </div>
                </div>
                ` : ''}
                
                <div>
                    <h3 class="text-sm font-semibold text-slate-700 mb-2">📂 Pfade</h3>
                    <div class="bg-slate-50 rounded-lg p-4">
                        ${(() => {
                            const folders = [];
                            if (scan.shares && scan.shares.length > 0) folders.push(...scan.shares.map(s => `Share: ${s}`));
                            if (scan.folders && scan.folders.length > 0) folders.push(...scan.folders.map(f => `Ordner: ${f}`));
                            if (scan.paths && scan.paths.length > 0) folders.push(...scan.paths.map(p => `Pfad: ${p}`));
                            
                            if (folders.length > 0) {
                                return '<ul class="space-y-1">' + folders.map(f => `<li class="text-sm text-slate-700">• ${f}</li>`).join('') + '</ul>';
                            }
                            return '<p class="text-sm text-slate-400">Keine Pfade konfiguriert</p>';
                        })()}
                    </div>
                </div>
            </div>
        </div>
        
        <div class="pt-6 border-t border-slate-200">
            <div class="flex gap-3">
                <button 
                    class="px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 transition-colors" 
                    onclick="window.showResultsForScan('${scan.scan_name}'); window.closeDetailModal();"
                >
                    📊 Ergebnisse anzeigen
                </button>
                <button 
                    class="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-50 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 transition-colors" 
                    onclick="window.showHistoryForScan('${scan.scan_name}'); window.closeDetailModal();"
                >
                    📜 Historie anzeigen
                </button>
            </div>
        </div>
    `;
    
    content.innerHTML = html;
    
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    document.body.style.overflow = 'hidden';
}

export function closeDetailModal() {
    const modal = document.getElementById('detail-modal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    document.body.style.overflow = '';
}

// Make functions globally available for onclick handlers
window.closeDetailModal = closeDetailModal;
window.showDetailModal = showDetailModal;
