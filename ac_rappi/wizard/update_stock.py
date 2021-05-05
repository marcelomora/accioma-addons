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

DB_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
L = logging.getLogger(__name__)
URL = 'https://services.grability.rappi.com/api/cpgs-integration/datasets'

class RappiSync(models.TransientModel):
    _name = 'rappi.sync'
    _description = 'Rappi Sync'

    def _prepare_data(self, product):
        quantities = product._compute_quantities_dict(None, None, None)
        tax_ids = product.taxes_id
        price = product.list_price
        for tax in tax_ids:
            if tax.amount_type == 'percent':
                price += price * tax.amount / 100
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
            'price': float_round(price, 2),
            'stock': qty_available,
        }

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
        self.env['ir.config_parameter'].sudo().set_param("rappi.last.execution", DT.now().strftime(DB_DATETIME_FORMAT))

    def _update_all(self):
        products = self.env['product.product'].search(
            [('active', '=', True), ('sale_ok', '=', True)]
        )
        records = []
        for product in products:
            records.append(self._prepare_data(product))

        self._send_data(records)


    def update_stock(self):

        last_execution_time = self.env['ir.config_parameter'].sudo().get_param("rappi.last.execution")

        if not last_execution_time:
            self._update_all()
            return
        moves = self.env['stock.move'].search([('date', '>', last_execution_time)])
        records = []

        for m in moves:
            data = self._prepare_data(m.product_id)
            records.append(data)

        self._send_data(records)






