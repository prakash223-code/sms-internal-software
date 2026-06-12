/** @odoo-module **/

window.addEventListener("beforeunload", () => {
    const data = JSON.stringify({
        jsonrpc: "2.0",
        method: "call",
        params: {},
    });
    navigator.sendBeacon(
        "/web/session/browser_close",
        new Blob([data], { type: "application/json" })
    );
});
