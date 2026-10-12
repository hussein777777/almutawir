/** @odoo-module **/
import { Component, onMounted, onPatched, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";
import { formatMonetary } from "@web/views/fields/formatters";
import { user } from "@web/core/user";
import { _t } from "@web/core/l10n/translation";

const STATUS_COLORS = {
    on_track: "#1a9e8f",
    at_risk: "#f2b632",
    overdue: "#e5484d",
    closed: "#c7cbd6",
};

export class ReSalesDashboard extends Component {
    static template = "re_sales_management.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.barRef = useRef("barChart");
        this.donutRef = useRef("donutChart");
        this.charts = [];
        this.state = useState({ data: null, year: new Date().getFullYear(), loading: true });
        this.userName = user.name;

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load();
        });
        onMounted(() => this.renderCharts());
        onPatched(() => this.renderCharts());
        onWillUnmount(() => this.destroyCharts());
    }

    async load() {
        this.state.loading = true;
        this.state.data = await this.orm.call("re.contract", "get_dashboard_data", [], { year: this.state.year });
        this.state.loading = false;
    }

    async onYearChange(ev) {
        this.state.year = parseInt(ev.target.value, 10);
        await this.load();
    }

    // ---------------------------------------------------------------- helpers
    get greeting() {
        const hour = new Date().getHours();
        if (hour < 12) {
            return _t("Good Morning, %s!", this.userName);
        }
        if (hour < 18) {
            return _t("Good Afternoon, %s!", this.userName);
        }
        return _t("Good Evening, %s!", this.userName);
    }

    get today() {
        return new Date().toLocaleDateString(user.lang?.replace("_", "-") || undefined, {
            weekday: "long", day: "numeric", month: "long", year: "numeric",
        });
    }

    money(value) {
        const data = this.state.data;
        return formatMonetary(value || 0, { currencyId: data && data.currency.id, digits: [16, 0] });
    }

    number(value) {
        return (value || 0).toLocaleString();
    }

    get statusRows() {
        const status = this.state.data.status;
        const total = Object.values(status).reduce((a, b) => a + b, 0) || 1;
        return [
            { key: "on_track", label: _t("On Track"), count: status.on_track },
            { key: "at_risk", label: _t("At Risk"), count: status.at_risk },
            { key: "overdue", label: _t("Overdue"), count: status.overdue },
            { key: "closed", label: _t("Fully Paid"), count: status.closed },
        ].map((row) => ({ ...row, pct: Math.round((row.count * 100) / total), color: STATUS_COLORS[row.key] }));
    }

    badgeClass(status) {
        return {
            on_track: "o_re_b_green", active: "o_re_b_green", closed: "o_re_b_grey", paid: "o_re_b_green",
            at_risk: "o_re_b_yellow", partial: "o_re_b_yellow", due: "o_re_b_yellow",
            overdue: "o_re_b_red", upcoming: "o_re_b_blue", draft: "o_re_b_blue",
        }[status] || "o_re_b_grey";
    }

    methodIcon(method) {
        return { cheque: "fa-credit-card", cash: "fa-money", bank_transfer: "fa-university" }[method] || "fa-money";
    }

    progressClass(pct) {
        return pct >= 40 ? "o_re_bar_green" : pct >= 25 ? "o_re_bar_yellow" : "o_re_bar_red";
    }

    // ---------------------------------------------------------------- charts
    destroyCharts() {
        for (const chart of this.charts) {
            chart.destroy();
        }
        this.charts = [];
    }

    renderCharts() {
        if (!this.state.data || !window.Chart) {
            return;
        }
        this.destroyCharts();
        const data = this.state.data;
        const months = [...Array(12).keys()].map((m) =>
            new Date(2000, m, 1).toLocaleDateString(user.lang?.replace("_", "-") || undefined, { month: "short" })
        );
        if (this.barRef.el) {
            this.charts.push(new window.Chart(this.barRef.el, {
                type: "bar",
                data: {
                    labels: months,
                    datasets: [
                        { label: _t("Collected"), data: data.chart.collected, backgroundColor: "#16a06e", borderRadius: 4, stack: "s" },
                        { label: _t("Pending"), data: data.chart.pending, backgroundColor: "#c9c6f5", borderRadius: 4, stack: "s" },
                    ],
                },
                options: {
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
                        tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${this.money(ctx.parsed.y)}` } },
                    },
                    scales: {
                        x: { stacked: true, grid: { display: false } },
                        y: {
                            stacked: true, beginAtZero: true,
                            ticks: {
                                callback: (v) => (v >= 1e6 ? `${v / 1e6}M` : v >= 1e3 ? `${v / 1e3}K` : v),
                            },
                        },
                    },
                },
            }));
        }
        if (this.donutRef.el) {
            const rows = this.statusRows;
            this.charts.push(new window.Chart(this.donutRef.el, {
                type: "doughnut",
                data: {
                    labels: rows.map((r) => r.label),
                    datasets: [{ data: rows.map((r) => r.count), backgroundColor: rows.map((r) => r.color), borderWidth: 2 }],
                },
                options: { cutout: "68%", maintainAspectRatio: false, plugins: { legend: { display: false } } },
            }));
        }
    }

    // ---------------------------------------------------------------- navigation
    openAction(xmlId, extra = {}) {
        return this.action.doAction(xmlId, { additionalContext: extra.context || {} , ...extra.options });
    }

    openRecord(model, id) {
        return this.action.doAction({ type: "ir.actions.act_window", res_model: model, res_id: id, views: [[false, "form"]] });
    }

    openList(model, name, domain, context = {}) {
        return this.action.doAction({
            type: "ir.actions.act_window", name, res_model: model, domain, context,
            views: [[false, "list"], [false, "form"]],
        });
    }

    openContractsByStatus(status) {
        this.openList("re.contract", _t("Contracts"), [["collection_status", "=", status]]);
    }

    openOverdue() {
        this.openList("re.contract.installment", _t("Overdue Installments"), [["state", "=", "overdue"]]);
    }

    openDueThisMonth() {
        const now = new Date();
        const start = new Date(now.getFullYear(), now.getMonth(), 1);
        const end = new Date(now.getFullYear(), now.getMonth() + 1, 1);
        const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
        this.openList("re.contract.installment", _t("Due This Month"), [
            ["due_date", ">=", fmt(start)], ["due_date", "<", fmt(end)], ["state", "not in", ["paid", "cancelled"]],
        ]);
    }
}

registry.category("actions").add("re_sales_dashboard", ReSalesDashboard);
