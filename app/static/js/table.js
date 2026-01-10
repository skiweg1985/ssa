/**
 * Table Functions for Scan Overview
 */

import { formatDateShort, getStatusConfig } from './utils.js';
import { triggerScan } from './api.js';
import { showToast } from './utils.js';

let currentScans = [];
let onShowResults, onShowHistory, onShowDetail;

export function initTable(callbacks) {
    onShowResults = callbacks.showResults;
    onShowHistory = callbacks.showHistory;
    onShowDetail = callbacks.showDetail;
}

export function getCurrentScans() {
    return currentScans;
}

export function createScanTableRow(scan) {
    const row = document.createElement('tr');
    const statusClass = scan.status === 'running' ? 'scan-row-running' : '';
    row.className = statusClass;
    
    const status = getStatusConfig(scan.status);
    
    // Status Cell
    const statusCell = document.createElement('td');
    const statusBadge = document.createElement('span');
    statusBadge.className = `inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold ${status.class}`;
    statusBadge.innerHTML = `<span>${status.icon}</span><span>${status.text}</span>`;
    statusCell.appendChild(statusBadge);
    
    // Job Name Cell
    const nameCell = document.createElement('td');
    const nameLink = document.createElement('a');
    nameLink.href = '#';
    nameLink.className = 'font-semibold text-slate-900 hover:text-primary-600 transition-colors cursor-pointer';
    nameLink.textContent = scan.scan_name;
    nameLink.onclick = (e) => {
        e.preventDefault();
        if (onShowDetail) onShowDetail(scan);
    };
    nameCell.appendChild(nameLink);
    
    // Last Run Cell
    const lastRunCell = document.createElement('td');
    if (scan.last_run) {
        lastRunCell.textContent = formatDateShort(scan.last_run);
    } else {
        lastRunCell.textContent = '-';
        lastRunCell.className = 'text-slate-400';
    }
    
    // Next Run Cell
    const nextRunCell = document.createElement('td');
    if (scan.next_run) {
        nextRunCell.textContent = formatDateShort(scan.next_run);
    } else {
        nextRunCell.textContent = '-';
        nextRunCell.className = 'text-slate-400';
    }
    
    // Additional Info Cell (with Tooltip)
    const infoCell = document.createElement('td');
    const tooltipContainer = document.createElement('div');
    tooltipContainer.className = 'tooltip-container';
    
    const infoIcon = document.createElement('span');
    infoIcon.className = 'text-slate-500 cursor-help';
    infoIcon.textContent = 'ℹ️';
    
    const tooltip = document.createElement('div');
    tooltip.className = 'tooltip';
    
    let tooltipContent = '';
    if (scan.interval) {
        tooltipContent += `Intervall: ${scan.interval}\n`;
    }
    tooltipContent += `Status: ${scan.enabled ? '✅ Aktiviert' : '❌ Deaktiviert'}\n`;
    
    if (scan.nas) {
        const protocol = scan.nas.use_https ? 'HTTPS' : 'HTTP';
        const port = scan.nas.port || (scan.nas.use_https ? 5001 : 5000);
        tooltipContent += `\nNAS: ${scan.nas.host}:${port}\n`;
        tooltipContent += `Protokoll: ${protocol}\n`;
        tooltipContent += `Benutzer: ${scan.nas.username}\n`;
    }
    
    const folders = [];
    if (scan.shares && scan.shares.length > 0) folders.push(...scan.shares);
    if (scan.folders && scan.folders.length > 0) folders.push(...scan.folders);
    if (scan.paths && scan.paths.length > 0) folders.push(...scan.paths);
    
    if (folders.length > 0) {
        tooltipContent += `\nPfade (${folders.length}):\n`;
        folders.slice(0, 5).forEach(folder => {
            tooltipContent += `  • ${folder}\n`;
        });
        if (folders.length > 5) {
            tooltipContent += `  ... und ${folders.length - 5} weitere`;
        }
    }
    
    tooltip.textContent = tooltipContent.trim();
    tooltipContainer.appendChild(infoIcon);
    tooltipContainer.appendChild(tooltip);
    infoCell.appendChild(tooltipContainer);
    
    // Actions Cell
    const actionsCell = document.createElement('td');
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'action-buttons';
    
    const startBtn = document.createElement('button');
    startBtn.className = 'action-btn bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed';
    startBtn.innerHTML = '▶';
    startBtn.title = 'Scan starten';
    startBtn.onclick = async (e) => {
        e.stopPropagation();
        try {
            await triggerScan(scan.scan_name);
            showToast('Erfolg', `Scan '${scan.scan_name}' wurde gestartet`, 'success');
            // Reload table after a short delay
            setTimeout(() => {
                if (window.loadScans) window.loadScans(false);
            }, 1000);
        } catch (error) {
            showToast('Fehler', `Fehler beim Starten: ${error.message}`, 'error');
        }
    };
    startBtn.disabled = scan.status === 'running' || !scan.enabled;
    
    const resultsBtn = document.createElement('button');
    resultsBtn.className = 'action-btn bg-primary-500 text-white hover:bg-primary-600';
    resultsBtn.innerHTML = '📊';
    resultsBtn.title = 'Ergebnisse anzeigen';
    resultsBtn.onclick = (e) => {
        e.stopPropagation();
        if (onShowResults) onShowResults(scan.scan_name);
    };
    
    const historyBtn = document.createElement('button');
    historyBtn.className = 'action-btn bg-white border border-slate-300 text-slate-700 hover:bg-slate-50';
    historyBtn.innerHTML = '📜';
    historyBtn.title = 'Historie anzeigen';
    historyBtn.onclick = (e) => {
        e.stopPropagation();
        if (onShowHistory) onShowHistory(scan.scan_name);
    };
    
    const detailBtn = document.createElement('button');
    detailBtn.className = 'action-btn bg-blue-600 text-white hover:bg-blue-700';
    detailBtn.innerHTML = '🔍';
    detailBtn.title = 'Details anzeigen';
    detailBtn.onclick = (e) => {
        e.stopPropagation();
        if (onShowDetail) onShowDetail(scan);
    };
    
    actionsDiv.appendChild(startBtn);
    actionsDiv.appendChild(resultsBtn);
    actionsDiv.appendChild(historyBtn);
    actionsDiv.appendChild(detailBtn);
    actionsCell.appendChild(actionsDiv);
    
    row.appendChild(statusCell);
    row.appendChild(nameCell);
    row.appendChild(lastRunCell);
    row.appendChild(nextRunCell);
    row.appendChild(infoCell);
    row.appendChild(actionsCell);
    
    return row;
}

