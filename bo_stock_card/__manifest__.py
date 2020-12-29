# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


{
    'name': 'Stock card',
    'version': '0.1',
    'author': 'Bitodoo',
    'category': 'Warehouse',
    'summary': 'Stock card',
    'website': 'https://www.bitodoo.com',
    'license': 'AGPL-3',
    'description': """
        Odoo stock card
    """,
    'depends': ['product', 'stock', 'stock_account'],
    'python': ["xlsxwriter"],
    'data': [
        'security/ir.model.access.csv',
        'data/card_data.xml',
        'views/stock_views.xml',
        'views/product_views.xml',
        'views/card_views.xml',
    ],
    'qweb': [],
    'price': 555.00,
    'currency': 'EUR',
    'live_test_url': 'https://youtu.be/8iqjBo0W3yg',
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'auto_install': False,
}
