import xlsxwriter
import base64
from io import BytesIO
import time
import pytz
from operator import itemgetter
import itertools

from odoo import models, fields, api, _
from odoo.addons import decimal_precision as dp


class StockCardWizard(models.TransientModel):
    _name = 'bo.stock.card.wizard'

    def _get_default_company_id(self):
        return self._context.get('force_company', self.env.user.company_id.id)

    def _default_start_date(self):
        start_date = time.strftime('%Y-%m-01') + ' 00:00:01'
        user_tz = pytz.timezone(self._context.get('tz') or self.env.user.tz or 'UTC')
        start_date = user_tz.localize(fields.Datetime.from_string(start_date)).astimezone(pytz.utc)
        return start_date

    name = fields.Char(string='Name period report')
    company_id = fields.Many2one('res.company', string='Company', default=_get_default_company_id, required=True)
    moves = fields.Boolean(
        string='Print product if you have movements', help='Print the product on the kardex if it has movements',
        default=True)
    #  date_from = fields.Datetime(
    #      string='Start date', default=_default_start_date,
    #      help='If you do not consider the start date, take from the beginning of the first movement')
    date_from = fields.Datetime(
        string='Start date',
        help='If you do not consider the start date, take from the beginning of the first movement')
    date_to = fields.Datetime(
        string='End date', help='If you do not consider the end date take until the current date')
    warehouse_ids = fields.Many2many('stock.warehouse', string='Warehouse')
    location_ids = fields.Many2many('stock.location', string='Location')
    product_ids = fields.Many2many('product.product', string='Product')
    categ_ids = fields.Many2many('product.category', string='Product category')
    out_file = fields.Binary(string="Out binary file")
    out_file_name = fields.Char(string='Out file')
    print_sale_purchase_ref = fields.Boolean(
        string='Add col. sale & purchase ref.', help='Add column sale & purchase reference name', )

    @api.onchange('warehouse_ids')
    def _onchange_warehouse_ids(self):
        if self.warehouse_ids:
            view_location_ids = [warehouse.view_location_id.id for warehouse in self.warehouse_ids]
            loc_ids = self.env['stock.location'].search([('location_id', 'in', view_location_ids)]).ids
            self.location_ids = [(6, 0, loc_ids)]
        else:
            self.location_ids = False

    def action_card_update(self):
        self.ensure_one()
        # Update standard price
        for pt in self.env['product.template'].search(
                [('check_update_history_price_card', '=', False), ('type', '=', 'product')]):
            pt.with_context(not_force_recalculated=True).update_history_price_locations()

        # Por implementar, agregar campo para generar el kardex solo de los productos activos
        # ('product_id.active', '=', True)

        # Update product card
        domain_stock_quant = [
            ('company_id', '=', self.company_id.id), ('location_id.usage', '=', 'internal'),
            ('product_id.active', '=', True)]
        if self.location_ids:
            domain_stock_quant.append(('location_id', 'in', self.location_ids.ids))
        if self.product_ids:
            domain_stock_quant.append(('product_id', 'in', self.product_ids.ids))

        # Falta optimizar cuando se define una fecha de inicio (date_from) ya no es necesario que recorra los stock
        # quants de fechas anteriores a date_from
        sq = self.env['stock.quant'].search(domain_stock_quant)
        bc = self.env['bo.card'].search(domain_stock_quant)
        # Por que los stocks quants suelen desaparecer cuando el producto ya no esta en stock
        sq._merge_update_card(sq, bc)

        return {
            'type': 'ir.actions.do_nothing',
        }

    @api.multi
    def generate_report(self):
        self.ensure_one()
        # Custom date format
        # For helper
        lang = self._context.get("lang")
        record_lang = self.env["res.lang"].search([("code", "=", lang)], limit=1)
        strftime_format = "%s %s" % (record_lang.date_format, record_lang.time_format)
        user_tz = pytz.timezone(self.env.context.get('tz') or self.env.user.tz or 'UTC')

        def format_datetime(dt):
            if dt:
                return fields.Datetime.from_string(dt).replace(
                    tzinfo=pytz.utc
                ).astimezone(user_tz).strftime(strftime_format)
            else:
                return ''

        output = BytesIO()
        DP = self.env.ref('product.decimal_product_uom')
        dpr = DP.precision_get('Product Price')
        # Product Unit of Measure (pum)
        dp_pum = DP.precision_get('Product Unit of Measure')
        num_format = '#,##0.%s' % ("0" * dpr)
        num_format_pum = '#,##0.%s' % ("0" * dp_pum)
        wb = xlsxwriter.Workbook(output, {
            'default_date_format': 'dd/mm/yyyy'
        })
        sheet = wb.add_worksheet('Stock Card')
        format_size_10 = wb.add_format({
            'size': 9,
            'font_name': 'Arial',
        })
        format_header_title = wb.add_format({
            'bold': True,
            'align': 'center',
            'size': 9
        })
        format_in = wb.add_format({
            'align': 'right',
            'valign': 'vright',
            'size': 9,
            'font_name': 'Arial',
            'fg_color': '#FFCCCC',
        })
        format_in_cost = wb.add_format({
            'align': 'right',
            'valign': 'vright',
            'size': 9,
            'font_name': 'Arial',
            'fg_color': '#FFCCCC',
            'num_format': num_format,
        })
        format_in_cost_init = wb.add_format({
            'align': 'right',
            'valign': 'vright',
            'size': 9,
            'font_name': 'Arial',
            'num_format': num_format,
        })
        format_out_cost = wb.add_format({
            'align': 'right',
            'valign': 'vright',
            'size': 9,
            'font_name': 'Arial',
            'fg_color': '#B4D3E7',
            'num_format': num_format,
        })
        format_out_cost_init = wb.add_format({
            'align': 'right',
            'valign': 'vright',
            'size': 9,
            'font_name': 'Arial',
            'num_format': num_format,
        })
        format_end_cost = wb.add_format({
            'align': 'right',
            'valign': 'vright',
            'size': 9,
            'font_name': 'Arial',
            'fg_color': '#FFCCCC',
            'num_format': num_format,
        })
        format_end_cost_init = wb.add_format({
            'align': 'right',
            'valign': 'vright',
            'size': 9,
            'font_name': 'Arial',
            'num_format': num_format,
        })
        format_sum_quantity = wb.add_format({
            'align': 'right',
            'valign': 'vright',
            'size': 9,
            'font_name': 'Arial',
            'bold': True,
            'border': 1,
            'num_format': num_format_pum
        })
        format_sum_total = wb.add_format({
            'align': 'right',
            'valign': 'vright',
            'size': 9,
            'font_name': 'Arial',
            'bold': True,
            'border': 1,
            'num_format': num_format,
        })
        sheet.set_column('A:A', 10)
        sheet.set_column('B:B', 13)
        sheet.set_column('C:C', 11)
        sheet.set_column('D:D', 11)
        sheet.set_column('E:E', 15)
        sheet.set_column('F:F', 13)
        sheet.set_column('G:G', 17)
        sheet.set_column('J:J', 15)
        sheet.set_column('K:K', 15)
        sheet.set_column('L:L', 12)
        sheet.set_column('M:M', 14)
        sheet.set_column('N:N', 14)
        sheet.set_column('R:R', 16)

        row = 0

        sheet.write(row, 0, _("Company:"), wb.add_format({'bold': True, 'size': 9}))
        sheet.write(row, 1, self.company_id.name)
        row += 1
        sheet.write(row, 0, _("Period:"), wb.add_format({'bold': True, 'size': 9}))
        sheet.write(row, 1, self.name or '- -', wb.add_format({'size': 9}))
        row += 2

        # Por implementar, agregar campo para generar el kardex solo de los productos activos
        # ('product_id.active', '=', True)
        domain = [('company_id', '=', self.company_id.id), ('product_id.active', '=', True)]
        domain_card_line = []
        if self.moves:
            sql = """
                SELECT bcl.card_id
                FROM bo_card_line bcl
                JOIN bo_card bc ON (bc.id=bcl.card_id)
                -- JOIN stock_move_line sml ON (sml.id = bcl.move_line_id)
                WHERE bc.company_id = %s AND bcl.datetime <= '%s'
                GROUP BY bcl.card_id""" % (self.company_id.id, self.date_to or fields.Datetime.now())
            if self.date_from:
                sql = """
                SELECT bcl.card_id
                FROM bo_card_line bcl
                JOIN bo_card bc ON (bc.id=bcl.card_id)
                -- JOIN stock_move_line sml ON (sml.id = bcl.move_line_id)
                WHERE bc.company_id = %s AND bcl.datetime >= '%s' AND bcl.datetime <= '%s'
                GROUP BY bcl.card_id""" % (self.company_id.id, self.date_from, self.date_to or fields.Datetime.now())

            self.env.cr.execute(sql)
            card_ids = [i[0] for i in self.env.cr.fetchall()]
            domain.append(('id', 'in', card_ids))

        if self.date_from:
            domain_card_line.append(('datetime', '>=', self.date_from))
        domain_card_line.append(('datetime', '<=', self.date_to or fields.Datetime.now()))

        if not self.warehouse_ids and not self.location_ids and not self.product_ids:
            pass
        elif self.location_ids and self.product_ids:
            domain.append(('location_id', 'in', self.location_ids.ids))
            domain.append(('product_id', 'in', self.product_ids.ids))
        elif self.location_ids and not self.product_ids:
            domain.append(('location_id', 'in', self.location_ids.ids))
        elif not self.location_ids and self.product_ids:
            domain.append(('product_id', 'in', self.product_ids.ids))
        if self.categ_ids:
            domain.append(('product_id.product_tmpl_id.categ_id', 'in', self.categ_ids.ids))

        bo_cards = self.env['bo.card'].search(domain)
        sorted_bo_cards = sorted(bo_cards, key=lambda a: (a.product_id.id, a.location_id.id))

        for card in sorted_bo_cards:
            col_A = 0
            col_B = 1
            col_C = 2
            col_D = 3
            col_E = 4
            col_F = 5
            col_G = 6
            col_H = 7
            col_I = 8
            col_J = 9
            col_K = 10
            col_L = 11
            col_M = 12
            col_N = 13
            col_O = 14
            col_P = 15
            col_ADD = 0

            sheet.write(row, col_A, _("Warehouse:"), wb.add_format({'bold': True, 'size': 9}))
            sheet.write(row, col_B, card.location_id.get_warehouse().name, wb.add_format({'size': 9}))
            row += 1
            sheet.write(row, col_A, _("Location:"), wb.add_format({'bold': True, 'size': 9}))
            sheet.write(row, col_B, card.location_id.name_get()[0][1], wb.add_format({'size': 9}))
            row += 1
            sheet.write(row, col_A, _("Product:"), wb.add_format({'bold': True, 'size': 9}))
            sheet.write(row, col_B, card.product_id.display_name, wb.add_format({'size': 9}))
            sheet.write(row, col_D, _("Category:"), wb.add_format({'bold': True, 'size': 9}))
            sheet.write(row, col_E, card.product_id.product_tmpl_id.categ_id.display_name, wb.add_format({'size': 9}))
            row += 1
            if card.lot_id:
                sheet.write(row, col_A, _("Lot/Serial Number:"), wb.add_format({'bold': True, 'size': 9}))
                sheet.write(row, col_B, card.lot_id.name, wb.add_format({'size': 9}))
                row += 1
            if card.package_id:
                sheet.write(row, col_A, _("Package:"), wb.add_format({'bold': True, 'size': 9}))
                sheet.write(row, col_B, card.package_id.name, wb.add_format({'size': 9}))
                row += 1
            sheet.write(row, col_A, _("Date from:"), wb.add_format({'bold': True, 'size': 9}))
            sheet.write(row, col_B, format_datetime(self.date_from) or "", wb.add_format({'size': 9}))
            sheet.write(row, col_C, _("Date to:"), wb.add_format({'bold': True, 'size': 9}))
            sheet.write(row, col_D, format_datetime(self.date_to) or "", wb.add_format({'size': 9}))
            row += 1
            sheet.write(row, col_A, _("Item"), format_header_title)
            sheet.write(row, col_B, _("Move"), format_header_title)
            if self.print_sale_purchase_ref:
                sheet.write(row, col_C, _("Sale"), format_header_title)
                sheet.write(row, col_D, _("Purchase"), format_header_title)
                sheet.set_column('H:H', 30)
                sheet.set_column('I:I', 30)
                col_ADD += 2
            sheet.write(row, col_C + col_ADD, _("Picking"), format_header_title)
            sheet.write(row, col_D + col_ADD, _("Invoice"), format_header_title)
            sheet.write(row, col_E + col_ADD, _("Date"), format_header_title)
            sheet.write(row, col_F + col_ADD, _("Location"), format_header_title)
            sheet.write(row, col_G + col_ADD, _("Location dest"), format_header_title)
            sheet.write(row, col_H + col_ADD, _("In quantity"), format_header_title)
            sheet.write(row, col_I + col_ADD, _("In cost"), format_header_title)
            sheet.write(row, col_J + col_ADD, _("In total cost"), format_header_title)

            sheet.write(row, col_K + col_ADD, _("Out quantity"), format_header_title)
            sheet.write(row, col_L + col_ADD, _("Out cost"), format_header_title)
            sheet.write(row, col_M + col_ADD, _("Out total cost"), format_header_title)

            sheet.write(row, col_N + col_ADD, _("End quantity"), format_header_title)
            sheet.write(row, col_O + col_ADD, _("End cost"), format_header_title)
            sheet.write(row, col_P + col_ADD, _("End total cost"), format_header_title)
            row += 1
            IN_QUANTITY = 0
            IN_COST = 0
            IN_COST_TOTAL = 0
            OUT_QUANTITY = 0
            OUT_COST = 0
            OUT_COST_TOTAL = 0
            END_QUANTITY = 0
            card_line_before = False

            if self.date_from:
                card_line_before = self.env['bo.card.line'].search([
                    ('datetime', '<', self.date_from), ('card_id', '=', card.id)], order='datetime DESC', limit=1)
                if card_line_before:
                    sheet.write(row, col_B, "- -", format_size_10)
                    if self.print_sale_purchase_ref:
                        sheet.write(row, col_C, "- -", format_size_10)
                        sheet.write(row, col_D, "- -", format_size_10)

                    sheet.write(row, col_C + col_ADD, "- -", format_size_10)
                    sheet.write(row, col_D + col_ADD, "- -", format_size_10)
                    sheet.write(row, col_E + col_ADD, "- -", format_size_10)
                    sheet.write(row, col_F + col_ADD, "- -", format_size_10)
                    sheet.write(row, col_G + col_ADD, "- -", format_size_10)

                    IN_QUANTITY += card_line_before.end_quantity
                    IN_COST += card_line_before.end_cost
                    IN_COST_TOTAL += card_line_before.end_cost_total
                    sheet.write(row, col_H + col_ADD, IN_QUANTITY, wb.add_format({'align': 'right', 'valign': 'vright',
                                                                        'size': 9, 'font_name': 'Arial',
                                                                        'num_format': num_format_pum}))
                    sheet.write(row, col_I + col_ADD, IN_COST, format_in_cost_init)
                    sheet.write(row, col_J + col_ADD, IN_COST_TOTAL, format_in_cost_init)
                    sheet.write(row, col_K + col_ADD, 0, wb.add_format({'align': 'right', 'valign': 'vright', 'size': 9,
                                                              'font_name': 'Arial', 'num_format': num_format_pum}))
                    sheet.write(row, col_L + col_ADD, 0, format_out_cost_init)
                    sheet.write(row, col_M + col_ADD, 0, format_out_cost_init)
                    sheet.write(row, col_N + col_ADD, card_line_before.end_quantity, wb.add_format({'align': 'right',
                                                                                          'valign': 'vright',
                                                                                          'size': 9,
                                                                                          'font_name': 'Arial',
                                                                                          'num_format': num_format_pum}))
                    sheet.write(row, col_O + col_ADD, card_line_before.end_cost, format_end_cost_init)
                    sheet.write(row, col_P + col_ADD, card_line_before.end_cost_total, format_end_cost_init)
                    row += 1

            for item, card_line in enumerate(self.env['bo.card.line'].search(
                    domain_card_line + [('card_id', '=', card.id)])):
                sheet.write(row, col_A, item, wb.add_format({'bold': True, 'align': 'center', 'size': 9}))
                sheet.write(row, col_B, card_line.move_line_id.reference, format_size_10)
                if self.print_sale_purchase_ref:
                    sheet.write(row, col_C, card_line.move_line_id.move_id.sale_line_id.order_id.name or '', format_size_10)
                    sheet.write(row, col_D, card_line.move_line_id.move_id.purchase_line_id.order_id.name or '', format_size_10)
                sheet.write(row, col_C + col_ADD, card_line.move_line_id.move_id.picking_id.name or '', format_size_10)
                sheet.write(row, col_D + col_ADD, card_line.move_line_id.move_id.invoice_id.number or '', format_size_10)
                sheet.write(row, col_E + col_ADD, format_datetime(card_line.move_line_id.date), format_size_10)
                sheet.write(row, col_F + col_ADD, card_line.move_line_id.location_id.name_get()[0][1], format_size_10)
                sheet.write(row, col_G + col_ADD, card_line.move_line_id.location_dest_id.name_get()[0][1], format_size_10)

                if not item and not card_line_before:
                    IN_QUANTITY += card_line.end_quantity
                    IN_COST += card_line.end_cost
                    IN_COST_TOTAL += card_line.end_cost_total
                    sheet.write(row, col_H + col_ADD, IN_QUANTITY, wb.add_format({'align': 'right', 'valign': 'vright',
                                                                        'size': 9, 'font_name': 'Arial',
                                                                        'fg_color': '#FFCCCC',
                                                                        'num_format': num_format_pum}))
                    sheet.write(row, col_I + col_ADD, IN_COST, format_in_cost)
                    sheet.write(row, col_J + col_ADD, IN_COST_TOTAL, format_in_cost)
                    sheet.write(row, col_K + col_ADD, 0, wb.add_format({'align': 'right', 'valign': 'vright', 'size': 9,
                                                              'font_name': 'Arial', 'fg_color': '#B4D3E7',
                                                              'num_format': num_format_pum}))
                    sheet.write(row, col_L + col_ADD, 0, format_out_cost)
                    sheet.write(row, col_M + col_ADD, 0, format_out_cost)
                    sheet.write(row, col_N + col_ADD, card_line.end_quantity, wb.add_format({'align': 'right', 'valign': 'vright',
                                                                                   'size': 9, 'font_name': 'Arial',
                                                                                   'fg_color': '#FFCCCC',
                                                                                   'num_format': num_format_pum}))
                    sheet.write(row, col_O + col_ADD, card_line.end_cost, format_end_cost)
                    sheet.write(row, col_P + col_ADD, card_line.end_cost_total, format_end_cost)
                else:
                    IN_QUANTITY += card_line.in_quantity
                    IN_COST += card_line.in_cost
                    IN_COST_TOTAL += card_line.in_cost_total
                    OUT_QUANTITY += card_line.out_quantity
                    OUT_COST += card_line.out_cost
                    OUT_COST_TOTAL += card_line.out_cost_total
                    sheet.write(row, col_H + col_ADD, card_line.in_quantity, wb.add_format({'align': 'right', 'valign': 'vright',
                                                                                  'size': 9, 'font_name': 'Arial',
                                                                                  'fg_color': '#FFCCCC',
                                                                                  'num_format': num_format_pum}))
                    sheet.write(row, col_I + col_ADD, card_line.in_cost, format_in_cost)
                    sheet.write(row, col_J + col_ADD, card_line.in_cost_total, format_in_cost)
                    sheet.write(row, col_K + col_ADD, card_line.out_quantity, wb.add_format({'align': 'right', 'valign':
                                                                                   'vright', 'size': 9,
                                                                                   'font_name': 'Arial',
                                                                                   'fg_color': '#B4D3E7',
                                                                                   'num_format': num_format_pum}))
                    sheet.write(row, col_L + col_ADD, card_line.out_cost, format_out_cost)
                    sheet.write(row, col_M + col_ADD, card_line.out_cost_total, format_out_cost)
                    sheet.write(row, col_N + col_ADD, card_line.end_quantity, wb.add_format({'align': 'right', 'valign': 'vright',
                                                                                   'size': 9, 'font_name': 'Arial',
                                                                                   'fg_color': '#FFCCCC',
                                                                                   'num_format': num_format_pum}))
                    sheet.write(row, col_O + col_ADD, card_line.end_cost, format_end_cost)
                    sheet.write(row, col_P + col_ADD, card_line.end_cost_total, format_end_cost)
                END_QUANTITY = card_line.end_quantity
                row += 1

            sheet.write(row, col_H + col_ADD, IN_QUANTITY, format_sum_quantity)
            sheet.write(row, col_I + col_ADD, IN_COST, format_sum_total)
            sheet.write(row, col_J + col_ADD, IN_COST_TOTAL, format_sum_total)
            sheet.write(row, col_K + col_ADD, OUT_QUANTITY, format_sum_quantity)
            sheet.write(row, col_L + col_ADD, OUT_COST, format_sum_total)
            sheet.write(row, col_M + col_ADD, OUT_COST_TOTAL, format_sum_total)
            sheet.write(row, col_N + col_ADD, END_QUANTITY, wb.add_format({'align': 'right', 'valign': 'vright',
                                                                 'size': 9, 'font_name': 'Arial', 'bold': True,
                                                                 'border': 1, 'num_format': num_format_pum}))

            row += 2

        wb.close()
        output.seek(0)

        self.out_file_name = "{} - {}.xlsx".format(self.company_id.name, 'Reporte Kardex')
        self.out_file = base64.encodestring(output.read())

        return {
            'type': 'ir.actions.do_nothing',
        }

    @api.multi
    def generate_report_inventory_valuation(self):
        self.ensure_one()
        # Custom date format
        # For helper
        lang = self._context.get("lang")
        record_lang = self.env["res.lang"].search([("code", "=", lang)], limit=1)
        strftime_format = "%s %s" % (record_lang.date_format, record_lang.time_format)
        user_tz = pytz.timezone(self.env.context.get('tz') or self.env.user.tz or 'UTC')

        def format_datetime(dt):
            if dt:
                return fields.Datetime.from_string(dt).replace(
                    tzinfo=pytz.utc
                ).astimezone(user_tz).strftime(strftime_format)
            else:
                return ''

        output = BytesIO()
        DP = self.env.ref('product.decimal_product_uom')
        # Product Unit of Measure (pum)
        dp_pum = DP.precision_get('Product Unit of Measure')
        num_format_pum = '#,##0.%s' % ("0" * dp_pum)
        wb = xlsxwriter.Workbook(output, {
            'default_date_format': 'dd/mm/yyyy'
        })
        sheet = wb.add_worksheet(_('inventory valuation'))
        format_header_title = wb.add_format({
            'bold': True,
            'align': 'center',
            'size': 10,
            'fg_color': '#2E75B6',
            'color': '#FFFFFF',
            'font_name': 'Arial',
        })

        format_line = wb.add_format({
            'align': 'right',
            'valign': 'vright',
            'size': 10,
            'font_name': 'Arial',
            'num_format': num_format_pum,
        })
        format_total_qty = wb.add_format({
            'align': 'right',
            'valign': 'vright',
            'size': 10,
            'bold': True,
            'num_format': num_format_pum,
        })

        sheet.set_column('A:A', 50)
        sheet.set_column('B:B', 12)
        sheet.set_column('C:C', 13)
        sheet.set_column('D:D', 13)
        sheet.set_column('E:E', 20)
        sheet.set_column('F:F', 11)
        sheet.set_column('G:G', 11)
        sheet.set_column('H:H', 15)
        sheet.set_column('I:I', 12)

        row = 0
        col_A = 0
        col_B = 1
        col_C = 2
        col_D = 3
        col_E = 4

        sheet.write(row, 0, _("Company:"), wb.add_format({'size': 10}))
        sheet.write(row, 1, self.company_id.name, wb.add_format({'bold': True, 'size': 10}))
        row += 1
        sheet.write(row, col_A, _("Period:"), wb.add_format({'size': 10}))
        sheet.write(row, col_B, self.name or '- -', wb.add_format({'bold': True, 'size': 10}))
        sheet.write(row, col_D, _('From:'), wb.add_format({'size': 10}))
        sheet.write(row, col_E, format_datetime(self.date_from) or _('Since its creation'), wb.add_format({'bold': True, 'size': 10}))
        row += 1
        sheet.write(row, col_A, _("Category:"), wb.add_format({'size': 10}))
        sheet.write(row, col_B, ", ".join([cat.name for cat in self.categ_ids]) if self.categ_ids else "all", wb.add_format({'bold': True, 'size': 10}))
        sheet.write(row, col_D, _('To:'), wb.add_format({'size': 10}))
        sheet.write(row, col_E, format_datetime(self.date_to) or _('To the present'), wb.add_format({'bold': True, 'size': 10}))
        row += 2

        # Por implementar, agregar campo para generar el kardex solo de los productos activos
        # ('product_id.active', '=', True)
        domain = [('company_id', '=', self.company_id.id), ('product_id.active', '=', True)]
        domain_card_line = []
        if self.moves:
            sql = """
            SELECT bcl.card_id
            FROM bo_card_line bcl
            JOIN bo_card bc ON (bc.id=bcl.card_id)
            JOIN stock_move_line sml ON (sml.id = bcl.move_line_id)
            WHERE bc.company_id = %s AND sml.date <= '%s'
            GROUP BY bcl.card_id""" % (self.company_id.id, self.date_from or fields.Datetime.now())

            self.env.cr.execute(sql)
            card_ids = [i[0] for i in self.env.cr.fetchall()]
            domain.append(('id', 'in', card_ids))

        if not self.warehouse_ids and not self.location_ids and not self.product_ids:
            pass
        elif self.location_ids and self.product_ids:
            domain.append(('location_id', 'in', self.location_ids.ids))
            domain.append(('product_id', 'in', self.product_ids.ids))
        elif self.location_ids and not self.product_ids:
            domain.append(('location_id', 'in', self.location_ids.ids))
        elif not self.location_ids and self.product_ids:
            domain.append(('product_id', 'in', self.product_ids.ids))
        if self.categ_ids:
            domain.append(('product_id.product_tmpl_id.categ_id', 'in', self.categ_ids.ids))

        vals = []
        for card in self.env['bo.card'].search(domain):
            END_QTY = 0
            END_COST = 0
            END_COST_TOTAL = 0

            card_line_before = self.env['bo.card.line'].search([
                ('datetime', '<=', self.date_from or fields.Datetime.now()), ('card_id', '=', card.id)], order='datetime DESC', limit=1)
            END_QTY += card_line_before.end_quantity
            END_COST += card_line_before.end_cost
            END_COST_TOTAL += card_line_before.end_cost_total

            vals.append({
                'location_id': card.location_id.id,
                'location_name': card.location_id.partner_id.street or card.location_id.name_get()[0][1] or "",
                'product_name': card.product_id.display_name, 'product_categ_id': card.product_id.categ_id.id,
                'product_categ_name': card.product_id.categ_id.name,
                'end_qty': END_QTY, 'end_cost': END_COST, 'end_cost_total': END_COST_TOTAL})

        sorted_loc_id = sorted(vals, key=itemgetter('location_id', 'product_name'))
        loc_group = [list(items) for key, items in itertools.groupby(sorted_loc_id, key=lambda x:x['location_id'])]

        for i in loc_group:
            sheet.write(row, col_A, _("Location:"), wb.add_format({'size': 9}))
            sheet.write(row, col_B, i[0].get('location_name', '- -'), wb.add_format({'bold': True, 'size': 9}))
            row += 1
            sheet.write(row, col_A, _("Product"), format_header_title)
            sheet.write(row, col_B, _("Qty"), format_header_title)
            sheet.write(row, col_C, _("Cost"), format_header_title)
            sheet.write(row, col_D, _("Cost total"), format_header_title)
            row += 1

            for j in i:
                sheet.write(row, col_A, j.get('product_name', '- -'), wb.add_format({
                    'font_name': 'Arial', 'align': 'left', 'size': 10}))
                sheet.write(row, col_B, j.get('end_qty', '- -'), format_line)
                sheet.write(row, col_C, j.get('end_cost', '- -'), format_line)
                sheet.write(row, col_D, j.get('end_cost_total', '- -'), format_line)
                row += 1
            row += 1

        wb.close()
        output.seek(0)

        file_name = 'ValoracionInventario'

        self.out_file_name = "{} - {}.xlsx".format(self.company_id.name, file_name)
        self.out_file = base64.encodestring(output.read())

        return {
            'type': 'ir.actions.do_nothing',
        }


