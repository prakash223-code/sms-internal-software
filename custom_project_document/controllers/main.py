import base64
import mimetypes
from werkzeug.wrappers import Response
from odoo import http
from odoo.http import request


class ProjectDocumentPreviewController(http.Controller):

    @http.route(
        '/project/document/preview/<int:doc_id>',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def preview_document(self, doc_id, **kwargs):
        """
        Serves project document with Content-Disposition: inline so the
        browser renders it instead of downloading.

        Uses werkzeug Response directly to avoid Odoo's internal wrappers
        that may override Content-Disposition back to attachment.

        Access:  Any logged-in project user can preview.
                 (project-level access is controlled at the model/view layer)
        """
        # Access check — must be at least a project user
        if not request.env.user.has_group('project.group_project_user'):
            return Response('Access Denied', status=403)

        # Find the document record (sudo so read always works for URL preview)
        document = request.env['project.document'].sudo().browse(doc_id)
        if not document.exists() or not document.file:
            return Response('Not Found', status=404)

        filename = document.filename or 'document'

        # Read binary data through ir.attachment — more reliable when
        # Binary field is stored with attachment=True
        attachment = request.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'project.document'),
            ('res_id', '=', doc_id),
            ('res_field', '=', 'file'),
        ], limit=1)

        if attachment and attachment.datas:
            file_data = base64.b64decode(attachment.datas)
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

        # Build werkzeug Response directly — guarantees headers are not
        # overridden by Odoo middleware
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
