/** @odoo-module **/
/**
 * Rozpis lékařů calendar (js_class="elite_vet_assignment_calendar"): the holiday calendar
 * whose popover also lets the user pick the room. A roster assignment changes the room
 * in its shift (elite.vet.doctor.assignment.set_room), a manual one directly.
 */
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { CalendarCommonPopover } from "@web/views/calendar/calendar_common/calendar_common_popover";
import {
    HolidayCalendarCommonRenderer,
    HolidayCalendarRenderer,
    holidayCalendarView,
} from "@elite_vet_calendar/holiday_calendar/holiday_calendar";

import { onWillStart, useState } from "@odoo/owl";

export class AssignmentCalendarPopover extends CalendarCommonPopover {
    static subTemplates = {
        ...CalendarCommonPopover.subTemplates,
        body: "elite_vet_reservation.AssignmentCalendarPopover.body",
    };

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.state = useState({ rooms: [], saving: false });
        onWillStart(async () => {
            if (this.props.model.canEdit) {
                this.state.rooms = await this.orm.searchRead("elite.vet.room", [], ["name", "color_hex"]);
            }
        });
    }

    get roomId() {
        const room = this.props.record.rawRecord.room_id;
        return Array.isArray(room) ? room[0] : room?.id || room;
    }

    async onPickRoom(room) {
        if (room.id === this.roomId || this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            await this.orm.call(this.props.model.resModel, "set_room", [[this.props.record.id], room.id]);
            await this.props.model.load();
            this.props.close();
        } finally {
            this.state.saving = false;
        }
    }
}

export class AssignmentCalendarCommonRenderer extends HolidayCalendarCommonRenderer {
    static components = { ...HolidayCalendarCommonRenderer.components, Popover: AssignmentCalendarPopover };
}

export class AssignmentCalendarRenderer extends HolidayCalendarRenderer {
    static components = {
        ...HolidayCalendarRenderer.components,
        day: AssignmentCalendarCommonRenderer,
        week: AssignmentCalendarCommonRenderer,
        month: AssignmentCalendarCommonRenderer,
    };
}

registry.category("views").add("elite_vet_assignment_calendar", {
    ...holidayCalendarView,
    Renderer: AssignmentCalendarRenderer,
});
