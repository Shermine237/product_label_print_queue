import logging

from odoo import api, models
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

# Category and global rules can match the whole catalog. Above this size we
# skip the queue so saving the rule cannot freeze the interface.
MAX_LABEL_PRODUCTS = 200

_LABEL_PRICE_FIELDS = frozenset({
    'fixed_price',
    'percent_price',
    'price_discount',
    'price_surcharge',
    'price_round',
    'price_min_margin',
    'price_max_margin',
    'price_markup',
    'compute_price',
    'base',
    'base_pricelist_id',
    'applied_on',
    'product_tmpl_id',
    'product_id',
    'categ_id',
    'min_quantity',
    'date_start',
    'date_end',
    'pricelist_id',
})


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    def _skip_label_queue(self):
        return bool(
            self.env.context.get('skip_label_print_queue')
            or self.env.context.get('install_mode')
        )

    def _limited_templates(self, domain):
        templates = self.env['product.template'].search(domain, limit=MAX_LABEL_PRODUCTS + 1)
        if len(templates) > MAX_LABEL_PRODUCTS:
            _logger.info(
                "Product label queue skipped a broad pricelist rule (more than %s products).",
                MAX_LABEL_PRODUCTS,
            )
            return self.env['product.template']
        return templates

    def _affected_templates(self):
        """Products whose label is tied to this rule.

        Product and variant rules stay on that one template. Category and
        global rules are capped and never run the pricelist price engine.
        """
        self.ensure_one()
        if not self.pricelist_id:
            return self.env['product.template']
        if self.applied_on == '1_product' and self.product_tmpl_id:
            return self.product_tmpl_id
        if self.applied_on == '0_product_variant' and self.product_id:
            return self.product_id.product_tmpl_id
        if self.applied_on == '2_product_category' and self.categ_id:
            return self._limited_templates([
                ('categ_id', 'child_of', self.categ_id.id),
                ('type', '!=', 'service'),
            ])
        if self.applied_on == '3_global':
            return self._limited_templates([('type', '!=', 'service')])
        return self.env['product.template']

    def _amount_snapshot(self):
        """Raw rule amount. This does not compute the pricelist price."""
        self.ensure_one()
        if self.compute_price == 'fixed':
            return self.fixed_price
        if self.compute_price == 'percentage':
            return self.percent_price
        return self.price_discount

    def _queue_label_changes(self, old_amounts=None):
        """Queue the products of rules that already changed.

        ``old_amounts`` maps an item id to its previous raw amount. Missing
        entries mean the rule was just created.
        """
        if self._skip_label_queue() or not self:
            return
        old_amounts = old_amounts or {}
        queue = self.env['product.label.print.queue']
        lines = queue.browse()
        for item in self:
            if not item.pricelist_id:
                continue
            templates = item._affected_templates()
            if not templates:
                continue
            new_amount = item._amount_snapshot()
            previous = old_amounts.get(item.id)
            old_prices = {}
            new_prices = {}
            for template in templates:
                new_prices[template.id] = new_amount
                if previous is None and item.compute_price == 'fixed':
                    # A new fixed rule that repeats the sales price does not
                    # change the printed label.
                    old_prices[template.id] = template.list_price
                elif previous is not None:
                    old_prices[template.id] = previous
            lines |= queue._enqueue(
                templates,
                'pricelist',
                item.pricelist_id,
                old_prices,
                new_prices,
                notify=False,
            )
        if lines:
            lines._notify_users()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self._skip_label_queue():
            records._queue_label_changes()
        return records

    def write(self, vals):
        if self._skip_label_queue() or not (set(vals) & _LABEL_PRICE_FIELDS):
            return super().write(vals)
        # Read the raw amounts already in cache. Do this before super(), and
        # do not compute pricelist prices here: that flushes the pending save
        # and walks every matching rule.
        old_amounts = {item.id: item._amount_snapshot() for item in self}
        res = super().write(vals)
        precision = self.env['decimal.precision'].precision_get('Product Price')
        changed = self.browse()
        for item in self:
            if float_compare(old_amounts[item.id], item._amount_snapshot(), precision_digits=precision):
                changed |= item
        if changed:
            changed._queue_label_changes(old_amounts)
        return res

    def unlink(self):
        if self._skip_label_queue():
            return super().unlink()
        pending = []
        for item in self:
            templates = item._affected_templates()
            if templates and item.pricelist_id:
                pending.append((item.pricelist_id, templates, item._amount_snapshot()))
        res = super().unlink()
        queue = self.env['product.label.print.queue']
        lines = queue.browse()
        for pricelist, templates, old_amount in pending:
            old_prices = {template.id: old_amount for template in templates}
            new_prices = {template.id: template.list_price for template in templates}
            lines |= queue._enqueue(
                templates, 'pricelist', pricelist, old_prices, new_prices, notify=False,
            )
        if lines:
            lines._notify_users()
        return res
