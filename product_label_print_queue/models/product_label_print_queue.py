from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare
from odoo.tools.misc import formatLang

SYSTRAY_LIMIT = 12


class ProductLabelPrintQueue(models.Model):
    _name = 'product.label.print.queue'
    _description = 'Product Label Print Queue'
    _order = 'write_date desc, id desc'

    product_tmpl_id = fields.Many2one(
        'product.template',
        string="Product",
        required=True,
        ondelete='cascade',
        index=True,
    )
    pricelist_id = fields.Many2one(
        'product.pricelist',
        string="Pricelist",
        ondelete='cascade',
        index=True,
    )
    source = fields.Selection(
        selection=[
            ('list_price', "Sales Price"),
            ('pricelist', "Pricelist"),
            ('price_extra', "Variant Extra Price"),
        ],
        required=True,
        default='list_price',
        index=True,
    )
    old_price = fields.Float(string="Previous Price", digits='Product Price')
    new_price = fields.Float(string="New Price", digits='Product Price')
    currency_id = fields.Many2one('res.currency', required=True)
    old_price_display = fields.Char(compute='_compute_price_display')
    new_price_display = fields.Char(compute='_compute_price_display')
    user_id = fields.Many2one(
        'res.users',
        string="Changed by",
        default=lambda self: self.env.user,
        ondelete='set null',
    )
    company_id = fields.Many2one('res.company', index=True)
    state = fields.Selection(
        selection=[
            ('pending', "Pending"),
            ('printed', "Printed"),
            ('cancelled', "Removed"),
        ],
        string="Status",
        required=True,
        default='pending',
        index=True,
    )

    @api.depends('old_price', 'new_price', 'currency_id')
    def _compute_price_display(self):
        for line in self:
            currency = line.currency_id
            line.old_price_display = formatLang(line.env, line.old_price, currency_obj=currency)
            line.new_price_display = formatLang(line.env, line.new_price, currency_obj=currency)

    @api.autovacuum
    def _gc_finished(self):
        deadline = fields.Datetime.now() - timedelta(days=7)
        self.sudo().search([
            ('state', 'in', ('printed', 'cancelled')),
            ('write_date', '<', deadline),
        ]).unlink()

    def _pending_domain(self):
        return [('state', '=', 'pending'), ('product_tmpl_id.active', '=', True)]

    def _notify_users(self):
        """Ping every internal user. The client refetches its own company queue."""
        if self.env.context.get('skip_label_print_queue'):
            return
        group = self.env.ref('base.group_user', raise_if_not_found=False)
        if group:
            self.env['bus.bus']._sendone(group, 'product_label_print/updated', {})

    @api.model
    def _enqueue(self, templates, source, pricelist=None, old_prices=None, new_prices=None, notify=True):
        """Create or update one pending line per product and price source.

        ``old_prices`` / ``new_prices`` map a product.template id to a float.
        A missing old price always enqueues. An unchanged price does not.
        If a later edit restores the original price, the pending line is removed.
        Pass ``skip_label_print_queue`` in the context to ignore a write.
        """
        if self.env.context.get('skip_label_print_queue') or self.env.context.get('install_mode'):
            return self.browse()
        templates = templates.filtered(lambda template: template.type != 'service')
        if not templates:
            return self.browse()

        precision = self.env['decimal.precision'].precision_get('Product Price')
        old_prices = old_prices or {}
        new_prices = new_prices or {}
        pricelist_id = pricelist.id if pricelist else False
        pending = []
        for template in templates:
            old = old_prices.get(template.id)
            new = new_prices.get(template.id, template.list_price)
            if (
                old is not None
                and new is not None
                and float_compare(old, new, precision_digits=precision) == 0
            ):
                continue
            pending.append((template, old, new))
        if not pending:
            return self.browse()

        queue = self.sudo()
        existing_lines = queue.search([
            ('product_tmpl_id', 'in', [template.id for template, _old, _new in pending]),
            ('pricelist_id', '=', pricelist_id),
            ('source', '=', source),
            ('state', '=', 'pending'),
        ])
        existing_by_template = {line.product_tmpl_id.id: line for line in existing_lines}
        touched = queue.browse()
        to_create = []
        for template, old, new in pending:
            currency = self._queue_currency(template, pricelist)
            company = self._queue_company(template, pricelist)
            company_id = company.id or False
            current = existing_by_template.get(template.id)
            if current:
                if new is not None and float_compare(current.old_price, new, precision_digits=precision) == 0:
                    current.write({'state': 'cancelled'})
                else:
                    current.write({
                        'new_price': new if new is not None else current.new_price,
                        'currency_id': currency.id,
                        'user_id': self.env.uid,
                        'company_id': company_id,
                    })
                touched |= current
                continue
            to_create.append({
                'product_tmpl_id': template.id,
                'pricelist_id': pricelist_id,
                'source': source,
                'old_price': 0.0 if old is None else old,
                'new_price': template.list_price if new is None else new,
                'currency_id': currency.id,
                'user_id': self.env.uid,
                'company_id': company_id,
                'state': 'pending',
            })
        if to_create:
            touched |= queue.create(to_create)
        if notify and touched:
            touched._notify_users()
        return touched

    @api.model
    def _queue_currency(self, template, pricelist):
        if pricelist and pricelist.currency_id:
            return pricelist.currency_id
        return template.currency_id or self.env.company.currency_id

    @api.model
    def _queue_company(self, template, pricelist):
        if template.company_id:
            return template.company_id
        if pricelist and pricelist.company_id:
            return pricelist.company_id
        return self.env['res.company']

    def _systray_item(self):
        self.ensure_one()
        if self.pricelist_id:
            detail = _("Pricelist: %s", self.pricelist_id.display_name)
        elif self.source == 'price_extra':
            detail = _("Variant extra price")
        else:
            detail = _("Sales price")
        return {
            'id': self.id,
            'product': self.product_tmpl_id.display_name,
            'detail': detail,
            'price': _("%(old)s → %(new)s", old=self.old_price_display, new=self.new_price_display),
        }

    @api.model
    def systray_get_pending(self):
        domain = self._pending_domain()
        lines = self.search(domain, limit=SYSTRAY_LIMIT, order='write_date desc, id desc')
        return {
            'count': self.search_count(domain),
            'items': [line._systray_item() for line in lines],
        }

    def action_print_labels(self):
        """Open the native label wizard for the pending products.

        Same result as selecting those product templates in the list view and
        clicking Print Labels (``product.template.action_open_label_layout``).
        An empty recordset prints every pending line visible to the user.
        """
        lines = self.filtered(lambda line: line.state == 'pending') if self else self.search(self._pending_domain())
        templates = lines.product_tmpl_id.filtered(lambda template: template.active and template.type != 'service')
        if not templates:
            raise UserError(_("There is no product label waiting to be printed."))
        action = templates.action_open_label_layout()
        pricelists = lines.pricelist_id
        if pricelists and len(pricelists) == 1 and not lines.filtered(lambda line: not line.pricelist_id):
            action['context'] = dict(action.get('context') or {}, default_pricelist_id=pricelists.id)
        return action

    def action_dismiss(self):
        lines = self.filtered(lambda line: line.state == 'pending') if self else self.search(self._pending_domain())
        if not lines:
            return True
        lines.write({'state': 'cancelled'})
        lines._notify_users()
        return True

    def unlink(self):
        pending = bool(self.filtered(lambda line: line.state == 'pending'))
        res = super().unlink()
        if pending:
            self._notify_users()
        return res
