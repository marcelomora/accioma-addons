# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 Devintelle Software Solutions (<http://devintellecs.com>).
#
##############################################################################
{
    'name': 'Import Payslip Input',
    'version': '12.0.1.0',
    'category': 'Generic Modules/Human Resources',
    'sequence': 1,
    'summary': 'odoo app allow Mass Import Payslip Input in quick way',
    'description': """
         odoo app  helps you to Import mass Payslip Input in quick way
         
         Import payslip,payslip input, other input, import inputs, mass input, import payslip inputes
 Import Payslip Input
Odoo Import Payslip Input
Import payslip
Odoo import payslip
Payslip input
Odoo payslip input
Export payslip
Odoo export payslip
Import multiple payslip
Odoo import multiple payslip
Export multiple payslip
Odoo export multiple payslip
Import payslip into excel
Odoo import payslip into excel
Import payslip into CSV
Odoo import payslip into CSV
Export payslip input
Odoo export payslip input
         """,
    'author': 'DevIntelle Consulting Service Pvt.Ltd',
    'website': 'http://www.devintellecs.com/',
    'depends': ['hr_payroll'],
    'data': [
        'views/payroll_input_view.xml'
    ],
    'demo': [],
    'test': [],
    'css': [],
    'qweb': [],
    'js': [],
    'images': ['images/main_screenshot.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price':12.0,
    'currency':'EUR',
   # 'live_test_url':'https://youtu.be/A5kEBboAh_k',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
