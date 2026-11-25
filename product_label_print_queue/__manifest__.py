{
    'name': "Étiquettes à imprimer après changement de prix",
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': "File d'attente d'étiquettes produit quand un prix ou une liste de prix change",
    'description': """
Met en file d'attente l'impression d'étiquettes lorsqu'un prix de vente,
un supplément de variante ou une règle de liste de prix est modifié.

Un indicateur animé apparaît dans la barre supérieure. Il ouvre la liste
des étiquettes en attente et le bouton d'impression lance le wizard natif
product.label.layout, comme la sélection de plusieurs produits puis
« Print Labels ».
    """,
    'author': 'Custom',
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
