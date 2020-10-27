#  -*- encoding: utf-8 -*-

from odoo import models, api, _
import time


class BankStatmentBalance(models.AbstractModel):

    _name = 'report.sg_bank_reconcilation_report.sg_bank_statment_report'


    @api.multi
    def get_blc(self, acc_id, st_date):
        self._cr.execute("select sum(debit) - sum(credit) from\
                        account_move_line l , account_move m  where \
                        l.move_id = m.id and l.account_id = %s and m.date >= %s \
                        and m.state='posted'",(acc_id.id,st_date ))
        acc_blc= self._cr.fetchall()
        if acc_blc and acc_blc[0] and acc_blc[0][0]:
            return acc_blc[0][0]
        else:
            return 0.00

    #==========================================================================
    # @api.model
    # def render_html(self, docids, data):
    #     report = self.env['report']
    #     if data == None:
    #         data = {}
    #     if not docids:
    #         docids = data.get('docids')
    #     st_ids = self.env['bank.acc.rec.statement'].browse(docids)
    #     docargs = {
    #         'doc_ids':docids,
    #         'doc_model':'bank.acc.rec.statement',
    #         'docs':st_ids,
    #         'data':data,
    #         'get_blc':self.get_blc,
    #         }
    #     return report.render('sg_bank_reconcilation_report.sg_bank_statment_report', docargs)
    #==========================================================================

    @api.model
    def _get_report_values(self, docids, data = None):
        self.model = self.env.context.get('active_model')
        docs = self.env['bank.acc.rec.statement'].browse(docids)
        return {'doc_ids': self.ids,
                'doc_model': self.model,
                'docs': docs,
                'time': time,
                'get_blc':self.get_blc,
                }
