import time
from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _authenticate(cls, endpoint):
        result = super()._authenticate(endpoint)
        if request.session.uid and request.session.get('pending_logout_at'):
            # Grace period of 5 seconds:
            # - Refresh / bfcache restore: cancel_logout arrives in < 1s via
            #   pageshow → pending_logout_at gets cleared
            # - Browser close: next visit is minutes/hours later → always
            #   > 5s → log out
            try:
                elapsed = time.time() - float(request.session['pending_logout_at'])
            except (TypeError, ValueError):
                # Corrupt or non-numeric value — clear it and carry on safely
                request.session.pop('pending_logout_at', None)
                elapsed = 0
            if elapsed > 5:
                request.session.logout(keep_db=True)
        return result