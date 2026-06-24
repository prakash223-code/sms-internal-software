/** @odoo-module **/

/**
 * AttachmentPreviewWidget — fully self-contained.
 *
 * Replaces Many2ManyBinaryField entirely so there are zero download-forcing
 * <a ?download=true> links anywhere in the widget.
 *
 * Upload  → FileUploader → creates ir.attachment via ORM → adds to M2M list
 * Image   → rendered inline via /web/image/{id}
 * PDF     → embedded via <embed type="application/pdf"> (browser PDF viewer,
 *           no Content-Disposition:attachment because we don't pass ?download)
 * Other   → download button only (Word, Excel, zip, etc. can't render in-browser)
 */

import {registry} from "@web/core/registry";
import {many2ManyBinaryField} from "@web/views/fields/many2many_binary/many2many_binary_field";
import {FileUploader} from "@web/views/fields/file_handler";
import {standardFieldProps} from "@web/views/fields/standard_field_props";
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
            <span class="text-muted fst-italic">No attachments</span>
        </t>

        <!-- ── Attachment cards ── -->
        <div class="d-flex flex-wrap gap-3">
            <t t-foreach="records" t-as="rec" t-key="rec.resId or rec.virtualId">
                <div class="border rounded overflow-hidden bg-white"
                     style="width:280px; box-shadow:0 1px 4px rgba(0,0,0,.08);">

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

                    <!-- Preview area -->
                    <div class="d-flex align-items-center justify-content-center"
                         style="min-height:150px; background:#fafafa;">

                        <!-- Uploading spinner (no resId yet) -->
                        <t t-if="!rec.resId">
                            <div class="text-muted text-center p-3">
                                <i class="fa fa-spinner fa-spin fa-2x d-block mb-1"/>
                                <small>Uploading…</small>
                            </div>
                        </t>

                        <!-- Image — rendered via /web/image (always inline) -->
                        <t t-elif="isImage(rec.data.mimetype)">
                            <img t-attf-src="/web/image/{{ rec.resId }}"
                                 class="img-fluid"
                                 style="max-height:220px; object-fit:contain; width:100%;"
                                 t-att-alt="rec.data.name"/>
                        </t>

                        <!--
                            PDF — use &lt;embed&gt; with explicit type so the browser
                            activates its built-in PDF viewer directly without going
                            through a redirect.  No ?download param → server returns
                            Content-Disposition: inline.
                        -->
                        <t t-elif="isPdf(rec.data.mimetype)">
                            <embed t-attf-src="/web/content/{{ rec.resId }}"
                                   type="application/pdf"
                                   style="width:280px; height:240px; border:none;"/>
                        </t>

                        <!-- Anything else → explicit download button -->
                        <t t-else="">
                            <div class="text-center p-3 text-muted">
                                <i t-att-class="getIcon(rec.data.mimetype) + ' fa-2x d-block mb-2'"/>
                                <a t-attf-href="/web/content/{{ rec.resId }}?download=true"
                                   target="_blank"
                                   class="btn btn-sm btn-outline-secondary">
                                    <i class="fa fa-download me-1"/>Download
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
    }

    get records() {
        return this.props.value?.records || [];
    }

    isImage(mimetype) {
        return !!mimetype && mimetype.startsWith("image/");
    }

    isPdf(mimetype) {
        return mimetype === "application/pdf";
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

    /**
     * Called by FileUploader when the user picks a file.
     * 1. Creates the ir.attachment record via ORM (same pattern as core many2many_binary).
     * 2. Adds it to the StaticList via addAndUnlink so OWL re-renders immediately.
     */
    async onFileUploaded({name, size: file_size, type: mimetype, data: datas}) {
        const attId = await this.orm.call("ir.attachment", "create", [{
            name,
            datas,
            res_model: "ir.ui.view",
        }]);
        await this.props.value.addAndUnlink(attId, {name, file_size, mimetype});
    }

    async removeRecord(record) {
        await this.props.value.delete(record);
    }
}

registry.category("fields").add("attachment_preview", {
    ...many2ManyBinaryField,   // keeps relatedFields: name, file_size, mimetype
    component: AttachmentPreviewWidget,
});