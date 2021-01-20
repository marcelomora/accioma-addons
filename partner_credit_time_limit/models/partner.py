# See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class Partner(models.Model):
    _inherit = 'res.partner'

    credit_time_limit = fields.Integer()
    over_credit_time_limit = fields.Boolean('Allow to over credit time limit?', help="Allow all time.")
