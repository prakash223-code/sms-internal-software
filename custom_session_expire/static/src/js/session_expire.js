/** @odoo-module **/

const PENDING_KEY = 'odoo_logout_pending';

// Mark explicit logout clicks so pagehide doesn't arm the auto-logout timer
document.addEventListener('click', (ev) => {
    const link = ev.target.closest('a[href*="/web/session/logout"]');
    if (link) {
        sessionStorage.setItem('odoo_explicit_logout', '1');
    }
});

window.addEventListener('pageshow', (ev) => {
    // Fires on every page load AND on bfcache restores (ev.persisted === true).
    // Either way, if we previously armed a pending logout, cancel it now —
    // we're clearly still alive in this tab.
    if (sessionStorage.getItem(PENDING_KEY)) {
        sessionStorage.removeItem(PENDING_KEY);
        fetch('/web/session/cancel_logout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: {} }),
            keepalive: true,
        }).catch(() => {});
    }
});

window.addEventListener('pagehide', () => {
    // Skip entirely on a deliberate logout click — let the real logout happen
    if (sessionStorage.getItem('odoo_explicit_logout')) {
        sessionStorage.removeItem('odoo_explicit_logout');
        return;
    }

    // Fires on real unloads AND on bfcache entry (back/forward, etc).
    // We can't tell which here, so we always arm it — pageshow will
    // disarm it on refresh, back/forward restore, or normal reload.
    // Only a genuine tab/browser close will leave it armed long enough
    // to trip the server-side grace period.
    sessionStorage.setItem(PENDING_KEY, '1');
    navigator.sendBeacon(
        '/web/session/request_logout',
        new Blob(
            [JSON.stringify({ jsonrpc: '2.0', method: 'call', params: {} })],
            { type: 'application/json' }
        )
    );
});