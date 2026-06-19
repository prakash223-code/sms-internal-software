import base64
import mimetypes
from werkzeug.wrappers import Response
from odoo import http
from odoo.http import request


class ProjectDocumentPreviewController(http.Controller):

    # ------------------------------------------------------------------
    # Project Document preview
    # ------------------------------------------------------------------

    @http.route(
        '/project/document/preview/<int:doc_id>',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def preview_document(self, doc_id, **kwargs):
        """
        Serves a project document inline in the browser.
        """
        if not request.env.user.has_group('project.group_project_user'):
            return Response('Access Denied', status=403)

        document = request.env['project.document'].sudo().browse(doc_id)
        if not document.exists() or not document.file:
            return Response('Not Found', status=404)

        return self._serve_binary(
            res_model='project.document',
            res_id=doc_id,
            field_binary=document.file,
            filename=document.filename or 'document',
        )

    # ------------------------------------------------------------------
    # Shared helper
    # ------------------------------------------------------------------

    def _serve_binary(self, res_model, res_id, field_binary, filename):
        """
        Build a werkzeug Response that renders the file inline in the browser.
        Tries ir.attachment first (more reliable when attachment=True);
        falls back to the field value directly.
        """
        attachment = request.env['ir.attachment'].sudo().search([
            ('res_model', '=', res_model),
            ('res_id', '=', res_id),
            ('res_field', '=', 'file'),
        ], limit=1)

        if attachment and attachment.datas:
            file_data = base64.b64decode(attachment.datas)
            mimetype = attachment.mimetype or None
        else:
            file_data = base64.b64decode(field_binary)
            mimetype = None

        if not mimetype:
            mimetype, _ = mimetypes.guess_type(filename)
        if not mimetype:
            mimetype = 'application/octet-stream'

        response = Response(file_data, status=200, mimetype=mimetype)
        response.headers['Content-Disposition'] = f'inline; filename="{filename}"'
        response.headers['Content-Length'] = str(len(file_data))
        response.headers['Cache-Control'] = 'no-cache, no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response