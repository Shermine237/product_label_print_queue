from odoo import models


class ProductLabelLayout(models.TransientModel):
    _inherit = 'product.label.layout'

    def process(self):
        action = super().process()
        templates = self.product_tmpl_ids
        if self.product_ids:
            templates |= self.product_ids.product_tmpl_id
        if not templates:
            return action
        queue = self.env['product.label.print.queue'].search([
            ('state', '=', 'pending'),
            ('product_tmpl_id', 'in', templates.ids),
        ])
        if queue:
            queue.write({'state': 'printed'})
            queue._notify_users()
        return action
