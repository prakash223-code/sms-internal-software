import base64
import mimetypes
from werkzeug.wrappers import Response
from odoo import http
from odoo.http import request


class HrDocumentPreviewController(http.Controller):

    @http.route(
        '/hr/document/preview/<int:doc_id>',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def preview_document(self, doc_id, **kwargs):
        """
        Serves employee document with Content-Disposition: inline so the
        browser renders it instead of downloading.

        Uses werkzeug Response directly to avoid Odoo's internal wrappers
        that may override Content-Disposition back to attachment.

        Reads binary data through ir.attachment (more reliable when the
        Binary field is stored with attachment=True).
        """
        # Access check — HR and Manager only
        if not request.env.user.has_group('hr.group_hr_user') \
                and not request.env.user.has_group('hr.group_hr_manager'):
            return Response('Access Denied', status=403)

        # Find the document record
        document = request.env['hr.employee.document'].sudo().browse(doc_id)
        if not document.exists() or not document.file:
            return Response('Not Found', status=404)

        filename = document.filename or 'document'

        # Read binary data through ir.attachment — more reliable than
        # reading document.file directly when attachment=True is set
        attachment = request.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'hr.employee.document'),
            ('res_id', '=', doc_id),
            ('res_field', '=', 'file'),
        ], limit=1)

        if attachment and attachment.datas:
            file_data = base64.b64decode(attachment.datas)
            # Use attachment's stored mimetype if available
            mimetype = attachment.mimetype or None
        else:
            # Fallback: read directly from field
            file_data = base64.b64decode(document.file)
            mimetype = None

        # Guess mimetype from filename extension if not already known
        if not mimetype:
            mimetype, _ = mimetypes.guess_type(filename)
        if not mimetype:
            mimetype = 'application/octet-stream'

        # Build werkzeug Response directly — this guarantees our headers
        # are not overridden by any Odoo middleware
        response = Response(
            file_data,
            status=200,
            mimetype=mimetype,
        )
        # inline → browser renders the file instead of downloading
        response.headers['Content-Disposition'] = f'inline; filename="{filename}"'
        response.headers['Content-Length'] = str(len(file_data))
        response.headers['Cache-Control'] = 'no-cache, no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'

        return response