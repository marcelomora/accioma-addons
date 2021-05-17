{
    "name": "Rappi Integration",
    "summary": "Rappi Integration for stock updating",
    "version": "12.0.1.2.0",
    "category": "Ecommerce Integration",
    "website": "www.accioma.com",
    "author": "Marcelo Mora (Accioma)",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "external_dependencies": {
        "python": [],
        "bin": [],
    },
    "depends": [
        "stock", "sale",
    ],
    "data": [
        "views/product_views.xml",
        "views/res_config_settings_views.xml",
        "wizard/update_stock_views.xml",
    ],
    "demo": [
    ],
    "qweb": [
    ]
}
