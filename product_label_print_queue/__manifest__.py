{
    'name': "Print Product Labels on Price Change",
    'version': '19.0.1.0.1',
    'category': 'Sales/Sales',
    'summary': "Queue product labels when a sales price or pricelist changes",
    'description': """
Queue a product label for printing when a sales price, a variant extra
price, or a pricelist rule changes.

An animated indicator appears in the top bar. It lists the labels waiting
to be printed, and Print Labels opens the standard product.label.layout
wizard, as if those products had been selected in the list view.
    """,
    'author': 'Charlie Rostant YOSSA (Shermine237)',
    'license': 'LGPL-3',
    'depends': ['product'],
    'data': [
        'security/ir.model.access.csv',
        'security/product_label_print_queue_security.xml',
        'views/product_label_print_queue_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'product_label_print_queue/static/src/systray/**/*',
        ],
    },
    'installable': True,
    'application': False,
}
