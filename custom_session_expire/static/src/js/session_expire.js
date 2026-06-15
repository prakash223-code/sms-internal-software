/** @odoo-module **/

const PENDING_KEY = 'odoo_logout_pending';

window.addEventListener('load', () => {
    if (sessionStorage.getItem(PENDING_KEY)) {
        // We got here after a beforeunload → it was a refresh, cancel logout
        sessionStorage.removeItem(PENDING_KEY);
        fetch('/web/session/cancel_logout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: {} }),
        }).catch(() => {});
    }
});

window.addEventListener('beforeunload', () => {
    // Set flag in sessionStorage
    // - On refresh: next page load will find this flag and cancel logout
    // - On browser close: sessionStorage is wiped, flag never found, logout stands
    sessionStorage.setItem(PENDING_KEY, '1');
    navigator.sendBeacon(
        '/web/session/request_logout',
        new Blob(
            [JSON.stringify({ jsonrpc: '2.0', method: 'call', params: {} })],
            { type: 'application/json' }
        )
    );
});