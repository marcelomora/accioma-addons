from ast import literal_eval

from odoo import models, fields, api
from odoo.tools import float_is_zero
from odoo.osv import expression


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    check_update_history_price_card = fields.Boolean(string='Check update history price')

    @api.model
    def default_get(self, fields):
        res = super(ProductTemplate, self).default_get(fields)
        res['check_update_history_price_card'] = True
        return res

    def update_history_price_locations(self):
        self.ensure_one()
        # Borra para hacer el recalculo
        if not self._context.get('not_force_recalculated'):
            self.env['product.price.history.card'].search(
                [('product_id', 'in', self.product_variant_ids.ids)]).unlink()
            self.env['bo.card'].search([('product_id', 'in', self.product_variant_ids.ids)]).unlink()
            for product in self.product_variant_ids:
                product.last_location_dict = False

        for product in self.product_variant_ids:
            product.pp_update_history_price_locations()

        self.check_update_history_price_card = True


class ProductProduct(models.Model):
    _inherit = 'product.product'

    last_location_dict = fields.Text(string='Last location dict')

    def pp_update_history_price_locations(self):
        self.ensure_one()
        ml_data = self.env['stock.move.line'].read_group(
            [('product_id', '=', self.id)],
            ['product_id', 'lot_id', 'package_id'],
            ['product_id', 'lot_id', 'package_id'], lazy=False)
        if_move_line = False
        get_param = self.env['ir.config_parameter'].sudo().get_param
        tax_included = get_param('bo_stock_card.tax_included')

        if self.last_location_dict:
            loc = literal_eval(self.last_location_dict)
            base_loc = loc.copy()

            for data in ml_data:
                move_lines = self.env['stock.move.line'].search(expression.AND([data['__domain'], [('date', '>', loc.get('move_line_last_datetime')), ('state', '=', 'done')]]), order='date asc')
                sorted_move_lines = sorted(move_lines, key=lambda a: a.set_date or a.date)
                # Verify not key add in dict loc
                loc.update({(sml.location_dest_id.id, sml.product_id.id, sml.lot_id.id, sml.package_id.id): {'product_tot_qty_available': 0.0, 'cost': 0.0,
                                                 'product_id': sml.product_id.id,
                                                 'usage': sml.location_dest_id.usage,
                                                 'lot_id': sml.lot_id.id,
                                                 'package_id': sml.package_id.id} for sml in sorted_move_lines if (sml.location_dest_id.id, sml.product_id.id, sml.lot_id.id, sml.package_id.id) not in loc})
                
                loc.update({(sml.location_id.id, sml.product_id.id, sml.lot_id.id, sml.package_id.id): {'product_tot_qty_available': 0.0, 'cost': 0.0,
                                                 'product_id': sml.product_id.id,
                                                 'usage': sml.location_id.usage,
                                                 'lot_id': sml.lot_id.id,
                                                 'package_id': sml.package_id.id} for sml in sorted_move_lines if (sml.location_id.id, sml.product_id.id, sml.lot_id.id, sml.package_id.id) not in loc})
                for index, ml in enumerate(sorted_move_lines):
                    qty_done = ml.qty_done
                    if tax_included == 'True':
                        price_unit = abs(ml.move_id._get_price_unit_bo())
                    else:
                        price_unit = abs(ml.move_id.price_unit)
                    rounding = ml.product_id.uom_id.rounding
                    if not index and (ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id) not in base_loc:
                        loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).update({'cost': price_unit})
                        price_used = ml.product_id.get_history_price(
                            self.env.user.company_id.id,
                            date=ml.set_date or ml.date,
                        )
                        # Save price_standar
                        self.env['product.price.history.card'].create({
                            'datetime': ml.set_date or ml.date,
                            'cost': loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).get('cost') or price_used,
                            'location_id': ml.location_dest_id.id,
                            'product_id': ml.product_id.id,
                            'lot_id': ml.lot_id.id,
                            'package_id': ml.package_id.id})
                    else:
                        if ml.location_id.usage not in ['internal', 'inventory'] and ml.location_dest_id.usage == 'internal':
                            product_tot_qty_available = loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).get('product_tot_qty_available')
                            new_std_price = loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).get('cost')
                            if float_is_zero(product_tot_qty_available, precision_rounding=rounding):
                                new_std_price = price_unit
                            elif float_is_zero(product_tot_qty_available + qty_done, precision_rounding=rounding):
                                new_std_price = price_unit
                            else:
                                new_std_price = ((new_std_price * product_tot_qty_available) + (price_unit * qty_done)) / (product_tot_qty_available + qty_done)
                            loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).update({'cost': new_std_price})
                            # Save price_standar
                            self.env['product.price.history.card'].create({
                                'datetime': ml.set_date or ml.date,
                                'cost': loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).get('cost'),
                                'location_id': ml.location_dest_id.id,
                                'product_id': ml.product_id.id,
                                'lot_id': ml.lot_id.id,
                                'package_id': ml.package_id.id})

                        if ml.location_id.usage == 'internal' and ml.location_dest_id.usage == 'internal':
                            product_tot_qty_available = loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).get('product_tot_qty_available')
                            price_unit = loc.get((ml.location_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).get('cost')

                            new_std_price = loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).get('cost')
                            if float_is_zero(product_tot_qty_available, precision_rounding=rounding):
                                new_std_price = price_unit
                            elif float_is_zero(product_tot_qty_available + qty_done, precision_rounding=rounding):
                                new_std_price = price_unit
                            else:
                                new_std_price = ((new_std_price * product_tot_qty_available) + (price_unit * qty_done)) / (product_tot_qty_available + qty_done)
                            loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).update({'cost': new_std_price})
                            # Save price_standar
                            self.env['product.price.history.card'].create({
                                'datetime': ml.set_date or ml.date,
                                'cost': loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).get('cost'),
                                'location_id': ml.location_dest_id.id,
                                'product_id': ml.product_id.id,
                                'lot_id': ml.lot_id.id,
                                'package_id': ml.package_id.id})

                    loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).update({
                        'product_tot_qty_available': loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).get('product_tot_qty_available') + qty_done})
                    loc.get((ml.location_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).update({
                        'product_tot_qty_available': loc.get((ml.location_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).get('product_tot_qty_available') - qty_done})

                    # Add last date move line
                    loc.update({'move_line_last_datetime': ml.set_date or ml.date})
                    if_move_line = True

                # Save last standard_price
                if sorted_move_lines:
                    for key in loc.keys():
                        if key != "move_line_last_datetime":
                            if loc.get(key).get('usage') == 'internal':
                                quant = self.env['stock.quant'].search([
                                    ('company_id', '=', self.env.user.company_id.id),
                                    ('location_id', '=', key[0]),
                                    ('product_id', '=', loc.get(key).get('product_id')),
                                    ('lot_id', '=', loc.get(key).get('lot_id')),
                                    ('package_id', '=', loc.get(key).get('package_id'))], limit=1)
                                new_std_price = loc.get(key).get('cost')
                                quant.with_context(not_create=True).write({'standard_price': new_std_price})
                                quant.with_context(update_card=True).show_stock_card()
            if if_move_line:
                # update dict loc
                self.last_location_dict = loc

        else:
            loc = False
            for data in ml_data:
                move_lines = self.env['stock.move.line'].search(data['__domain'] + [('state', '=', 'done')], order='date asc')
                sorted_move_lines = sorted(move_lines, key=lambda a: a.set_date or a.date)
                loc = {(sml.location_dest_id.id, sml.product_id.id, sml.lot_id.id, sml.package_id.id): {'product_tot_qty_available': 0.0, 'cost': 0.0,
                                                 'product_id': sml.product_id.id,
                                                 'usage': sml.location_dest_id.usage,
                                                 'lot_id': sml.lot_id.id,
                                                 'package_id': sml.package_id.id} for sml in sorted_move_lines}

                loc.update({(sml.location_id.id, sml.product_id.id, sml.lot_id.id, sml.package_id.id): {'product_tot_qty_available': 0.0, 'cost': 0.0,
                                                 'product_id': sml.product_id.id,
                                                 'usage': sml.location_id.usage,
                                                 'lot_id': sml.lot_id.id,
                                                 'package_id': sml.package_id.id} for sml in sorted_move_lines})

                for index, ml in enumerate(sorted_move_lines):
                    qty_done = ml.qty_done
                    qty_done = ml.qty_done
                    if tax_included == 'True':
                        price_unit = abs(ml.move_id._get_price_unit_bo())
                    else:
                        price_unit = abs(ml.move_id.price_unit)
                    rounding = ml.product_id.uom_id.rounding
                    if not index:
                        loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).update({'cost': price_unit})
                        price_used = ml.product_id.get_history_price(
                            self.env.user.company_id.id,
                            date=ml.set_date or ml.date,
                        )
                        # Save price_standar
                        self.env['product.price.history.card'].create({
                            'datetime': ml.set_date or ml.date,
                            'cost': loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).get('cost') or price_used,
                            'location_id': ml.location_dest_id.id,
                            'product_id': ml.product_id.id,
                            'lot_id': ml.lot_id.id,
                            'package_id': ml.package_id.id})
                    else:
                        if ml.location_id.usage not in ['internal', 'inventory'] and ml.location_dest_id.usage == 'internal':
                            product_tot_qty_available = loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).get('product_tot_qty_available')
                            new_std_price = loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).get('cost')
                            if float_is_zero(product_tot_qty_available, precision_rounding=rounding):
                                new_std_price = price_unit
                            elif float_is_zero(product_tot_qty_available + qty_done, precision_rounding=rounding):
                                new_std_price = price_unit
                            else:
                                new_std_price = ((new_std_price * product_tot_qty_available) + (price_unit * qty_done)) / (product_tot_qty_available + qty_done)
                            loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).update({'cost': new_std_price})
                            # Save price_standar
                            self.env['product.price.history.card'].create({
                                'datetime': ml.set_date or ml.date,
                                'cost': loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).get('cost'),
                                'location_id': ml.location_dest_id.id,
                                'product_id': ml.product_id.id,
                                'lot_id': ml.lot_id.id,
                                'package_id': ml.package_id.id})

                        if ml.location_id.usage == 'internal' and ml.location_dest_id.usage == 'internal':
                            product_tot_qty_available = loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).get('product_tot_qty_available')
                            price_unit = loc.get((ml.location_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).get('cost')

                            new_std_price = loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).get('cost')
                            if float_is_zero(product_tot_qty_available, precision_rounding=rounding):
                                new_std_price = price_unit
                            elif float_is_zero(product_tot_qty_available + qty_done, precision_rounding=rounding):
                                new_std_price = price_unit
                            else:
                                new_std_price = ((new_std_price * product_tot_qty_available) + (price_unit * qty_done)) / (product_tot_qty_available + qty_done)
                            loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).update({'cost': new_std_price})
                            # Save price_standar
                            self.env['product.price.history.card'].create({
                                'datetime': ml.set_date or ml.date,
                                'cost': loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).get('cost'),
                                'location_id': ml.location_dest_id.id,
                                'product_id': ml.product_id.id,
                                'lot_id': ml.lot_id.id,
                                'package_id': ml.package_id.id})

                    loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).update({
                        'product_tot_qty_available': loc.get((ml.location_dest_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).get('product_tot_qty_available') + qty_done})
                    loc.get((ml.location_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).update({
                        'product_tot_qty_available': loc.get((ml.location_id.id, ml.product_id.id, ml.lot_id.id, ml.package_id.id)).get('product_tot_qty_available') - qty_done})
                    # Add last date move line
                    loc.update({'move_line_last_datetime': ml.set_date or ml.date})

                # Save last standard_price
                if sorted_move_lines:
                    for key in loc.keys():
                        if key != "move_line_last_datetime":
                            if loc.get(key).get('usage') == 'internal':
                                quant = self.env['stock.quant'].search([
                                    ('company_id', '=', self.env.user.company_id.id),
                                    ('location_id', '=', key[0]),
                                    ('product_id', '=', loc.get(key).get('product_id')),
                                    ('lot_id', '=', loc.get(key).get('lot_id')),
                                    ('package_id', '=', loc.get(key).get('package_id'))], limit=1)
                                new_std_price = loc.get(key).get('cost')
                                quant.with_context(not_create=True).write({'standard_price': new_std_price})
                                quant.with_context(update_card=True).show_stock_card()
            # update dict loc
            self.last_location_dict = loc
