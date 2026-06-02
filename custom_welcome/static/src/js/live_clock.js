/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

class LiveClock extends Component {

    static template = xml`
<div class="owc_shell" t-ref="shell">
    <div class="owc_inner"></div>
    <div class="owc_fade_top"/>
    <div class="owc_fade_bot"/>
</div>

<style>
.owc_shell {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: #ffffff;
    /*border: 1.5px solid #e2e8f0;*/
    border-radius: 12px;
    overflow: hidden;
    padding: 0 14px;
    height: 68px;
    box-shadow: 0 2px 14px rgba(0,0,0,0.07);
    user-select: none;
    box-sizing: border-box;
    width: fit-content;
}
.owc_inner {
    display: flex;
    align-items: center;
    height: 82px;
    overflow: hidden;
    position: relative;
    z-index: 1;
    gap: 0;
}
.owc_col {
    position: relative;
    width: 23px;
    height: 82px;
    overflow: hidden;
    flex-shrink: 0;
}
.owc_tape {
    display: flex;
    flex-direction: column;
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    will-change: transform;
}
.owc_digit {
    /*font-family: 'Montserrat', sans-serif;*/
    font-size: 35px;
    font-weight: 565;
    color: #0f172a;
    line-height: 82px;
    height: 82px;
    display: block;
    text-align: center;
    font-variant-numeric: tabular-nums;
    flex-shrink: 0;
}
.owc_col_sec .owc_digit { color: #0891b2; }
.owc_colon {
    /*font-family: ui-monospace, 'Consolas', monospace;*/
    font-size: 40px;
    font-weight: 900;
    color: #cbd5e1;
    line-height: 72px;
    height: 82px;
    width: 10px;
    text-align: center;
    flex-shrink: 0;
    transition: opacity 0.15s ease;
    position: relative;
    z-index: 1;
}
.owc_colon_hidden { opacity: 1; }
.owc_fade_top,
.owc_fade_bot {
    position: absolute;
    left: 0; right: 0;
    height: 22px;
    z-index: 2;
    pointer-events: none;
}
.owc_fade_top {
    top: 0;
    background: linear-gradient(to bottom, #ffffff 40%, transparent);
}
.owc_fade_bot {
    bottom: 0;
    background: linear-gradient(to top, #ffffff 40%, transparent);
}
</style>
    `;

    static props = { ...standardWidgetProps };

    static ROW_H    = 82;
    static DURATION = 700;
    static EASING   = "cubic-bezier(0.4, 0.0, 0.2, 1)";

    setup() {
        this.shellRef  = useRef("shell");
        this._cols     = {};
        this._colons   = [];
        this._interval = null;

        onMounted(() => {
            const shell = this.shellRef.el;
            if (!shell) return;
            const inner = shell.querySelector(".owc_inner");

            const slots = ["h0","h1",":","m0","m1",":","s0","s1"];
            slots.forEach(key => {
                if (key === ":") {
                    const c = document.createElement("div");
                    c.className = "owc_colon";
                    c.textContent = ":";
                    inner.appendChild(c);
                    this._colons.push(c);
                    return;
                }
                const col  = document.createElement("div");
                col.className = "owc_col" + (key.startsWith("s") ? " owc_col_sec" : "");

                const tape = document.createElement("div");
                tape.className = "owc_tape";
                tape.style.transition = "none";
                tape.style.transform  = "translateY(0px)";

                col.appendChild(tape);
                inner.appendChild(col);
                this._cols[key] = { tape, offset: 0, nodeCount: 0 };
            });

            const now = new Date();
            const hh  = String(now.getHours()  ).padStart(2,"0");
            const mm  = String(now.getMinutes()).padStart(2,"0");
            const ss  = String(now.getSeconds()).padStart(2,"0");
            const init = { h0:hh[0], h1:hh[1], m0:mm[0], m1:mm[1], s0:ss[0], s1:ss[1] };

            Object.entries(init).forEach(([key, d]) => {
                this._appendDigit(key, d);
            });

            this._updateColons(now.getSeconds() % 2 === 0);
            this._interval = setInterval(() => this._tick(), 1000);
        });

        onWillUnmount(() => clearInterval(this._interval));
    }

    _appendDigit(key, digit) {
        const col  = this._cols[key];
        const span = document.createElement("span");
        span.className   = "owc_digit";
        span.textContent = String(digit);
        col.tape.appendChild(span);
        col.nodeCount++;
    }

    _roll(key, newDigit) {
        const col  = this._cols[key];
        const { tape } = col;

        const current = tape.lastElementChild?.textContent;
        if (current === String(newDigit)) return;

        const RH = LiveClock.ROW_H;
        this._appendDigit(key, newDigit);

        const targetOffset = -(col.nodeCount - 1) * RH;
        tape.style.transition = `transform ${LiveClock.DURATION}ms ${LiveClock.EASING}`;
        tape.style.transform  = `translateY(${targetOffset}px)`;
        col.offset = targetOffset;

        setTimeout(() => {
            while (tape.children.length > 1) {
                tape.removeChild(tape.firstElementChild);
                col.nodeCount--;
            }
            tape.style.transition = "none";
            tape.style.transform  = "translateY(0px)";
            col.offset = 0;
        }, LiveClock.DURATION + 50);
    }

    _updateColons(visible) {
        this._colons.forEach(c => {
            c.classList.toggle("owc_colon_hidden", !visible);
        });
    }

    _tick() {
        const now = new Date();
        const hh  = String(now.getHours()  ).padStart(2,"0");
        const mm  = String(now.getMinutes()).padStart(2,"0");
        const ss  = String(now.getSeconds()).padStart(2,"0");

        this._roll("h0", hh[0]);
        this._roll("h1", hh[1]);
        this._roll("m0", mm[0]);
        this._roll("m1", mm[1]);
        this._roll("s0", ss[0]);
        this._roll("s1", ss[1]);

        this._updateColons(now.getSeconds() % 2 === 0);
    }
}

registry.category("view_widgets").add("live_clock", { component: LiveClock });