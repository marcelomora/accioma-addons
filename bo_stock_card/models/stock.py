from collections import defaultdict

from odoo.addons import decimal_precision as dp
from odoo.tools import float_is_zero
from odoo import models, fields, api, _


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    set_date = fields.Datetime('Set date', default=False)

    def _get_quant_dest(self):
        # Considerar si hay multiples stock quants
        return self.env['stock.quant'].search([
            ('company_id', '=', self.move_id.company_id.id),
            ('product_id', '=', self.product_id.id),
            ('location_id', '=', self.location_dest_id.id),
            ('lot_id', '=', self.lot_id.id),
            ('package_id', '=', self.package_id.id)])

    def _get_quant(self):
        # Considerar si hay multiples stock quants
        return self.env['stock.quant'].search([
            ('company_id', '=', self.move_id.company_id.id),
            ('product_id', '=', self.product_id.id),
            ('location_id', '=', self.location_id.id),
            ('lot_id', '=', self.lot_id.id),
            ('package_id', '=', self.package_id.id)])

    def _get_price_unit_card(self):
        """ Returns the unit price to store on the quant per location"""
        return self._get_quant().standard_price

    def _get_price_unit_card_dest(self):
        """ Returns the unit price to store on the quant per location"""
        return self._get_quant_dest().standard_price

    @api.multi
    def edit_set_date(self):
        form_view = self.env.ref('bo_stock_card.set_date_form')
        return {
            'name': _('Set date'),
            'res_model': 'stock.move.line',
            'res_id': self.id,
            'views': [(form_view.id, 'form'), ],
            'type': 'ir.actions.act_window',
            'target': 'new'
        }

    def action_edit(self):
        pass


