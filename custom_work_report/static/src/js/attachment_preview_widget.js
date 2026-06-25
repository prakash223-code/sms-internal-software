/** @odoo-module **/

/**
 * AttachmentPreviewWidget — fully self-contained.
 *
 * Shows a compact card per attachment with a "Preview" button that opens
 * the file in a NEW BROWSER TAB (via our own inline-serving controller),
 * instead of embedding the file inline in the form or letting Odoo force
 * a download via /web/content.
 *
 * Odoo 19: standardFieldProps no longer exposes `value`. The field's
 * current static list lives at this.props.record.data[this.props.name],
 * and mutations go through useX2ManyCrud() (saveRecord / removeRecord).
 */

import {registry} from "@web/core/registry";
import {many2ManyBinaryField} from "@web/views/fields/many2many_binary/many2many_binary_field";
import {FileUploader} from "@web/views/fields/file_handler";
import {standardFieldProps} from "@web/views/fields/standard_field_props";
import {useX2ManyCrud} from "@web/views/fields/relational_utils";
import {useService} from "@web/core/utils/hooks";
import {Component, xml} from "@odoo/owl";

export class AttachmentPreviewWidget extends Component {
    static props = {...standardFieldProps};
    static components = {FileUploader};

    static template = xml`
    <div class="o_field_attachment_preview">

        <!-- ── Upload button (edit mode only) ── -->
        <t t-if="!props.readonly">
            <FileUploader multiUpload="true" onUploaded.bind="onFileUploaded">
                <t t-set-slot="toggler">
                    <button type="button" class="btn btn-secondary btn-sm mb-3">
                        <i class="fa fa-paperclip me-1"/> Attach Files
                    </button>
                </t>
            </FileUploader>
        </t>

        <!-- ── Empty state ── -->
        <t t-if="records.length === 0">
            <div><span class="text-muted fst-italic">No attachments</span></div>
        </t>

        <!-- ── Attachment cards ── -->
        <div class="d-flex flex-wrap gap-3">
            <t t-foreach="records" t-as="rec" t-key="rec.resId or rec.id">
                <div class="border rounded overflow-hidden bg-white"
                     style="width:220px; box-shadow:0 1px 4px rgba(0,0,0,.08);">

                    <!-- Header: icon + filename + remove -->
                    <div class="d-flex align-items-center gap-1 px-2 py-1 border-bottom"
                         style="background:#f5f5f5;">
                        <i t-att-class="getIcon(rec.data.mimetype) + ' text-muted flex-shrink-0'"/>
                        <span class="text-truncate small fw-semibold flex-grow-1"
                              t-att-title="rec.data.name">
                            <t t-esc="rec.data.name"/>
                        </span>
                        <t t-if="!props.readonly">
                            <button type="button"
                                    class="btn btn-sm p-0 lh-1 ms-1 text-danger border-0 bg-transparent"
                                    title="Remove"
                                    t-on-click="() => this.removeRecord(rec)">
                                <i class="fa fa-times"/>
                            </button>
                        </t>
                    </div>

                    <!-- Body: big icon + Preview / Download buttons -->
                    <div class="d-flex flex-column align-items-center justify-content-center p-3"
                         style="min-height:120px; background:#fafafa;">

                        <!-- Uploading spinner (no resId yet) -->
                        <t t-if="!rec.resId">
                            <i class="fa fa-spinner fa-spin fa-2x mb-1 text-muted"/>
                            <small class="text-muted">Uploading…</small>
                        </t>

                        <t t-else="">
                            <i t-att-class="getIcon(rec.data.mimetype) + ' fa-3x mb-2 text-muted'"/>
                            <div class="d-flex gap-2">
                                <!-- Opens in a NEW TAB via our inline-serving controller -->
                                <a t-attf-href="/work_report/attachment/preview/{{ rec.resId }}"
                                   target="_blank"
                                   rel="noopener"
                                   class="btn btn-sm btn-outline-primary"
                                   onclick="event.stopPropagation()">
                                    <i class="fa fa-eye me-1"/>Preview
                                </a>
                                <!-- Explicit force-download, for anyone who actually wants to save it -->
                                <a t-attf-href="/web/content/{{ rec.resId }}?download=true"
                                   class="btn btn-sm btn-outline-secondary"
                                   onclick="event.stopPropagation()">
                                    <i class="fa fa-download"/>
                                </a>
                            </div>
                        </t>
                    </div>
                </div>
            </t>
        </div>

    </div>
    `;

    setup() {
        this.orm = useService("orm");
        this.operations = useX2ManyCrud(
            () => this.props.record.data[this.props.name],
            true // isMany2Many
        );
    }

    get records() {
        return this.props.record.data[this.props.name]?.records || [];
    }

    getIcon(mimetype) {
        if (!mimetype) return "fa fa-file-o";
        if (mimetype.startsWith("image/")) return "fa fa-file-image-o";
        if (mimetype === "application/pdf") return "fa fa-file-pdf-o";
        if (mimetype.includes("word") || mimetype.includes("document")) return "fa fa-file-word-o";
        if (mimetype.includes("excel") || mimetype.includes("spreadsheet")) return "fa fa-file-excel-o";
        if (mimetype.includes("zip") || mimetype.includes("compressed")) return "fa fa-file-zip-o";
        return "fa fa-file-o";
    }

    async onFileUploaded({name, size: file_size, type: mimetype, data: datas}) {
        const attId = await this.orm.call("ir.attachment", "create", [{
            name,
            datas,
            res_model: "ir.ui.view",
        }]);
        await this.operations.saveRecord([attId]);
    }

    async removeRecord(record) {
        this.operations.removeRecord(record);
    }
}

registry.category("fields").add("attachment_preview", {
    ...many2ManyBinaryField,
    component: AttachmentPreviewWidget,
});