/** @odoo-module **/

import { Component, useState, onMounted, onWillUnmount, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

// --------------------------------------------------------------------
// LiveClock — segmented block design
// Three cards (HH / MM / SS) with pulsing colon separators,
// a subtle gradient header bar, and a live date + AM/PM footer.
// Registered as a view_widget: <widget name="live_clock"/>
// --------------------------------------------------------------------

class LiveClock extends Component {

    static template = xml`
<div class="owc_clock_shell">

    <!-- top accent bar -->
    <div class="owc_clock_bar"/>

    <!-- digit blocks + separators -->
    <div class="owc_clock_digits">

        <div class="owc_clock_block">
            <span class="owc_clock_num" t-out="state.hh"/>
            <span class="owc_clock_unit">HH</span>
        </div>

        <span class="owc_clock_sep" t-att-class="state.sepVisible ? '' : 'owc_sep_hidden'">:</span>

        <div class="owc_clock_block">
            <span class="owc_clock_num" t-out="state.mm"/>
            <span class="owc_clock_unit">MM</span>
        </div>

        <span class="owc_clock_sep" t-att-class="state.sepVisible ? '' : 'owc_sep_hidden'">:</span>

        <div class="owc_clock_block owc_clock_block_sec">
            <span class="owc_clock_num owc_clock_num_sec" t-out="state.ss"/>
            <span class="owc_clock_unit">SS</span>
        </div>

    </div>

    <!-- footer: AM/PM badge + weekday -->
    <div class="owc_clock_footer">
        <span class="owc_clock_ampm" t-out="state.ampm"/>
        <span class="owc_clock_day"  t-out="state.day"/>
    </div>

</div>

<style>
/* ── shell ────────────────────────────────────────────────── */
.owc_clock_shell {
    display: inline-flex;
    flex-direction: column;
    align-items: stretch;
    background: #0f172a;
    border-radius: 14px;
    overflow: hidden;
    min-width: 210px;
    box-shadow: 0 4px 20px rgba(15,23,42,0.25);
    user-select: none;
}

/* ── top accent gradient bar ─────────────────────────────── */
.owc_clock_bar {
    height: 4px;
    background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 50%, #06b6d4 100%);
}

/* ── digit row ───────────────────────────────────────────── */
.owc_clock_digits {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    padding: 14px 18px 10px;
}

/* ── individual block ────────────────────────────────────── */
.owc_clock_block {
    display: flex;
    flex-direction: column;
    align-items: center;
    background: #1e293b;
    border-radius: 8px;
    padding: 8px 12px 6px;
    min-width: 52px;
}

.owc_clock_num {
    font-family: ui-monospace, 'Cascadia Code', 'Consolas', monospace;
    font-size: 30px;
    font-weight: 800;
    color: #f1f5f9;
    letter-spacing: 1px;
    line-height: 1;
    font-variant-numeric: tabular-nums;
}

.owc_clock_unit {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: #475569;
    margin-top: 4px;
}

/* seconds block — teal accent ───────────────────────────── */
.owc_clock_block_sec {
    background: #0c1a2e;
    border: 1px solid #164e63;
}

.owc_clock_num_sec {
    color: #22d3ee !important;
}

/* ── colon separator ─────────────────────────────────────── */
.owc_clock_sep {
    font-family: ui-monospace, 'Consolas', monospace;
    font-size: 26px;
    font-weight: 900;
    color: #6366f1;
    line-height: 1;
    margin-bottom: 12px;
    transition: opacity 0.15s ease;
}

.owc_sep_hidden {
    opacity: 0;
}

/* ── footer ──────────────────────────────────────────────── */
.owc_clock_footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 16px 10px;
    border-top: 1px solid #1e293b;
}

.owc_clock_ampm {
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: #fff;
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    padding: 2px 8px;
    border-radius: 99px;
}

.owc_clock_day {
    font-size: 10px;
    font-weight: 600;
    color: #64748b;
    letter-spacing: 0.5px;
}
</style>
    `;

    static props = { ...standardWidgetProps };

    setup() {
        this.state     = useState({
            hh: "00", mm: "00", ss: "00",
            ampm: "AM", day: "",
            sepVisible: true,
        });
        this._interval = null;

        onMounted(() => {
            this._tick();
            this._interval = setInterval(() => this._tick(), 1000);
        });

        onWillUnmount(() => clearInterval(this._interval));
    }

    _tick() {
        const now  = new Date();
        const hh   = String(now.getHours()).padStart(2, "0");
        const mm   = String(now.getMinutes()).padStart(2, "0");
        const ss   = String(now.getSeconds()).padStart(2, "0");
        const ampm = now.getHours() < 12 ? "AM" : "PM";
        const days = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];

        this.state.hh         = hh;
        this.state.mm         = mm;
        this.state.ss         = ss;
        this.state.ampm       = ampm;
        this.state.day        = days[now.getDay()];
        this.state.sepVisible = now.getSeconds() % 2 === 0;   // blink every second
    }
}

registry.category("view_widgets").add("live_clock", { component: LiveClock });