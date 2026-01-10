/**
 * Utility Functions
 */

export function showToast(title, message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    
    const typeConfig = {
        success: 'bg-green-50 border-green-200 text-green-800',
        error: 'bg-red-50 border-red-200 text-red-800',
        warning: 'bg-yellow-50 border-yellow-200 text-yellow-800',
        info: 'bg-blue-50 border-blue-200 text-blue-800'
    };
    
    toast.className = `bg-white border-l-4 rounded-lg shadow-lg p-4 min-w-[300px] ${typeConfig[type] || typeConfig.info}`;
    
    toast.innerHTML = `
        <div class="flex justify-between items-start mb-2">
            <span class="font-semibold">${title}</span>
            <button 
                class="text-slate-400 hover:text-slate-600 focus:outline-none focus:ring-2 focus:ring-primary-500 rounded"
                onclick="this.parentElement.parentElement.remove()"
                aria-label="Toast schließen"
            >
                ×
            </button>
        </div>
        <div class="text-sm">${message}</div>
    `;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        if (toast.parentElement) {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.3s';
            setTimeout(() => toast.remove(), 300);
        }
    }, 5000);
}

export function formatDate(dateString) {
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

export function formatDateShort(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString('de-DE', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

export function getStatusConfig(status) {
    const statusConfig = {
        completed: { icon: '✅', text: 'Abgeschlossen', class: 'bg-green-100 text-green-800' },
        running: { icon: '🔄', text: 'Läuft', class: 'bg-yellow-100 text-yellow-800' },
        failed: { icon: '❌', text: 'Fehlgeschlagen', class: 'bg-red-100 text-red-800' },
        pending: { icon: '⏳', text: 'Ausstehend', class: 'bg-slate-100 text-slate-800' }
    };
    return statusConfig[status] || statusConfig.pending;
}
