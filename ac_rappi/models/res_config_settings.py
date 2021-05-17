# -*- encoding: utf-8 -*-
# Copyright 2021 Accioma (https://accioma.com).
# @author marcelomora <java.diablo@gmail.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rappi_pricelist_id = fields.Many2one(
        'product.pricelist',
        'Rappi Pricelist',
        config_parameter="rappi.pricelist_id"
    )

