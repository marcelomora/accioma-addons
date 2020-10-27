#  -*- encoding: utf-8 -*-
{
    "name": "Bank Reconcilation Report",
    "version": "12.0.0.1.0",
    "license": "LGPL-3",
    "author": "Serpent Consulting Services Pvt. Ltd.",
    'category': 'Accounting',
    "sequence": 1,
    "website": "http://www.serpentcs.com",
    "description": """
Singapore Accounting: QWeb reports of bank reconcilation.
Bank statement report
bank reconcilation report
bank detail report
bank statement reconcilation
""",
    "summary": """
Singapore Accounting
""",
    'depends': ['account'],
    'data': [
             'views/sg_bank_statement_recon_template.xml',
             'views/report_view.xml'
    ],
    'installable': True,
    'auto_install': False,
    "price": 49,
    "currency": 'EUR',
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
