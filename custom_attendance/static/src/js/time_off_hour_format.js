/** @odoo-module **/

import {patch} from "@web/core/utils/patch";
import {TimeOffCard} from "@hr_holidays/dashboard/time_off_card";

/**
 * Converts a decimal-hours float (e.g. 1.4667) into an "Xh Ym" string
 * (e.g. "1h 28m"). Falls back gracefully for whole hours or pure minutes.
 *
 * Only applied when the leave type's request_unit is 'hour' — day-based
 * leave types (Casual/Earned/Medical) are untouched and keep Odoo's
 * native day-count formatting.
 */
function formatHoursAsHM(value) {
    if (value === undefined || value === null || isNaN(value)) {
        return value;
    }
    const totalMinutes = Math.round(value * 60);
    const sign = totalMinutes < 0 ? "-" : "";
    const absMinutes = Math.abs(totalMinutes);
    const hours = Math.floor(absMinutes / 60);
    const minutes = absMinutes % 60;

    if (hours && minutes) {
        return `${sign}${hours}h ${minutes}m`;
    }
    if (hours) {
        return `${sign}${hours}h`;
    }
    return `${sign}${minutes}m`;
}

patch(TimeOffCard.prototype, {
    setup() {
        super.setup();
        // Wrap the original formatNumber so hour-based durations render
        // as "1h 28m" instead of Odoo's default decimal ("1.47").
        // Day-based leave types fall through to the original formatter
        // untouched.
        const originalFormatNumber = this.formatNumber;
        this.formatNumber = (lang, value) => {
            const requestUnit = this.props.data && this.props.data.request_unit;
            if (requestUnit === "hour") {
                return formatHoursAsHM(value);
            }
            return originalFormatNumber(lang, value);
        };
    },
});