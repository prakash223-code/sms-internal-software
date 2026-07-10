from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Creating a user via hr.employee's "Create User" button triggers
    # res.users.create() -> parent.write() on the linked res.partner
    # (base/models/res_partner.py write()). That override pre-reads
    # every field key present in vals — via
    # `{fname: partner[fname] for fname in vals}` — to log tracked
    # changes, regardless of whether the field is meaningfully set.
    # 'credit_limit' is Accounting-restricted (group_account_invoice /
    # similar), so HR/Manager users without Accounting access hit an
    # AccessError on a field they never intended to touch.
    #
    # Same fix pattern as hr_version.py: unlock read access with
    # groups=False rather than granting Accounting/Invoicing group
    # membership, which would pull in unrelated Accounting menus/rights.
    credit_limit = fields.Float(
        string='Credit Limit',
        help='Credit limit specific to this partner.',
        company_dependent=True,
        copy=False,
        readonly=False,
        groups=False,
    )