# -*- encoding: utf-8 -*-
# Copyright 2021 Accioma (https://accioma.com).
# @author marcelomora <java.diablo@gmail.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    rappi_discount = fields.Integer("Rappi Discount", default=0)
    rappi_published = fields.Boolean("Published in Rappi")

    @api.multi
    def rappi_publish_button(self):
        self.ensure_one()
        self.rappi_published = not self.rappi_published