class StockMove(models.Model):
    _inherit = 'stock.move'

    invoice_id = fields.Many2one('account.invoice', compute='_compute_invoice_id')
    invoice_line_id = fields.Many2one('account.invoice.line', compute='_compute_invoice_line_id')

    def _compute_invoice_id(self):
        for move in self:
            if move.picking_id:
                move.invoice_id = self.env['account.invoice'].search([
                    ('origin', '=', move.picking_id.origin)], limit=1).id

    def _compute_invoice_line_id(self):
        for move in self:
            if move.picking_id:
                move.invoice_line_id = self.env['account.invoice.line'].search([
                    ('invoice_id.origin', '=', move.picking_id.origin),
                    ('product_id', '=', move.product_id.id)], limit=1).id

    @api.multi
    def product_price_update_before_done(self, forced_qty=None):
        res = super(StockMove, self).product_price_update_before_done(forced_qty)
        # self.product_price_update_before_done_card()
        return res

    @api.multi
    def product_price_update_before_done_card(self, forced_qty=None):
        tmpl_dict = defaultdict(lambda: 0.0)
        std_price_update = {}
        # adapt standard price on incomming moves if the product cost_method is 'average'
        for move in self.filtered(lambda mov: mov.location_dest_id.usage in ('internal') and mov.location_id.usage in ('internal') and mov.product_id.cost_method == 'average'):
            move_lines = move.move_line_ids.filtered(lambda ml: ml.location_id._should_be_valued() and ml.location_dest_id._should_be_valued() and not ml.owner_id)
            for move_line in move_lines:
                product_tot_qty_available = move_line._get_quant_dest().quantity + tmpl_dict[move.product_id.id]

                rounding = move_line.product_id.uom_id.rounding

                qty_done = 0.0
                if float_is_zero(product_tot_qty_available, precision_rounding=rounding):
                    new_std_price = move.price_unit or move_line._get_price_unit_card()
                elif float_is_zero(product_tot_qty_available + move_line.product_qty, precision_rounding=rounding):
                    new_std_price = move.price_unit or move_line._get_price_unit_card()
                else:
                    # Get the standard price
                    amount_unit = std_price_update.get((move.company_id.id, move.product_id.id)) or move_line._get_quant().standard_price
                    qty_done = move_line.product_uom_id._compute_quantity(move_line.qty_done, move.product_id.uom_id)
                    qty = forced_qty or qty_done
                    new_std_price = ((amount_unit * qty) + (move_line._get_price_unit_card_dest() * product_tot_qty_available)) / (product_tot_qty_available + qty_done)

                tmpl_dict[move.product_id.id] += qty_done
                if move_line._get_quant_dest():
                    # Write the standard price, as SUPERUSER_ID because a warehouse manager may not have the right to write on products
                    move_line._get_quant_dest().with_context(force_company=move.company_id.id).sudo().write({'standard_price': new_std_price})
                    std_price_update[move.company_id.id, move.product_id.id] = new_std_price
                else:
                    PriceHistory = self.env['product.price.history.card']
                    PriceHistory.create({
                        'company_id': move.company_id.id,
                        'product_id': move_line.product_id.id,
                        'location_id': move_line.location_dest_id.id,
                        'lot_id': move_line.lot_id.id,
                        'package_id': move_line.package_id.id,
                        'cost': new_std_price
                    })

        for move in self.filtered(lambda move: move.location_id.usage in ('supplier', 'production') and move.product_id.cost_method == 'average'):
            move_lines = move.move_line_ids.filtered(lambda ml: not ml.location_id._should_be_valued() and ml.location_dest_id._should_be_valued() and not ml.owner_id)
            for move_line in move_lines:

                if move_line.product_id.tracking != 'none':
                    picking_type_id = move_line.move_id.picking_type_id
                    if picking_type_id:
                        if picking_type_id.use_create_lots:
                            # If a picking type is linked, we may have to create a production lot on
                            # the fly before assigning it to the move line if the user checked both
                            # `use_create_lots` and `use_existing_lots`.
                            if move_line.lot_name and not move_line.lot_id:
                                lot = self.env['stock.production.lot'].create(
                                    {'name': move_line.lot_name, 'product_id': move_line.product_id.id}
                                )
                                move_line.write({'lot_id': lot.id})


                product_tot_qty_available = move_line._get_quant_dest().quantity + tmpl_dict[move.product_id.id]
                rounding = move_line.product_id.uom_id.rounding

                qty_done = 0.0
                if float_is_zero(product_tot_qty_available, precision_rounding=rounding):
                    new_std_price = move.price_unit or move_line._get_price_unit_card()
                elif float_is_zero(product_tot_qty_available + move_line.product_qty, precision_rounding=rounding):
                    new_std_price = move.price_unit or move_line._get_price_unit_card()
                else:
                    # Get the standard price
                    amount_unit = std_price_update.get((move.company_id.id, move.product_id.id)) or move_line._get_quant_dest().standard_price
                    qty_done = move_line.product_uom_id._compute_quantity(move_line.qty_done, move.product_id.uom_id)
                    qty = forced_qty or qty_done
                    new_std_price = ((amount_unit * product_tot_qty_available) + ((move.price_unit or move_line._get_price_unit_card()) * qty)) / (product_tot_qty_available + qty_done)

                tmpl_dict[move.product_id.id] += qty_done
                if move_line._get_quant_dest():
                    # Write the standard price, as SUPERUSER_ID because a warehouse manager may not have the right to write on products
                    move_line._get_quant_dest().with_context(force_company=move.company_id.id).sudo().write({'standard_price': new_std_price})
                    std_price_update[move.company_id.id, move.product_id.id] = new_std_price
                else:
                    PriceHistory = self.env['product.price.history.card']
                    PriceHistory.create({
                        'company_id': move.company_id.id,
                        'product_id': move_line.product_id.id,
                        'location_id': move_line.location_id.id,
                        'lot_id': move_line.lot_id.id,
                        'package_id': move_line.package_id.id,
                        'cost': new_std_price
                    })

    @api.multi
    def _get_price_unit_bo(self, total_type='total_included'):
        self.ensure_one()
        if self.purchase_line_id and self.product_id.id == self.purchase_line_id.product_id.id:
            line = self.purchase_line_id
            order = line.order_id
            price_unit = line.price_unit
            if line.taxes_id:
                price_unit = line.taxes_id.with_context(round=False).compute_all(price_unit, currency=line.order_id.currency_id, quantity=1.0)[total_type]
            if line.product_uom.id != line.product_id.uom_id.id:
                price_unit *= line.product_uom.factor / line.product_id.uom_id.factor
            if order.currency_id != order.company_id.currency_id:
                price_unit = order.currency_id.with_context(date=fields.Date.context_today(self)).compute(price_unit, order.company_id.currency_id, round=False)
            return price_unit
        return not self.company_id.currency_id.is_zero(self.price_unit) and self.price_unit or self.product_id.standard_price