export async function renderScanTable(showToastCallback = null) {
    const scanList = document.getElementById('scan-list');
    
    scanList.innerHTML = '<tr><td colspan="6" class="text-center py-12"><div class="text-slate-500">Lade Scans...</div></td></tr>';
    
    try {
        const { fetchScans } = await import('./api.js');
        const data = await fetchScans();
        
        if (data.scans && data.scans.length > 0) {
            scanList.innerHTML = '';
            currentScans = data.scans;
            
            data.scans.forEach(scan => {
                const scanRow = createScanTableRow(scan);
                scanList.appendChild(scanRow);
            });
        } else {
            currentScans = [];
            scanList.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center py-16">
                        <div class="flex flex-col items-center justify-center text-center">
                            <div class="text-6xl mb-4">📭</div>
                            <p class="text-slate-600 text-lg">Keine Scans konfiguriert</p>
                        </div>
                    </td>
                </tr>
            `;
        }
    } catch (error) {
        currentScans = [];
        scanList.innerHTML = `
            <tr>
                <td colspan="6" class="text-center py-4">
                    <div class="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800">
                        <div class="font-semibold mb-1">Fehler beim Laden der Scans</div>
                        <div class="text-sm">${error.message}</div>
                        <button 
                            class="mt-3 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
                            onclick="window.loadScans()"
                        >
                            Erneut versuchen
                        </button>
                    </div>
                </td>
            </tr>
        `;
        if (showToastCallback) {
            showToastCallback('Fehler', 'Fehler beim Laden der Scans', 'error');
        }
    }
}
