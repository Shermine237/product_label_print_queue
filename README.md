# Print Product Labels on Price Change

Odoo 19 module that queues a product label whenever a price changes, then prints it with the standard label wizard.

## What it does

Changing one of these prices adds the product to a print queue:

- sales price on the product
- variant extra price
- pricelist rule for a product, a variant, or a product category

A tag icon then appears in the top bar, with a badge and a short animation, for as long as labels are waiting. Open it to see the products, the previous price, and the new price. **Print Labels** opens the native `product.label.layout` wizard, the same window as selecting those products in the product list and clicking **Print Labels**. Confirming the wizard marks the lines as printed.

Putting the price back to its original value removes the queue line. Service products are never queued. A category or global pricelist rule that matches more than 200 products is skipped, so saving the rule stays responsive.

Other modules can skip the queue by writing with the context key `skip_label_print_queue`.

## Requirements

- Odoo 19.0
- the `product` module

## Installation

Add this repository to the Odoo addons path. The module directory is `product_label_print_queue`.

```text
addons_path = /path/to/odoo/addons,/path/to/this/repository
```

Update the apps list, then install **Print Product Labels on Price Change**.

French translations are in `product_label_print_queue/i18n/fr.po`.

## Tests

GitHub Actions checks out Odoo 19.0 and runs the module tests on PostgreSQL 16. The workflow is `.github/workflows/ci.yml`.

To run them locally:

```bash
python odoo/odoo-bin \
  --addons-path=odoo/addons,/path/to/this/repository \
  --database=ci_product_label_print_queue \
  --init=product_label_print_queue \
  --test-enable \
  --stop-after-init \
  --without-demo=all
```

## License

LGPL-3.0 or later.