class ProductPriceHistoryCard(models.Model):
    _name = 'product.price.history.card'
    _rec_name = 'datetime'
    _order = 'datetime desc'

    def _get_default_company_id(self):
        return self._context.get('force_company', self.env.user.company_id.id)

    company_id = fields.Many2one('res.company', string='Company', default=_get_default_company_id, required=True)
    location_id = fields.Many2one('stock.location', string='Location', required=True)
    product_id = fields.Many2one('product.product', 'Product', ondelete='cascade', required=True)
    lot_id = fields.Many2one('stock.production.lot', 'Lot/Serial Number', readonly=True)
    package_id = fields.Many2one(
        'stock.quant.package', 'Package',
        help='The package containing this quant', readonly=True)
    datetime = fields.Datetime('Date', default=fields.Datetime.now)
    cost = fields.Float('Cost', digits=dp.get_precision('Product Price History Card'))


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    standard_price = fields.Float(
        'Cost', company_dependent=True,
        digits=dp.get_precision('Product Price History Card'),
        groups="base.group_user",
        help="Cost used for stock valuation in standard price and as a first price to set in average/fifo. "
               "Also used as a base price for pricelists. "
               "Expressed in the default unit of measure of the product.")
    check_update_history_price_card = fields.Boolean(related='product_id.check_update_history_price_card')

    @api.multi
    def unlink(self):
        for quant in self:
            quant.update_card(self.company_id, self.location_id,
                              self.product_id, self.lot_id, self.package_id)
        return super(StockQuant, self).unlink()

    @api.multi
    def _set_standard_price(self, value):
        PriceHistory = self.env['product.price.history.card']
        for quant in self:
            PriceHistory.create({
                'company_id': self._context.get('force_company', self.env.user.company_id.id),
                'location_id': quant.location_id.id,
                'product_id': quant.product_id.id,
                'lot_id': quant.lot_id.id,
                'package_id': quant.package_id.id,
                'cost': value
            })

    @api.model
    def get_history_price(self, company_id, product_id, location_id, lot_id, package_id, date=None):
        history = self.env['product.price.history.card'].search([
            ('company_id', '=', company_id),
            ('location_id', '=', location_id),
            ('product_id', '=', product_id),
            ('lot_id', '=', lot_id),
            ('package_id', '=', package_id),
            ('datetime', '<=', date or fields.Datetime.now())], order='datetime desc,id desc', limit=1)
        return history.cost or 0.0

    @api.model
    def domain_stock_card(self, company_id, location_id, product_id, lot_id, package_id):
        return [('company_id', '=', company_id),
                ('location_id', '=', location_id),
                ('product_id', '=', product_id),
                ('lot_id', '=', lot_id),
                ('package_id', '=', package_id)]

    @api.model
    def _merge_update_card(self, stock_quants, bo_cards):
        stock_quants_dict = {(sq.company_id.id, sq.location_id.id, sq.product_id.id, sq.lot_id.id, sq.package_id.id): {
            'company_id': sq.company_id,
            'location_id': sq.location_id,
            'product_id': sq.product_id,
            'lot_id': sq.lot_id,
            'package_id': sq.package_id} for sq in stock_quants}

        bo_cards_dict = {(bc.company_id.id, bc.location_id.id, bc.product_id.id, bc.lot_id.id, bc.package_id.id): {
            'company_id': bc.company_id,
            'location_id': bc.location_id,
            'product_id': bc.product_id,
            'lot_id': bc.lot_id,
            'package_id': bc.package_id} for bc in bo_cards}

        stock_quants_dict.update(bo_cards_dict)
        for index, key in enumerate(stock_quants_dict.keys()):
            if not index:
                # Unique update price history card
                stock_quants_dict[key].get('product_id').pp_update_history_price_locations()
            self.update_card(stock_quants_dict[key].get('company_id'),
                             stock_quants_dict[key].get('location_id'), stock_quants_dict[key].get('product_id'),
                             stock_quants_dict[key].get('lot_id'), stock_quants_dict[key].get('package_id'))

    @api.model
    def update_card(self, company_id, location_id, product_id, lot_id, package_id):
        get_param = self.env['ir.config_parameter'].sudo().get_param
        tax_included = get_param('bo_stock_card.tax_included')
        move_line_domain = [
            ('product_id', '=', product_id.id),
            '|',
                ('location_id', '=', location_id.id),
                ('location_dest_id', '=', location_id.id),
            ('lot_id', '=', lot_id.id),
            '|',
                ('package_id', '=', package_id.id),
                ('result_package_id', '=', package_id.id),
            ('state', '=', 'done')
        ]
        domain = self.domain_stock_card(company_id.id, location_id.id, product_id.id, lot_id.id, package_id.id)
        card_obj = self.env['bo.card']
        card_objs = card_obj.search(domain)
        card_line_values = []
        end_date_process = False
        init_qty = 0
        end_cost_total = 0
        init_date_process = False
        create_bo_card = True
        if card_objs:
            create_bo_card = False
            move_line_domain.append(('date', '>', card_objs.end_date_process))
            init_qty = card_objs.last_end_quantity
            end_cost_total = card_objs.last_end_cost_total

        stock_move_lines = self.env['stock.move.line'].search(move_line_domain, order='date asc')
        sorted_move_lines = sorted(stock_move_lines, key=lambda a: a.set_date or a.date)
        for index, move_line in enumerate(sorted_move_lines):
            values = {}
            cost = self.get_history_price(
                company_id.id, product_id.id, location_id.id, lot_id.id, package_id.id,
                date=move_line.set_date or move_line.date)
            qty_done = move_line.qty_done

            if tax_included == 'True':
                price_unit = abs(move_line.move_id._get_price_unit_bo())
            else:
                price_unit = abs(move_line.move_id.price_unit)

            if location_id.id == move_line.location_dest_id.id:
                # Cuando realiza una tranferencia a una misma ubicación
                if move_line.location_id.id != move_line.location_dest_id.id:
                    init_qty += qty_done
                end_cost_total = init_qty * cost
                if index or not create_bo_card:
                    # If product return keep last standard_price
                    if move_line.move_id.origin_returned_move_id:
                        values.update({
                            'move_line_id': move_line.id,
                            'in_quantity': qty_done,
                            'in_cost': cost,
                            'in_cost_total': qty_done * cost,

                            'end_quantity': init_qty,
                            'end_cost': cost,
                            'end_cost_total': end_cost_total, 'io': 'in'})
                    else:
                        values.update({
                            'move_line_id': move_line.id,
                            'in_quantity': qty_done,
                            'in_cost': price_unit,
                            'in_cost_total': qty_done * price_unit,

                            'end_quantity': init_qty,
                            'end_cost': cost,
                            'end_cost_total': end_cost_total, 'io': 'in'})

                        if move_line.location_id.usage in ['internal', 'inventory'] and move_line.location_dest_id.usage == 'internal':
                            # Si es un ajuste de inventario obtiene el mismo precio anterior de la misma ubicación
                            if move_line.location_id.usage in ['inventory']:
                                cost = self.get_history_price(
                                    company_id.id, product_id.id, location_id.id, lot_id.id, package_id.id,
                                    date=move_line.set_date or move_line.date)
                            # Si es una tranferencia obtiene el ultimo costo de la ubicación origen
                            else:
                                cost = self.get_history_price(
                                    company_id.id, product_id.id, move_line.location_id.id, lot_id.id, package_id.id,
                                    date=move_line.set_date or move_line.date)
                            values.update({'in_cost': cost, 'in_cost_total': qty_done * cost})
                else:
                    init_date_process = move_line.set_date or move_line.date
                    values.update({
                        'move_line_id': move_line.id, 'end_quantity': init_qty, 'end_cost': cost,
                        'end_cost_total': end_cost_total, 'io': 'in'})
            else:
                init_qty -= qty_done
                end_cost_total = init_qty * cost
                values.update({
                    'move_line_id': move_line.id,
                    'out_quantity': qty_done,
                    'out_cost': cost,
                    'out_cost_total': qty_done * cost,

                    'end_quantity': init_qty,
                    'end_cost': cost,
                    'end_cost_total': end_cost_total, 'io': 'out'})

            card_line_values.append((0, 0, values))
            end_date_process = move_line.set_date or move_line.date

        if sorted_move_lines:
            if create_bo_card:
                card_obj.create({
                    'location_id': location_id.id,
                    'product_id': product_id.id,
                    'lot_id': lot_id.id,
                    'package_id': package_id.id,
                    'card_lines': card_line_values,
                    'last_end_quantity': init_qty,
                    'last_end_cost': cost,
                    'last_end_cost_total': end_cost_total,
                    'init_date_process': init_date_process,
                    'end_date_process': end_date_process})
            else:
                card_objs.write({
                    'card_lines': card_line_values,
                    'last_end_quantity': init_qty,
                    'last_end_cost': cost,
                    'last_end_cost_total': end_cost_total,
                    'end_date_process': end_date_process})

    def show_stock_card(self):
        # Before stock card
        if not self._context.get('update_card'):
            self.product_id.pp_update_history_price_locations()
        self.update_card(self.company_id, self.location_id, self.product_id, self.lot_id, self.package_id)
        action = self.env.ref('bo_stock_card.action_bo_card_line').read()[0]
        action['domain'] = [('id', 'in', self.env['bo.card'].search(
            self.domain_stock_card(
                self.env.user.company_id.id, self.location_id.id, self.product_id.id,
                self.lot_id.id, self.package_id.id)).card_lines.ids)]
        return action
