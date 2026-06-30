import time
from odoo import http
from odoo.http import request


class SessionExpireController(http.Controller):

    @http.route('/web/session/request_logout', type='jsonrpc', auth='user')
    def request_logout(self):
        """Mark session as pending logout (called on pagehide)."""
        request.session['pending_logout_at'] = time.time()
        return {'status': 'pending'}

    @http.route('/web/session/cancel_logout', type='jsonrpc', auth='public')
    def cancel_logout(self):
        """Cancel pending logout (called on pageshow = tab still alive).

        auth='public' on purpose: by the time this fires the session may
        already be gone (real logout, or it expired before we got here).
        We just no-op instead of throwing, so this call can never itself
        cause an error page.
        """
        if request.session.uid:
            request.session.pop('pending_logout_at', None)
            return {'status': 'cancelled'}
        return {'status': 'no_session'}