class BoCard(models.Model):
    _name = 'bo.card'
    _description = 'Bitodoo card'

    def _get_default_company_id(self):
        return self._context.get('force_company', self.env.user.company_id.id)

    company_id = fields.Many2one('res.company', string='Company', default=_get_default_company_id, required=True)
    location_id = fields.Many2one('stock.location', string='Location')
    product_id = fields.Many2one('product.product', string='Product')
    lot_id = fields.Many2one(
        'stock.production.lot', 'Lot/Serial Number',
        ondelete='restrict', readonly=True)
    package_id = fields.Many2one(
        'stock.quant.package', 'Package',
        help='The package containing this quant', readonly=True, ondelete='restrict')
    owner_id = fields.Many2one(
        'res.partner', 'Owner',
        help='This is the owner of the quant', readonly=True)
    last_end_quantity = fields.Float('Last end quantity')
    last_end_cost = fields.Float('Last end cost')
    last_end_cost_total = fields.Float('Last end cost total')
    card_lines = fields.One2many('bo.card.line', 'card_id', 'Card lines')
    init_date_process = fields.Datetime('Init date process')
    end_date_process = fields.Datetime('End date process')

    _sql_constraints = [
        ('card_uniq', 'unique (company_id, location_id, product_id, lot_id, package_id)', _('The card must be unique !')),
    ]


