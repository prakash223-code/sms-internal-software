/** @odoo-module **/

import { FormController } from "@web/views/form/form_controller";
import { registry } from "@web/core/registry";
import { formView } from "@web/views/form/form_view";

/**
 * Custom FormController for res.partner.
 *
 * Odoo 19's partner_autocomplete calls web_save() immediately when the user
 * clicks an IAP suggestion, which triggers Python create() before the user
 * has explicitly clicked Save.  We therefore generate the company_custom_id
 * here — after an explicit Save button click — rather than in Python create().
 */
class PartnerCompanyIdFormController extends FormController {

    async saveButtonClicked(params = {}) {
        const saved = await super.saveButtonClicked(params);
        if (saved) {
            await this._maybeGenerateCompanyId();
        }
        return saved;
    }

    async _maybeGenerateCompanyId() {
        const record = this.model.root;
        const resId = record.resId;
        if (!resId) return;

        // Reload to pick up any server-side side effects (e.g. company_type
        // regeneration from the Python write() handler).
        await record.load();

        if (record.data.is_company && !record.data.company_custom_id) {
            await this.env.services.orm.call(
                "res.partner",
                "action_generate_company_id",
                [[resId]]
            );
            // Reload once more so the generated ID appears in the form.
            await record.load();
        }
    }
}

registry.category("views").add("res_partner_company_id_form", {
    ...formView,
    Controller: PartnerCompanyIdFormController,
});