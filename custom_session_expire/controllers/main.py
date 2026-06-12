from odoo.http import request
from odoo import http


class SessionExpireController(http.Controller):

    @http.route('/web/session/browser_close', type='jsonrpc', auth='user')
    def browser_close(self):
        request.session.logout(keep_db=True)
        return {'status': 'logged_out'}
