# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://devintellecs.com>).
#
##############################################################################

from odoo import models, api


class payslip_input(models.Model):
    _inherit = 'hr.payslip.input'

    @api.multi
    @api.onchange('payslip_id')
    def onchange_payslip_id(self):
        for input in self:
            if input.payslip_id.contract_id:
                input.contract_id = input.payslip_id.contract_id
            else:
                input.contract_id = False

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
