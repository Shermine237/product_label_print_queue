from odoo import api, models
from odoo.tools import float_compare


class ProductTemplateAttributeValue(models.Model):
    _inherit = 'product.template.attribute.value'

    def _skip_label_queue(self):
        return bool(
            self.env.context.get('skip_label_print_queue')
            or self.env.context.get('install_mode')
        )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self._skip_label_queue():
            changed = records.filtered('price_extra')
            if changed:
                self._enqueue_extra_price(changed, {ptav.id: 0.0 for ptav in changed})
        return records

    def write(self, vals):
        if 'price_extra' not in vals or self._skip_label_queue():
            return super().write(vals)
        old_extras = {ptav.id: ptav.price_extra for ptav in self}
        res = super().write(vals)
        precision = self.env['decimal.precision'].precision_get('Product Price')
        changed = self.filtered(
            lambda ptav: float_compare(old_extras[ptav.id], ptav.price_extra, precision_digits=precision) != 0
        )
        if changed:
            self._enqueue_extra_price(changed, old_extras)
        return res

    def _enqueue_extra_price(self, ptavs, old_extras):
        templates = self.env['product.template']
        old_prices = {}
        new_prices = {}
        for ptav in ptavs:
            template = ptav.product_tmpl_id
            if not template:
                continue
            templates |= template
            old_prices.setdefault(template.id, old_extras.get(ptav.id, 0.0))
            new_prices[template.id] = ptav.price_extra
        self.env['product.label.print.queue']._enqueue(
            templates, 'price_extra', None, old_prices, new_prices,
        )
