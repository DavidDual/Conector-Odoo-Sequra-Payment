# -*- coding: utf-8 -*-

{
    'name': 'SeQura Payment Acquirer',
    'summary': 'SeQura Acquirer: SeQura Implementation',
    'version': '1.0',
    'description': """SeQura Payment Acquirer""",
    'author': 'Raul Fidel Rodríguez Trasanco',
    'depends': ['payment', 'website', 'website_sale'],
    'data': [
        'views/sequra.xml',
        'views/payment_acquirer.xml',
        'views/res_config_view.xml',
        'views/website_template.xml',
        'views/sale_view.xml',
        'data/sequra.xml'
    ],
    'installable': True,
}
