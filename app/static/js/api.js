/**
 * API Functions
 */

export async function fetchScans() {
    const response = await fetch('/api/scans');
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }
    return await response.json();
}

export async function fetchScan(scanName) {
    const response = await fetch(`/api/scans/${scanName}`);
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }
    return await response.json();
}

export async function fetchScanResults(scanName, latest = true) {
    const response = await fetch(`/api/scans/${scanName}/results?latest=${latest}`);
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }
    return await response.json();
}

export async function fetchScanHistory(scanName) {
    const response = await fetch(`/api/scans/${scanName}/history`);
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }
    return await response.json();
}

export async function fetchScanProgress(scanName) {
    const response = await fetch(`/api/scans/${scanName}/progress`);
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }
    return await response.json();
}

export async function triggerScan(scanName) {
    const response = await fetch(`/api/scans/${scanName}/trigger`, {
        method: 'POST'
    });
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }
    return await response.json();
}

export async function reloadConfig() {
    const response = await fetch('/api/config/reload', {
        method: 'POST'
    });
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }
    return await response.json();
}
