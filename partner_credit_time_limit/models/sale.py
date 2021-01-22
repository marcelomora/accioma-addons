# -*- encoding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

from datetime import datetime
from odoo import api, models, _
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def check_time_limit(self):
        self.ensure_one()
        partner = self.partner_id
        moveline_obj = self.env['account.move.line']
        #  movelines = moveline_obj.search(
        #      [('partner_id', '=', partner.id),
        #       ('account_id.user_type_id.name', 'in', ['Receivable', 'Payable']),
        #       ('full_reconcile_id', '=', False)]
        #  )
        movelines = moveline_obj.search(
            [('partner_id', '=', partner.id),
             ('account_id.user_type_id.name', '=', 'Por cobrar'),
             ('full_reconcile_id', '=', False)]
        )
        today_dt = datetime.strftime(datetime.now().date(), DF)
        today = datetime.now().date()
        diff = 0
        for line in movelines:
            date_maturity = line.date_maturity
            diff = today - date_maturity
            if diff.days > partner.credit_time_limit:
                if not partner.over_credit_time_limit:
                    #  msg = 'Can not confirm Sale Order, Total mature due days ' \
                    #        '%s as on %s !\nCheck Partner Accounts or Credit Time ' \
                    #        'Limits !' % (diff.days, today_dt)

                    msg = """El cliente ha sobrepasado el tiempo de credito!
                             No se puede confirmar la orden de venta, el total de dias vencidos
                          {} hasta el {}!\nSolicite un pago, extienda el limite de crédito
                          o solicite una aprobación""".format(diff.days, today_dt)
                    raise UserError(_(msg))
        return True

    @api.multi
    def action_confirm(self):
        res = super(SaleOrder, self).action_confirm()
        if self.env.user.has_group('partner_credit_time_limit.credit_time_limit_manager'):
            return res

        for order in self:
            order.check_time_limit()
        return res
