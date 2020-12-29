# -*- encoding: utf-8 -*-

from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.main import serialize_exception
from odoo.addons.web.controllers.main import content_disposition


class ReportBinary(http.Controller):

    @http.route('/web/binary/download_bo_report_stock_card', type='http', auth='user')
    @serialize_exception
    def download_bo_report_stock_card(self, model, record_id, filename=None, **kw):
        obj = request.env[model]
        record_id = obj.browse([int(record_id)])
        filecontent = record_id.get_bo_report_stock_card()
        response = request.make_response(filecontent, [
            ('Content-Type', 'application/octet-stream;charset=utf-8;'),
            ('Content-Disposition', content_disposition(filename))
        ])
        return response

    @http.route('/web/binary/download_bo_report_simple_stock_card', type='http', auth='user')
    @serialize_exception
    def download_bo_report_simple_stock_card(self, model, record_id, filename=None, **kw):
        obj = request.env[model]
        record_id = obj.browse([int(record_id)])
        filecontent = record_id.get_bo_report_simple_stock_card()
        response = request.make_response(filecontent, [
            ('Content-Type', 'application/octet-stream;charset=utf-8;'),
            ('Content-Disposition', content_disposition(filename))
        ])
        return response
