from unittest.mock import patch

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.product_label_print_queue.models import product_pricelist_item as pricelist_item_module


@tagged('post_install', '-at_install')
class TestProductLabelPrintQueue(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Queue = cls.env['product.label.print.queue']

    def _product(self, name, **vals):
        vals.setdefault('name', name)
        vals.setdefault('list_price', 10.0)
        return self.env['product.template'].create(vals)

    def _pending(self, template, source=None):
        domain = [
            ('product_tmpl_id', '=', template.id),
            ('state', '=', 'pending'),
        ]
        if source:
            domain.append(('source', '=', source))
        return self.Queue.search(domain)

    def test_create_does_not_queue_a_label(self):
        template = self._product('Shelf')
        self.assertFalse(self._pending(template))

    def test_list_price_change_queues_one_label(self):
        template = self._product('Shelf')
        template.list_price = 12.0
        line = self._pending(template, 'list_price')
        self.assertEqual(len(line), 1)
        self.assertAlmostEqual(line.old_price, 10.0)
        self.assertAlmostEqual(line.new_price, 12.0)
        payload = self.Queue.systray_get_pending()
        self.assertGreaterEqual(payload['count'], 1)
        item = next(row for row in payload['items'] if row['id'] == line.id)
        self.assertEqual(item['product'], template.display_name)
        self.assertIn('→', item['price'])

    def test_same_price_does_not_queue(self):
        template = self._product('Shelf')
        template.write({'list_price': template.list_price})
        self.assertFalse(self._pending(template))

    def test_second_change_keeps_the_original_price(self):
        template = self._product('Shelf')
        template.list_price = 12.0
        template.list_price = 15.0
        line = self._pending(template, 'list_price')
        self.assertEqual(len(line), 1)
        self.assertAlmostEqual(line.old_price, 10.0)
        self.assertAlmostEqual(line.new_price, 15.0)

    def test_reverting_the_price_clears_the_queue(self):
        template = self._product('Shelf')
        template.list_price = 12.0
        template.list_price = 10.0
        self.assertFalse(self._pending(template))
        cancelled = self.Queue.search([
            ('product_tmpl_id', '=', template.id),
            ('state', '=', 'cancelled'),
        ])
        self.assertEqual(len(cancelled), 1)

    def test_service_price_is_ignored(self):
        service = self._product('Hours', type='service')
        service.list_price = 40.0
        self.assertFalse(self._pending(service))

    def test_variant_sales_price_uses_the_template_hook(self):
        template = self._product('Shelf')
        template.product_variant_id.list_price = 18.0
        line = self._pending(template, 'list_price')
        self.assertEqual(len(line), 1)
        self.assertAlmostEqual(line.new_price, 18.0)

    def test_context_flag_skips_the_queue(self):
        template = self._product('Shelf')
        template.with_context(skip_label_print_queue=True).write({'list_price': 30.0})
        self.assertFalse(self._pending(template))

    def test_copy_does_not_queue_a_label(self):
        template = self._product('Shelf')
        template.list_price = 12.0
        self._pending(template).action_dismiss()
        copied = template.copy()
        self.assertFalse(self._pending(copied))
        self.assertFalse(self._pending(template))

    def test_print_action_opens_the_native_wizard(self):
        first = self._product('First')
        second = self._product('Second')
        first.list_price = 11.0
        second.list_price = 13.0
        action = self.Queue.action_print_labels()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'product.label.layout')
        self.assertEqual(action['target'], 'new')
        self.assertEqual(
            set(action['context']['default_product_tmpl_ids']),
            {first.id, second.id},
        )
        self.assertNotIn('default_pricelist_id', action['context'])

    def test_empty_queue_cannot_print(self):
        with self.assertRaises(UserError):
            self.Queue.action_print_labels()

    def test_dismiss_hides_the_line_from_the_systray(self):
        template = self._product('Shelf')
        template.list_price = 12.0
        line = self._pending(template)
        line.action_dismiss()
        self.assertEqual(line.state, 'cancelled')
        payload = self.Queue.systray_get_pending()
        self.assertFalse(any(row['id'] == line.id for row in payload['items']))

    def test_wizard_process_marks_the_products_printed(self):
        first = self._product('First')
        second = self._product('Second')
        first.list_price = 11.0
        second.list_price = 13.0
        wizard = self.env['product.label.layout'].create({
            'print_format': '2x7xprice',
            'custom_quantity': 1,
            'product_tmpl_ids': [Command.set((first | second).ids)],
        })
        action = wizard.process()
        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertTrue(action.get('close_on_report_download'))
        self.assertFalse(self._pending(first))
        self.assertFalse(self._pending(second))
        self.assertEqual(
            set(self.Queue.search([
                ('product_tmpl_id', 'in', (first | second).ids),
            ]).mapped('state')),
            {'printed'},
        )

    def test_pricelist_rule_queues_the_product(self):
        template = self._product('Milk')
        pricelist = self.env['product.pricelist'].create({'name': 'Shop'})
        self.env['product.pricelist.item'].create({
            'pricelist_id': pricelist.id,
            'applied_on': '1_product',
            'product_tmpl_id': template.id,
            'compute_price': 'fixed',
            'fixed_price': 8.0,
        })
        line = self._pending(template, 'pricelist')
        self.assertEqual(len(line), 1)
        self.assertEqual(line.pricelist_id, pricelist)
        self.assertAlmostEqual(line.old_price, 10.0, places=2)
        self.assertAlmostEqual(line.new_price, 8.0, places=2)
        action = line.action_print_labels()
        self.assertEqual(action['context']['default_product_tmpl_ids'], [template.id])
        self.assertEqual(action['context']['default_pricelist_id'], pricelist.id)

    def test_pricelist_rule_without_a_price_change_is_ignored(self):
        template = self._product('Milk')
        pricelist = self.env['product.pricelist'].create({'name': 'Shop'})
        self.env['product.pricelist.item'].create({
            'pricelist_id': pricelist.id,
            'applied_on': '1_product',
            'product_tmpl_id': template.id,
            'compute_price': 'fixed',
            'fixed_price': 10.0,
        })
        self.assertFalse(self._pending(template, 'pricelist'))

    def test_pricelist_update_and_removal(self):
        template = self._product('Milk')
        pricelist = self.env['product.pricelist'].create({'name': 'Shop'})
        item = self.env['product.pricelist.item'].create({
            'pricelist_id': pricelist.id,
            'applied_on': '1_product',
            'product_tmpl_id': template.id,
            'compute_price': 'fixed',
            'fixed_price': 8.0,
        })
        item.fixed_price = 7.0
        line = self._pending(template, 'pricelist')
        self.assertEqual(len(line), 1)
        self.assertAlmostEqual(line.old_price, 10.0, places=2)
        self.assertAlmostEqual(line.new_price, 7.0, places=2)
        line.action_dismiss()
        item.unlink()
        restored = self._pending(template, 'pricelist')
        self.assertEqual(len(restored), 1)
        self.assertAlmostEqual(restored.new_price, 10.0, places=2)

    def test_category_pricelist_rule_queues_the_product(self):
        category = self.env['product.category'].create({'name': 'Cold'})
        template = self._product('Yogurt', categ_id=category.id)
        pricelist = self.env['product.pricelist'].create({'name': 'Cold shop'})
        self.env['product.pricelist.item'].create({
            'pricelist_id': pricelist.id,
            'applied_on': '2_product_category',
            'categ_id': category.id,
            'compute_price': 'fixed',
            'fixed_price': 4.0,
        })
        line = self._pending(template, 'pricelist')
        self.assertEqual(len(line), 1)
        self.assertAlmostEqual(line.new_price, 4.0, places=2)

    def test_broad_pricelist_rule_is_skipped(self):
        template = self._product('Bulk')
        pricelist = self.env['product.pricelist'].create({'name': 'Everything'})
        with patch.object(pricelist_item_module, 'MAX_LABEL_PRODUCTS', 0):
            self.env['product.pricelist.item'].create({
                'pricelist_id': pricelist.id,
                'applied_on': '3_global',
                'compute_price': 'percentage',
                'percent_price': 10.0,
            })
        self.assertFalse(self._pending(template, 'pricelist'))

    def test_variant_extra_price_queues_the_template(self):
        template = self._product('Shirt')
        attribute = self.env['product.attribute'].create({'name': 'Size'})
        value = self.env['product.attribute.value'].create({
            'name': 'M',
            'attribute_id': attribute.id,
        })
        template.write({
            'attribute_line_ids': [Command.create({
                'attribute_id': attribute.id,
                'value_ids': [Command.set(value.ids)],
            })],
        })
        ptav = template.attribute_line_ids.product_template_value_ids
        self.assertTrue(ptav)
        ptav.price_extra = 2.5
        line = self._pending(template, 'price_extra')
        self.assertEqual(len(line), 1)
        self.assertAlmostEqual(line.old_price, 0.0)
        self.assertAlmostEqual(line.new_price, 2.5)
