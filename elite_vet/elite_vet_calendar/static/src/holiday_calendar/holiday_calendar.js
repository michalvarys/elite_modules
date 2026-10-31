/** @odoo-module **/
/**
 * Calendar view with the Czech public holidays (js_class="elite_vet_holiday_calendar").
 *
 * Used by Rozpis služeb (elite.vet.shift) and Rezervace › Rozpis lékařů
 * (elite.vet.doctor.assignment). The holidays are computed on the server
 * (`elite.vet.shift.holiday_map`, models/holidays.py) - nothing is entered and
 * no records are created. Month: the name in the day cell; week / day: the name
 * under the day in the header. Clicking the day works as before (a double-click no
 * longer fails, see onDateClick).
 */
import { registry } from "@web/core/registry";
import { calendarView } from "@web/views/calendar/calendar_view";
import { CalendarModel } from "@web/views/calendar/calendar_model";
import { CalendarRenderer } from "@web/views/calendar/calendar_renderer";
import { CalendarCommonRenderer } from "@web/views/calendar/calendar_common/calendar_common_renderer";

const { DateTime } = luxon;

export class HolidayCalendarModel extends CalendarModel {
    async updateData(data) {
        await super.updateData(data);
        const { start, end } = data.range;
        try {
            data.holidays = await this.orm.call("elite.vet.shift", "holiday_map", [
                start.toISODate(),
                end.toISODate(),
            ]);
        } catch {
            // The calendar itself must keep working even if the holidays cannot be loaded.
            data.holidays = {};
        }
    }

    /** {"YYYY-MM-DD": name} of the shown range. */
    get holidays() {
        return this.data.holidays || {};
    }
}

export class HolidayCalendarCommonRenderer extends CalendarCommonRenderer {
    static headerTemplate = "elite_vet_calendar.HolidayCalendarHeader";

    get options() {
        return {
            ...super.options,
            dayCellDidMount: this.onHolidayCellDidMount,
        };
    }

    /**
     * A double-click on a day opens the form after the first click and closes the calendar;
     * FullCalendar then reports the second click without its mouse event (destroy() ->
     * onPointerUp({})) and the base handler fails on `info.jsEvent.defaultPrevented`.
     */
    onDateClick(info) {
        if (!info.jsEvent) {
            return;
        }
        super.onDateClick(info);
    }

    holidayName(iso) {
        return this.props.model.holidays[iso] || "";
    }

    /** Day cells: local midnight, read as in getDayCellClassNames (unusual days). */
    cellIso(date) {
        return DateTime.fromJSDate(date).toISODate();
    }

    getDayCellClassNames(info) {
        const classes = super.getDayCellClassNames(info);
        return this.holidayName(this.cellIso(info.date)) ? [...classes, "o_ev_holiday"] : classes;
    }

    onHolidayCellDidMount(info) {
        if (this.props.model.scale !== "month") {
            return;
        }
        const name = this.holidayName(this.cellIso(info.date));
        const top = name && info.el.querySelector(".fc-daygrid-day-top");
        if (!top) {
            return;
        }
        const label = document.createElement("span");
        label.className = "o_ev_holiday_name";
        label.textContent = name;
        label.title = `Státní svátek: ${name}`;
        top.prepend(label);
    }

    headerTemplateProps(date) {
        const props = super.headerTemplateProps(date);
        if (props.scale === "month") {
            return { ...props, holiday: "" };   // the month header has weekday names only
        }
        // the same reading of the date as super (day / week headers)
        const iso = DateTime.fromJSDate(date).plus({ hour: 1 }).toISODate();
        return { ...props, holiday: this.holidayName(iso) };
    }
}

export class HolidayCalendarRenderer extends CalendarRenderer {
    static components = {
        ...CalendarRenderer.components,
        day: HolidayCalendarCommonRenderer,
        week: HolidayCalendarCommonRenderer,
        month: HolidayCalendarCommonRenderer,
    };
}

export const holidayCalendarView = {
    ...calendarView,
    Model: HolidayCalendarModel,
    Renderer: HolidayCalendarRenderer,
};

registry.category("views").add("elite_vet_holiday_calendar", holidayCalendarView);
