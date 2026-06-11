/** @odoo-module **/

import { FormController } from "@web/views/form/form_controller";
import { registry } from "@web/core/registry";
import { formView } from "@web/views/form/form_view";

/**
 * Custom FormController for res.partner.
 *
 * Generates company_custom_id only when the user explicitly clicks Save —
 * not when partner_autocomplete calls web_save() on IAP suggestion click.
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

        // Reload to pick up server-side field values after save.
        await record.load();

        if (record.data.is_company && !record.data.company_custom_id) {
            await this.env.services.orm.call(
                "res.partner",
                "action_generate_company_id",
                [[resId]]
            );
            // Reload to display the generated ID in the form.
            await record.load();
        }
    }
}

registry.category("views").add("res_partner_company_id_form", {
    ...formView,
    Controller: PartnerCompanyIdFormController,
});