from odoo import models
from odoo.tools import float_compare


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
        if not track:
            return res
        precision = self.env['decimal.precision'].precision_get('Product Price')
        changed = self.browse()
        changed_old = {}
        changed_new = {}
        for template in self:
            new_price = template.list_price
            if float_compare(old_prices[template.id], new_price, precision_digits=precision):
                changed |= template
                changed_old[template.id] = old_prices[template.id]
                changed_new[template.id] = new_price
        if changed:
            self.env['product.label.print.queue']._enqueue(
                changed, 'list_price', None, changed_old, changed_new,
            )
        return res

    def copy(self, default=None):
        template = self.with_context(skip_label_print_queue=True)
        return super(ProductTemplate, template).copy(default=default)
