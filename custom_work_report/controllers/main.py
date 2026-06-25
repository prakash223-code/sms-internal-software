import base64
import mimetypes
from werkzeug.wrappers import Response
from odoo import http
from odoo.http import request


class WorkReportAttachmentPreviewController(http.Controller):

    @http.route(
        '/work_report/attachment/preview/<int:attachment_id>',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def preview_attachment(self, attachment_id, **kwargs):
        """
        Serves a work report attachment with Content-Disposition: inline
        so the browser renders it instead of forcing a download.

        Built directly with werkzeug (not Odoo's content controller) to
        avoid Odoo's default attachment-disposition for non-image
        mimetypes like PDF.

        Access check: attachments are uploaded with res_model='ir.ui.view'
        (standard many2many_binary pattern), so we can't rely on
        ir.attachment's own res_model/res_id access. Instead:
          - allow the uploader to preview their own just-uploaded file
            (covers unsaved/draft work reports where the M2M isn't
            committed yet), or
          - allow anyone who can read a work.report that the attachment
            is actually linked to (respects work.report's own ir.rule:
            employees see their own, HR/Manager see all).
        """
        attachment = request.env['ir.attachment'].sudo().browse(attachment_id)
        if not attachment.exists() or not attachment.datas:
            return Response('Not Found', status=404)

        is_owner = attachment.create_uid.id == request.env.uid
        report = False
        if not is_owner:
            report = request.env['work.report'].search(
                [('attachment_ids', 'in', attachment_id)], limit=1
            )

        if not is_owner and not report:
            return Response('Access Denied', status=403)

        filename = attachment.name or 'attachment'
        file_data = base64.b64decode(attachment.datas)
        mimetype = attachment.mimetype

        if not mimetype:
            mimetype, _ = mimetypes.guess_type(filename)
        if not mimetype:
            mimetype = 'application/octet-stream'

        response = Response(
            file_data,
            status=200,
            mimetype=mimetype,
        )
        response.headers['Content-Disposition'] = f'inline; filename="{filename}"'
        response.headers['Content-Length'] = str(len(file_data))
        response.headers['Cache-Control'] = 'no-cache, no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'

        return response