{
    'name': 'Company Auto ID',
    'version': '19.0.1.0.0',
    'category': 'CRM',
    'summary': 'Auto generate unique Company ID',
    'depends': ['base', 'contacts', 'crm'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_view.xml',
        'views/crm_lead_view.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'custom_company_auto_id/static/src/js/res_partner_company_id_form.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}