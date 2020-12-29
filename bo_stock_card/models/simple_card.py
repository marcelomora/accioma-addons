import xlsxwriter
import base64
import pytz
from io import BytesIO
from operator import itemgetter
import itertools

from odoo import models, fields, api, _


class StockCardWizard(models.TransientModel):
    _inherit = 'bo.stock.card.wizard'

    print_family = fields.Boolean(
        string='Print family (Only apply in Simple card)',
    )

    @api.multi
    def generate_report_simple_card(self):
        self.ensure_one()

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
        sheet = wb.add_worksheet('Stock Card')
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
                GROUP BY bcl.card_id""" % (self.company_id.id, self.date_to or fields.Datetime.now())
            if self.date_from:
                sql = """
                SELECT bcl.card_id
                FROM bo_card_line bcl
                JOIN bo_card bc ON (bc.id=bcl.card_id)
                JOIN stock_move_line sml ON (sml.id = bcl.move_line_id)
                WHERE bc.company_id = %s AND sml.date >= '%s' AND sml.date <= '%s'
                GROUP BY bcl.card_id""" % (self.company_id.id, self.date_from, self.date_to or fields.Datetime.now())

            self.env.cr.execute(sql)
            card_ids = [i[0] for i in self.env.cr.fetchall()]
            domain.append(('id', 'in', card_ids))

        if self.date_from:
            domain_card_line.append(('date', '>=', self.date_from))
        domain_card_line.append(('date', '<=', self.date_to or fields.Datetime.now()))

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
            BEGINNING_BALANCE = 0
            IN_QUANTITY = 0
            OUT_QUANTITY = 0
            card_line_before = False

            if self.date_from:
                card_line_before = self.env['bo.card.line'].search([
                    ('datetime', '<', self.date_from), ('card_id', '=', card.id)], order='datetime DESC', limit=1)
                if card_line_before:
                    BEGINNING_BALANCE += card_line_before.end_quantity

            for item, card_line in enumerate(self.env['bo.card.line'].search(
                    domain_card_line + [('card_id', '=', card.id)])):
                if not item and not card_line_before:
                    BEGINNING_BALANCE += card_line.end_quantity
                else:
                    IN_QUANTITY += card_line.in_quantity
                    OUT_QUANTITY += card_line.out_quantity

            vals.append({
                'location_id': card.location_id.id,
                'location_name': card.location_id.partner_id.street or card.location_id.name_get()[0][1] or "",
                'product_name': card.product_id.display_name, 'beginning_balance': BEGINNING_BALANCE,
                'product_categ_id': card.product_id.categ_id.id, 'product_categ_name': card.product_id.categ_id.name,
                'in_quantity': IN_QUANTITY, 'out_quantity': OUT_QUANTITY,
                'total_quantity': (BEGINNING_BALANCE + IN_QUANTITY) - OUT_QUANTITY})

        if not self.print_family:
            sorted_loc_id = sorted(vals, key=itemgetter('location_id', 'product_name'))
            loc_group = [list(items) for key, items in itertools.groupby(sorted_loc_id, key=lambda x:x['location_id'])]

            for i in loc_group:
                sheet.write(row, col_A, _("Location:"), wb.add_format({'size': 9}))
                sheet.write(row, col_B, i[0].get('location_name', '- -'), wb.add_format({'bold': True, 'size': 9}))
                row += 1
                sheet.write(row, col_A, _("Product"), format_header_title)
                sheet.write(row, col_B, _("Init balance"), format_header_title)
                sheet.write(row, col_C, _("In"), format_header_title)
                sheet.write(row, col_D, _("Out"), format_header_title)
                sheet.write(row, 4, _("Final balance"), format_header_title)
                row += 1

                for j in i:
                    sheet.write(row, col_A, j.get('product_name', '- -'), wb.add_format({
                        'font_name': 'Arial', 'align': 'left', 'size': 10}))
                    sheet.write(row, col_B, j.get('beginning_balance', '- -'), format_line)
                    sheet.write(row, col_C, j.get('in_quantity', '- -'), format_line)
                    sheet.write(row, col_D, j.get('out_quantity', '- -'), format_line)
                    sheet.write(row, 4, j.get('total_quantity', '- -'), format_total_qty)
                    row += 1
                row += 1
        else:
            sorted_loc_id = sorted(vals, key=itemgetter('location_id', 'product_name'))
            loc_group = [list(items) for key, items in itertools.groupby(sorted_loc_id, key=itemgetter('location_id', 'product_categ_id'))]

            for i in loc_group:
                sheet.write(row, col_A, _("Location:"), wb.add_format({'size': 9}))
                sheet.write(row, col_B, i[0].get('location_name', '- -'), wb.add_format({'bold': True, 'size': 9}))
                row += 1
                sheet.write(row, col_A, _("Product"), format_header_title)
                sheet.write(row, col_B, _("Init balance"), format_header_title)
                sheet.write(row, col_C, _("In"), format_header_title)
                sheet.write(row, col_D, _("Out"), format_header_title)
                sheet.write(row, 4, _("Final balance"), format_header_title)
                row += 1
                sheet.write(row, col_A, _("Product Family (Category)"), wb.add_format({'size': 9}))
                sheet.write(row, col_B, i[0].get('product_categ_name', '- -'), wb.add_format({'bold': True, 'size': 9}))
                row += 1

                for j in i:
                    sheet.write(row, col_A, j.get('product_name', '- -'), wb.add_format({
                        'font_name': 'Arial', 'align': 'left', 'size': 10}))
                    sheet.write(row, col_B, j.get('beginning_balance', '- -'), format_line)
                    sheet.write(row, col_C, j.get('in_quantity', '- -'), format_line)
                    sheet.write(row, col_D, j.get('out_quantity', '- -'), format_line)
                    sheet.write(row, 4, j.get('total_quantity', '- -'), format_total_qty)
                    row += 1
                row += 1

        wb.close()
        output.seek(0)

        file_name = 'ReportSimpleStockCard'
        if self.print_family:
            file_name = 'FamilyReportSimpleStockCard'

        self.out_file_name = "{} - {}.xlsx".format(self.company_id.name, file_name)
        self.out_file = base64.encodestring(output.read())

        return {
            'type': 'ir.actions.do_nothing',
        }

    @api.multi
    def generate_report_simple_card_2(self):
        self.ensure_one()

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
        sheet = wb.add_worksheet('Stock Card')
        format_header_title = wb.add_format({
            'bold': True,
            'align': 'center',
            'size': 10,
            'font_name': 'Arial',
            'fg_color': '#2E75B6',
            'color': '#FFFFFF',
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
            'font_name': 'Arial',
            'num_format': num_format_pum,
            'fg_color': '#2E75B6',
            'color': '#FFFFFF',
        })

        sheet.set_column('A:A', 50)
        sheet.set_column('B:B', 12)
        sheet.set_column('C:C', 13)
        sheet.set_column('D:D', 13)
        sheet.set_column('E:E', 13)
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
        col_F = 5

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
                GROUP BY bcl.card_id""" % (self.company_id.id, self.date_to or fields.Datetime.now())
            if self.date_from:
                sql = """
                SELECT bcl.card_id
                FROM bo_card_line bcl
                JOIN bo_card bc ON (bc.id=bcl.card_id)
                JOIN stock_move_line sml ON (sml.id = bcl.move_line_id)
                WHERE bc.company_id = %s AND sml.date >= '%s' AND sml.date <= '%s'
                GROUP BY bcl.card_id""" % (self.company_id.id, self.date_from, self.date_to or fields.Datetime.now())

            self.env.cr.execute(sql)
            card_ids = [i[0] for i in self.env.cr.fetchall()]
            domain.append(('id', 'in', card_ids))

        if self.date_from:
            domain_card_line.append(('date', '>=', self.date_from))
        domain_card_line.append(('date', '<=', self.date_to or fields.Datetime.now()))

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
            BEGINNING_BALANCE = 0
            IN_QUANTITY = 0
            OUT_QUANTITY = 0
            OUT_QUANTITY_CUSTOMER = 0
            card_line_before = False

            if self.date_from:
                card_line_before = self.env['bo.card.line'].search([
                    ('datetime', '<', self.date_from), ('card_id', '=', card.id)], order='datetime DESC', limit=1)
                if card_line_before:
                    BEGINNING_BALANCE += card_line_before.end_quantity

            for item, card_line in enumerate(self.env['bo.card.line'].search(
                    domain_card_line + [('card_id', '=', card.id)])):
                if not item and not card_line_before:
                    BEGINNING_BALANCE += card_line.end_quantity
                else:
                    if card_line.io == 'in':
                        IN_QUANTITY += card_line.in_quantity
                    else:
                        if card_line.location_dest_id.usage in ['customer']:
                            OUT_QUANTITY_CUSTOMER += card_line.out_quantity
                        else:
                            OUT_QUANTITY += card_line.out_quantity
            vals.append({
                'location_id': card.location_id.id,
                'location_name': card.location_id.partner_id.street or card.location_id.name_get()[0][1] or "",
                'product_name': card.product_id.display_name, 'beginning_balance': BEGINNING_BALANCE,
                'product_categ_id': card.product_id.categ_id.id, 'product_categ_name': card.product_id.categ_id.name,
                'product_tmpl_id': card.product_id.product_tmpl_id.id,
                'in_quantity': IN_QUANTITY, 'out_quantity': - OUT_QUANTITY,
                'out_quantity_customer': - OUT_QUANTITY_CUSTOMER,
                'total_quantity': (BEGINNING_BALANCE + IN_QUANTITY) - (OUT_QUANTITY + OUT_QUANTITY_CUSTOMER)})

        if not self.print_family:
            sorted_loc_id = sorted(vals, key=itemgetter('location_id', 'product_name'))
            loc_group = [list(items) for key, items in itertools.groupby(sorted_loc_id, key=lambda x:x['location_id'])]

            for i in loc_group:
                sheet.write(row, col_A, _("Location:"), wb.add_format({'size': 9}))
                sheet.write(row, col_B, i[0].get('location_name', '- -'), wb.add_format({'bold': True, 'size': 9}))
                row += 1
                sheet.write(row, col_A, _("Product"), format_header_title)
                sheet.write(row, col_B, _("Quantity"), format_header_title)
                sheet.write(row, col_C, _("In"), format_header_title)
                sheet.write(row, col_D, _("Out"), format_header_title)
                sheet.write(row, col_E, _("Sale."), format_header_title)
                sheet.write(row, col_F, _("Total"), format_header_title)
                row += 1
                sorted_i = sorted(i, key=itemgetter('product_name'))
                # Group product variant gpv
                for gpv in [list(items) for key, items in itertools.groupby(sorted_i, key=lambda x:x['product_tmpl_id'])]:
                    # Product variant pv
                    total_group_product_tmpl = 0
                    row_init = row
                    for pv in gpv:
                        sheet.write(row, col_A, pv.get('product_name', '- -'), wb.add_format({
                            'font_name': 'Arial', 'align': 'left', 'size': 10}))
                        sheet.write(row, col_B, pv.get('beginning_balance', 0), format_line)
                        sheet.write(row, col_C, pv.get('in_quantity', 0), format_line)
                        sheet.write(row, col_D, pv.get('out_quantity', 0), format_line)
                        sheet.write(row, col_E, pv.get('out_quantity_customer', 0), format_line)
                        sheet.write(row, col_F, pv.get('total_quantity', 0), format_line)
                        total_group_product_tmpl += pv.get('total_quantity', 0)
                        row += 1
                    sheet.write(row, col_E, 'Total', format_total_qty)
                    sheet.write(row, col_F, '=SUM(F%s:F%s)' % (row_init + 1, row), format_total_qty)
                    row += 1
                row += 1
        else:
            sorted_loc_id = sorted(vals, key=itemgetter('location_id', 'product_name'))
            loc_group = [list(items) for key, items in itertools.groupby(sorted_loc_id, key=itemgetter('location_id', 'product_categ_id'))]

            for i in loc_group:
                sheet.write(row, col_A, _("Location:"), wb.add_format({'size': 9}))
                sheet.write(row, col_B, i[0].get('location_name', '- -'), wb.add_format({'bold': True, 'size': 9}))
                row += 1
                sheet.write(row, col_A, _("Product"), format_header_title)
                sheet.write(row, col_B, _("Quantity"), format_header_title)
                sheet.write(row, col_C, _("In"), format_header_title)
                sheet.write(row, col_D, _("Out"), format_header_title)
                sheet.write(row, col_E, _("Sale."), format_header_title)
                sheet.write(row, col_F, _("Total"), format_header_title)
                row += 1
                sheet.write(row, col_A, _("Product Family (Category)"), wb.add_format({'size': 9}))
                sheet.write(row, col_B, i[0].get('product_categ_name', '- -'), wb.add_format({'bold': True, 'size': 9}))
                row += 1

                sorted_i = sorted(i, key=itemgetter('product_name'))
                # Group product variant gpv
                for gpv in [list(items) for key, items in itertools.groupby(sorted_i, key=lambda x:x['product_tmpl_id'])]:
                    # Product variant pv
                    total_group_product_tmpl = 0
                    row_init = row
                    for pv in gpv:
                        sheet.write(row, col_A, pv.get('product_name', '- -'), wb.add_format({
                            'font_name': 'Arial', 'align': 'left', 'size': 10}))
                        sheet.write(row, col_B, pv.get('beginning_balance', 0), format_line)
                        sheet.write(row, col_C, pv.get('in_quantity', 0), format_line)
                        sheet.write(row, col_D, pv.get('out_quantity', 0), format_line)
                        sheet.write(row, col_E, pv.get('out_quantity_customer', 0), format_line)
                        sheet.write(row, col_F, pv.get('total_quantity', 0), format_line)
                        total_group_product_tmpl += pv.get('total_quantity', 0)
                        row += 1
                    sheet.write(row, col_E, 'Total', format_total_qty)
                    sheet.write(row, col_F, '=SUM(F%s:F%s)' % (row_init + 1, row), format_total_qty)
                    row += 1
                row += 1

        wb.close()
        output.seek(0)

        file_name = 'ReportSimpleStockCard_2'
        if self.print_family:
            file_name = 'FamilyReportSimpleStockCard_2'

        self.out_file_name = "{} - {}.xlsx".format(self.company_id.name, file_name)
        self.out_file = base64.encodestring(output.read())

        return {
            'type': 'ir.actions.do_nothing',
        }
