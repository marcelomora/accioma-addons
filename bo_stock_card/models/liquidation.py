# -*- coding: utf-8 -*-

import xlsxwriter
import base64
from io import BytesIO
from odoo import fields, models, _


class LiquidationWizard(models.TransientModel):
    _inherit = 'bo.stock.card.wizard'

    def get_domain(self):
        domain_card_line = [('card_id.company_id', '=', self.company_id.id)]

        if self.date_from:
            domain_card_line.append(('date', '>=', self.date_from))
        domain_card_line.append(('date', '<=', self.date_to or fields.Datetime.now()))

        if not self.warehouse_ids and not self.location_ids and not self.product_ids:
            pass
        elif self.location_ids and self.product_ids:
            domain_card_line.append(('card_id.location_id', 'in', self.location_ids.ids))
            domain_card_line.append(('card_id.product_id', 'in', self.product_ids.ids))
        elif self.location_ids and not self.product_ids:
            domain_card_line.append(('card_id.location_id', 'in', self.location_ids.ids))
        elif not self.location_ids and self.product_ids:
            domain_card_line.append(('card_id.product_id', 'in', self.product_ids.ids))
        if self.categ_ids:
            domain_card_line.append(('card_id.product_id.product_tmpl_id.categ_id', 'in', self.categ_ids.ids))

        return domain_card_line

    def get_header_labels(self):
        return [
            (_('Invoice Date'), {}),
            (_('Move Location'), {}),
            (_('Invoice User'), {}),
            (_('Move Product'), {}),
            (_('Invoice Unit Price'), {}),
            (_('Invoice Quantity'), {}),
            (_('Invoice UOM'), {}),
            (_('Invoice Total'), {}),
            (_('Invoice Journal'), {}),
            (_('Invoice #'), {}),
            (_('Invoice Client'), {}),
            (_('Invoice State'), {}),
        ]

    def get_record_columns(self, card_line):
        return [
            (card_line.move_line_id.move_id.invoice_line_id.invoice_id.date_invoice or '', 'text', {}),
            (card_line.location_id.name_get()[0][1] or '', 'text', {}),
            (card_line.move_line_id.move_id.invoice_line_id.invoice_id.user_id.name, 'text', {}),
            (card_line.move_line_id.move_id.product_id.display_name, 'text', {}),
            (card_line.move_line_id.move_id.invoice_line_id.price_unit, 'num', {'num_format': '#,##0.000000'}),
            (card_line.move_line_id.move_id.invoice_line_id.quantity, 'num', {}),
            (card_line.move_line_id.move_id.invoice_line_id.uom_id.name, 'text', {}),
            (card_line.move_line_id.move_id.invoice_line_id.price_total, 'num', {'num_format': '#,##0.000000'}),
            (card_line.move_line_id.move_id.invoice_line_id.invoice_id.journal_id.name, 'text', {}),
            (card_line.move_line_id.move_id.invoice_line_id.invoice_id.number, 'text', {}),
            (card_line.move_line_id.move_id.invoice_line_id.invoice_id.partner_id.name, 'text', {}),
            (dict(card_line.move_line_id.move_id.invoice_line_id.invoice_id._fields['state']._description_selection(card_line.move_line_id.move_id.invoice_line_id.invoice_id.env)).get(card_line.move_line_id.move_id.invoice_line_id.invoice_id.state), 'text', {}),
        ]

    def generate_report_liquidation(self):
        self.ensure_one()
        output = BytesIO()
        wb = xlsxwriter.Workbook(output, {
            'default_date_format': 'dd/mm/yyyy'
        })
        sheet = wb.add_worksheet('Report liquidation')
        sheet.set_row(0, 25)
        sheet.set_row(4, 30)
        sheet.set_column('A:A', 10)
        sheet.set_column('B:B', 30)
        sheet.set_column('C:C', 15)
        sheet.set_column('D:D', 35)
        sheet.set_column('E:E', 12)
        sheet.set_column('F:F', 12)
        sheet.set_column('G:G', 12)
        sheet.set_column('H:H', 12)
        sheet.set_column('I:I', 15)
        sheet.set_column('J:J', 15)
        sheet.set_column('K:K', 30)
        sheet.set_column('L:L', 35)
        sheet.set_column('M:M', 12)
        sheet.set_column('N:N', 15)
        sheet.set_column('O:O', 15)
        sheet.set_column('P:P', 15)
        sheet.set_column('Q:Q', 40)
        sheet.set_column('R:R', 16)
        sheet.set_column('S:S', 50)
        sheet.set_column('T:T', 50)
        format_header_center = {
            'align': 'center',
            'valign': 'vcenter',
            'size': 10,
            'font_name': 'Arial',
            'bold': True,
            'text_wrap': True,
            'fg_color': '#2E75B6',
            'color': '#FFFFFF'
        }
        format_values_center = {
            'align': 'center',
            'valign': 'vcenter',
            'size': 8,
            'font_name': 'Arial',
        }
        format_values_right = {
            'align': 'right',
            'valign': 'vright',
            'size': 8,
            'font_name': 'Arial',
            'num_format': '#,##0.00',
        }
        format_header_label = wb.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'bold': True,
            'size': 8,
            'font_name': 'Arial',
        })
        format_title_header = wb.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'bold': True,
            'size': 14,
            'font_name': 'Arial',
        })

        domain = self.get_domain()
        records = self.env['bo.card.line'].search(domain, order='datetime ASC')

        row = 0
        sheet.write(row, 0, _("Company:"), format_header_label)
        sheet.merge_range(row, 1, row, 9, self.company_id.name, format_title_header)
        row += 2
        sheet.write(row, 2, _("Start date"), format_header_label)
        sheet.write(row, 3, self.date_from or '', format_header_label)
        sheet.write(row, 5, _("End date"), format_header_label)
        sheet.write(row, 6, self.date_to or '', format_header_label)
        sheet.write(row, 8, _("Category:"), wb.add_format({'size': 10}))
        sheet.write(row, 9, ", ".join([cat.name for cat in self.categ_ids]) if self.categ_ids else "all", format_header_label)
        row += 2

        for i, label in enumerate(self.get_header_labels()):
            sheet.write(4, i, label[0], wb.add_format(dict(format_header_center, **label[1])))
        row = 5
        for card_line in records:
            for i, rec in enumerate(self.get_record_columns(card_line)):
                if rec[1] == 'text':
                    sheet.write(row, i, rec[0] or '', wb.add_format(dict(format_values_center, **rec[2])))
                else:
                    sheet.write(row, i, rec[0], wb.add_format(dict(format_values_right, **rec[2])))
            row += 1

        wb.close()
        output.seek(0)
        self.out_file_name = "{} - {}.xlsx".format(self.company_id.name, _('Report liquidation'))
        self.out_file = base64.encodestring(output.read())

        return {'type': 'ir.actions.do_nothing'}
