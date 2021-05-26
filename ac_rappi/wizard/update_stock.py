# -*- encoding: utf-8 -*-
# Copyright 2021 Accioma (https://accioma.com).
# @author marcelomora <java.diablo@gmail.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import json
import requests as R
from datetime import datetime as DT
from datetime import timedelta as TD
from odoo import _, api, fields, models
from odoo.tools.float_utils import float_round
from odoo.exceptions import UserError

DB_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
L = logging.getLogger(__name__)
URL = 'https://services.grability.rappi.com/api/cpgs-integration/datasets'

class RappiSync(models.TransientModel):
    _name = 'rappi.sync'
    _description = 'Rappi Sync'

    send_all_products = fields.Boolean("Send all products")
    return_msg = fields.Char("Returned Message")

    def _prepare_data(self, product, price):
        quantities = product._compute_quantities_dict(None, None, None)
        tax_ids = product.taxes_id

        product_price = price
        list_price = product.list_price

        for tax in tax_ids:
            if tax.amount_type == 'percent':
                product_price += product_price * tax.amount / 100

        for tax in tax_ids:
            if tax.amount_type == 'percent':
                list_price += list_price * tax.amount / 100

        qty_available = quantities[product.id]['qty_available']

        data = {
            'store_id': "UIO-001",
            'trademark': "",
            'description': product.name,
            'is_available': product.active,
            'sale_type': "U",
            'id': product.default_code,
            'name': product.default_code,
            'discount': product.product_tmpl_id.rappi_discount,
            'price': float_round(list_price, 2),
            'stock': qty_available,
            'gtin': product.product_tmpl_id.barcode,
            'brand': "",
            'category_first_level': product.product_tmpl_id.categ_id.name,
            'category_second_level': "",
            'discount_price': float_round(product_price, 2),

        }

        #  discount number false Porcentaje de descuento de producto
        #  discount_start_at string false Rango de inicio del descuento de productos en
        #  discount_end_at string false Descuento de producto en el rango final en
        #  image_url string false

        L.info(data)

        return data

    def _send_data(self, records):
        """Send records to rappi api"""
        if not records:
            return

        token = self.env['ir.config_parameter'].sudo().get_param("rappi.token")
        payload = {'records': records}
        headers = {'content-type': 'application/json', 'Api_key': token}
        r = R.post(URL, data = json.dumps(payload), headers=headers)
        L.info(r.text)
        self.return_msg = r.text
        self.env['ir.config_parameter'].sudo().set_param("rappi.last.execution", DT.now().strftime(DB_DATETIME_FORMAT))

    def _update_all(self):
        products = self.env['product.product'].search(
            [('active', '=', True),
             ('sale_ok', '=', True),
             ('rappi_published', '=', True)
            ]
        )

        prices = self._compute_product_price(products)

        records = []
        for product in products:
            records.append(self._prepare_data(product, prices[product.id]))

        self._send_data(records)


    def update_stock(self):

        last_execution_time = self.env['ir.config_parameter'].sudo().get_param("rappi.last.execution")

        if not last_execution_time or self.send_all_products:
            self._update_all()
            return
        moves = self.env['stock.move'].search([('date', '>', last_execution_time)])
        products = [m.product_id for m in moves if m.product_id.rappi_published]
        prices = self._compute_product_price(products)
        records = []

        for p in products:
            data = self._prepare_data(p, prices[product.id])
            records.append(data)

        self._send_data(records)

    def _compute_product_price(self, products):
        pricelist_id = self.env['ir.config_parameter'].sudo().get_param("rappi.pricelist_id")
        pricelist = self.env['product.pricelist'].browse(pricelist_id)

        if not pricelist:
            raise UserError(_("Please configure Rappi Pricelist"))

        product_ids = products
        quantities = [1.0] * len(product_ids)
        partners = [False] * len(product_ids)

        return pricelist.sudo().get_products_price(product_ids, quantities, partners)








