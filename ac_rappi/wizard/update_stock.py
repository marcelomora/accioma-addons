# -*- encoding: utf-8 -*-
# Copyright 2021 Accioma (https://accioma.com).
# @author marcelomora <java.diablo@gmail.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import json
import requests as R
from odoo import _, api, fields, models
from datetime import datetime as DT
from datetime import timedelta as TD

DB_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
L = logging.getLogger(__name__)
URL = 'https://services.grability.rappi.com/api/cpgs-integration/datasets'
TOKEN_TEST = '6bc37261-7615-47c0-b6d8-91c23b747cea'

class RappiSync(models.TransientModel):
    _name = 'rappi.sync'
    _description = 'Rappi Sync'

    def update_stock(self):
        dt = DT.now() - TD(minutes=1440)
        L.info(dt.strftime(DB_DATETIME_FORMAT))

        moves = self.env['stock.move'].search([('date', '>', dt.strftime(DB_DATETIME_FORMAT))])
        payload = {'records': []}
        headers = {'content-type': 'application/json', 'Api_key': TOKEN_TEST}

        for m in moves:
            quantities = m.product_id._compute_quantities_dict(None, None, None)
            qty_available = quantities[m.product_id.id]['qty_available']
            L.info("Product Qty {} {}".format(quantities, qty_available))
            data = {
                'store_id': "1",
                'trademark': "",
                'description': m.product_id.name,
                'is_available': m.product_id.active,
                'sale_type': "U",
                'id': m.product_id.default_code,
                'name': m.product_id.default_code,
                'price': m.product_id.list_price,
                'stock': qty_available,
            }

            payload['records'].append(data)
            L.info(payload)
            r = R.post(URL, data = json.dumps(payload), headers=headers)
            L.info(r.text)






