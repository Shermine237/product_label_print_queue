import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { useDropdownState } from "@web/core/dropdown/dropdown_hooks";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class LabelPrintSystray extends Component {
    static template = "product_label_print_queue.Systray";
    static components = { Dropdown };
    static props = [];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.busService = useService("bus_service");
        this.dropdown = useDropdownState();
        this.state = useState({ count: 0, items: [] });
        this._onBus = () => this.refresh();
        onWillStart(() => this.refresh());
        this.busService.subscribe("product_label_print/updated", this._onBus);
        onWillUnmount(() => {
            this.busService.unsubscribe("product_label_print/updated", this._onBus);
        });
    }

    get title() {
        return _t("Labels to print");
    }

    get removeLabel() {
        return _t("Remove");
    }

    get printLabel() {
        return _t("Print Labels");
    }

    get viewAllLabel() {
        return _t("View all");
    }

    async refresh() {
        try {
            const data = await this.orm.call("product.label.print.queue", "systray_get_pending", []);
            this.state.count = data.count;
            this.state.items = data.items;
        } catch (error) {
            this.state.count = 0;
            this.state.items = [];
        }
    }

    async onBeforeOpen() {
        await this.refresh();
    }

    async onPrint() {
        this.dropdown.close();
        const action = await this.orm.call("product.label.print.queue", "action_print_labels", [[]]);
        if (action) {
            await this.actionService.doAction(action);
        }
    }

    async openList() {
        this.dropdown.close();
        await this.actionService.doAction("product_label_print_queue.action_product_label_print_queue");
    }

    async dismiss(lineId) {
        await this.orm.call("product.label.print.queue", "action_dismiss", [[lineId]]);
        await this.refresh();
    }
}

registry.category("systray").add(
    "product_label_print_queue.LabelPrintSystray",
    { Component: LabelPrintSystray },
    { sequence: 5 },
);
