import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# Category and global rules can match the whole catalog. Above this size we
# skip the queue so saving the rule cannot freeze the interface.
MAX_LABEL_PRODUCTS = 200

_LABEL_PRICE_FIELDS = {
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
}


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

    def _templates_for_scope(self, applied_on, product_tmpl, product, categ):
        if applied_on == '1_product' and product_tmpl:
            return product_tmpl
        if applied_on == '0_product_variant' and product:
            return product.product_tmpl_id
        if applied_on == '2_product_category' and categ:
            return self._limited_templates([
                ('categ_id', 'child_of', categ.id),
                ('type', '!=', 'service'),
            ])
        if applied_on == '3_global':
            return self._limited_templates([('type', '!=', 'service')])
        return self.env['product.template']

    def _templates_for_label_queue(self):
        templates = self.env['product.template']
        for item in self:
            if not item.pricelist_id:
                continue
            templates |= self._templates_for_scope(
                item.applied_on,
                item.product_tmpl_id,
                item.product_id,
                item.categ_id,
            )
        return templates.filtered(lambda template: template.type != 'service')

    def _templates_from_values(self, values):
        values = dict(values)
        if values.get('product_id') and not values.get('product_tmpl_id'):
            product = self.env['product.product'].browse(values['product_id'])
            values['product_tmpl_id'] = product.product_tmpl_id.id
        applied = values.get('applied_on')
        if not applied:
            applied = (
                '0_product_variant' if values.get('product_id') else
                '1_product' if values.get('product_tmpl_id') else
                '2_product_category' if values.get('categ_id') else
                '3_global'
            )
        return self._templates_for_scope(
            applied,
            self.env['product.template'].browse(values.get('product_tmpl_id')),
            self.env['product.product'].browse(values.get('product_id')),
            self.env['product.category'].browse(values.get('categ_id')),
        )

    @api.model
    def _price_map(self, pricelist, templates):
        if not pricelist or not templates:
            return {}
        templates = templates.filtered('product_variant_id')
        products = templates.product_variant_id
        if not products:
            return {}
        prices = pricelist._get_products_price(products, 1.0)
        return {
            template.id: prices.get(template.product_variant_id.id, 0.0)
            for template in templates
            if template.product_variant_id
        }

    def _queue_groups(self, groups):
        merged = {}
        for pricelist, templates, old_map in groups:
            if not pricelist or not templates:
                continue
            bucket = merged.setdefault(pricelist.id, {
                'pricelist': pricelist,
                'templates': self.env['product.template'],
                'old_map': {},
            })
            bucket['templates'] |= templates
            bucket['old_map'].update(old_map)
        queue = self.env['product.label.print.queue']
        lines = queue.browse()
        for bucket in merged.values():
            new_map = self._price_map(bucket['pricelist'], bucket['templates'])
            lines |= queue._enqueue(
                bucket['templates'],
                'pricelist',
                bucket['pricelist'],
                bucket['old_map'],
                new_map,
                notify=False,
            )
        if lines:
            lines._notify_users()
        return lines

    @api.model_create_multi
    def create(self, vals_list):
        if self._skip_label_queue():
            return super().create(vals_list)
        previews = []
        for vals in vals_list:
            pricelist = self.env['product.pricelist'].browse(vals.get('pricelist_id'))
            templates = self._templates_from_values(vals)
            old_map = self._price_map(pricelist, templates) if pricelist else {}
            previews.append((pricelist, templates, old_map))
        records = super().create(vals_list)
        groups = []
        for record, (pricelist, templates, old_map) in zip(records, previews):
            groups.append((
                record.pricelist_id or pricelist,
                templates | record._templates_for_label_queue(),
                old_map,
            ))
        if groups:
            self._queue_groups(groups)
        return records

    def write(self, vals):
        if self._skip_label_queue() or not (set(vals) & _LABEL_PRICE_FIELDS):
            return super().write(vals)
        extra = self.env['product.template']
        if any(key in vals for key in ('applied_on', 'product_tmpl_id', 'product_id', 'categ_id')):
            extra = self._templates_from_values(vals)
        previews = []
        for item in self:
            pricelist = item.pricelist_id
            templates = item._templates_for_label_queue() | extra
            previews.append((pricelist, templates, self._price_map(pricelist, templates)))
        res = super().write(vals)
        groups = []
        for item, (pricelist, templates, old_map) in zip(self, previews):
            groups.append((
                item.pricelist_id or pricelist,
                templates | item._templates_for_label_queue(),
                old_map,
            ))
        if groups:
            self._queue_groups(groups)
        return res

    def unlink(self):
        if self._skip_label_queue():
            return super().unlink()
        groups = []
        for item in self:
            pricelist = item.pricelist_id
            templates = item._templates_for_label_queue()
            groups.append((pricelist, templates, self._price_map(pricelist, templates)))
        res = super().unlink()
        if groups:
            self._queue_groups(groups)
        return res