class BoCardLine(models.Model):
    _name = 'bo.card.line'
    _description = 'Bitodoo card line'

    card_id = fields.Many2one('bo.card', 'Card', ondelete='cascade')
    card_location_id = fields.Many2one(related='card_id.location_id')
    move_line_id = fields.Many2one('stock.move.line', string='Move line')
    date = fields.Datetime(related='move_line_id.date', string='Date move')
    set_date = fields.Datetime(related='move_line_id.set_date')
    # For get before card line (Not get with fields date)
    datetime = fields.Datetime(string='Date card', compute='_compute_date_card', store=True)
    reference = fields.Char(related='move_line_id.reference')
    product_id = fields.Many2one(related='move_line_id.product_id')
    location_id = fields.Many2one(related='move_line_id.location_id')
    location_dest_id = fields.Many2one(related='move_line_id.location_dest_id')
    lot_id = fields.Many2one(related='move_line_id.lot_id')
    package_id = fields.Many2one(related='move_line_id.package_id')
    result_package_id = fields.Many2one(related='move_line_id.result_package_id')
    standard_price = fields.Float(
        'Standard price', compute='_compute_standard_price', digits=dp.get_precision('Product Price'))

    # In
    in_quantity = fields.Float('In quantity')
    in_cost = fields.Float('In cost', digits=dp.get_precision('Product Price History Card'))
    in_cost_total = fields.Float('In cost total', digits=dp.get_precision('Product Price'))

    # Out
    out_quantity = fields.Float('Out quantity')
    out_cost = fields.Float('Out cost', digits=dp.get_precision('Product Price History Card'))
    out_cost_total = fields.Float('Out cost total', digits=dp.get_precision('Product Price'))

    # End
    end_quantity = fields.Float('End quantity')
    # En la vista solo mostrar con la cantidad de dígitos de 'Product Price'
    end_cost = fields.Float('End cost', digits=dp.get_precision('Product Price History Card'))
    end_cost_total = fields.Float('End cost total', digits=dp.get_precision('Product Price'))

    io = fields.Char(string='I/O', size=5)

    @api.depends('move_line_id', 'date', 'set_date')
    def _compute_date_card(self):
        for i in self:
            i.datetime = i.set_date or i.date

    @api.depends('location_id', 'card_location_id', 'datetime')
    def _compute_standard_price(self):
        for i in self:
            i.standard_price = self.env['product.price.history.card'].search(
                [('location_id', '=', i.card_location_id.id), ('product_id', '=', i.product_id.id),
                 ('lot_id', '=', i.lot_id.id), ('package_id', '=', i.package_id.id),
                 ('datetime', '<=', i.date)], order='datetime desc,id desc', limit=1).cost
