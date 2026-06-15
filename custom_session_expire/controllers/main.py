import time
from odoo import http
from odoo.http import request


class SessionExpireController(http.Controller):

    @http.route('/web/session/request_logout', type='jsonrpc', auth='user')
    def request_logout(self):
        """Mark session as pending logout (called on beforeunload)."""
        request.session['pending_logout_at'] = time.time()
        return {'status': 'pending'}

    @http.route('/web/session/cancel_logout', type='jsonrpc', auth='user')
    def cancel_logout(self):
        """Cancel pending logout (called on page load = it was a refresh)."""
        request.session.pop('pending_logout_at', None)
        return {'status': 'cancelled'}
