from odoo import models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def write(self, vals):
        track = (
            'list_price' in vals
            and not self.env.context.get('skip_label_print_queue')
            and not self.env.context.get('install_mode')
        )
        old_prices = {template.id: template.list_price for template in self} if track else {}
        res = super().write(vals)
        if track:
            new_prices = {template.id: template.list_price for template in self}
            self.env['product.label.print.queue']._enqueue(
                self, 'list_price', None, old_prices, new_prices,
            )
        return res

    def copy(self, default=None):
        template = self.with_context(skip_label_print_queue=True)
        return super(ProductTemplate, template).copy(default=default)
