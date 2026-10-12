/* Booking wizard. No framework: the page already has all text in QWeb,
   this script only calls the JSON API and switches steps. */
(function () {
    "use strict";
    var root = document.getElementById("ev-booking");
    if (!root) return;

    var MONTHS = {
        cs_CZ: ["Leden","Únor","Březen","Duben","Květen","Červen","Červenec","Srpen","Září","Říjen","Listopad","Prosinec"],
        de_DE: ["Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"],
        ru_RU: ["Январь","Февраль","Март","Апрель","Май","Июнь","Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"],
        en_US: ["January","February","March","April","May","June","July","August","September","October","November","December"]
    };
    var DAYS = { cs_CZ: ["Po","Út","St","Čt","Pá","So","Ne"], de_DE: ["Mo","Di","Mi","Do","Fr","Sa","So"],
                 ru_RU: ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"], en_US: ["Mo","Tu","We","Th","Fr","Sa","Su"] };
    var lang = root.dataset.lang || "cs_CZ";
    var months = MONTHS[lang] || MONTHS.cs_CZ, days = DAYS[lang] || DAYS.cs_CZ;

    var state = { options: null, procedure: null, doctor: null, spec: null, date: null, time: null,
                  slot: null, slotDoctor: null, month: null, year: null, daysOk: [], loadingDays: false };
    // Request counters: a slower, older response must not overwrite a newer one
    var seq = { days: 0, slots: 0 };

    function q(sel) { return root.querySelector(sel); }
    function qa(sel) { return Array.prototype.slice.call(root.querySelectorAll(sel)); }
    function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
    function pad(n) { return (n < 10 ? "0" : "") + n; }
    // Translated text from a hidden data-text element; {name} is replaced with the value
    function T(key, name) {
        var n = q('[data-text="' + key + '"]');
        var t = n ? n.textContent.trim() : "";
        return name != null ? t.replace("{name}", function () { return name; }) : t;
    }
    function loadingEl() { return el("p", "evbk-loading", T("loading")); }
    // Case- and diacritics-insensitive comparison
    function norm(s) { return (s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase(); }

    function rpc(path, params) {
        return fetch(path, { method: "POST", credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jsonrpc: "2.0", method: "call", id: Date.now(), params: params || {} }) })
            .then(function (r) { return r.json(); })
            .then(function (b) { if (b.error) throw new Error(b.error.data && b.error.data.message || "rpc"); return b.result; });
    }

    // Scroll so the step bar is visible below the fixed site header
    function scrollToSteps() {
        var steps = q(".evbk-steps") || root;
        var header = document.querySelector(".ev-topbar, header");
        var offset = header ? header.getBoundingClientRect().height : 80;
        var top = steps.getBoundingClientRect().top + window.pageYOffset - offset - 8;
        window.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
    }

    function showStep(n) {
        qa(".evbk-step").forEach(function (s) { s.hidden = s.dataset.step !== String(n); });
        qa(".evbk-steps li").forEach(function (li) {
            li.classList.toggle("is-active", li.dataset.step === String(n));
            li.classList.toggle("is-done", Number(li.dataset.step) < n);
        });
        scrollToSteps();
    }

    // ---------- step 1 ----------
    function doctorNames(p) {
        var ds = state.options.doctors;
        return p.doctor_ids.map(function (id) {
            var d = ds.filter(function (x) { return x.id === id; })[0];
            return d ? d.name : null;
        }).filter(Boolean);
    }
    function procButton(p, withDoctors) {
        var b = el("button", "evbk-item"); b.type = "button";
        b.appendChild(el("span", "evbk-item-name", p.name));
        b.appendChild(el("span", "evbk-item-meta", p.duration + " min" + (p.deposit ? " · " + p.deposit + " Kč" : "")));
        // Specialized procedure: who performs it (only doctors present in the options)
        if (withDoctors && p.specialization_ids.length) {
            var names = doctorNames(p);
            if (names.length) b.appendChild(el("span", "evbk-item-doctors", T("done-by", names.join(", "))));
        }
        if (p.client_note) b.appendChild(el("span", "evbk-item-note", p.client_note));
        b.addEventListener("click", function () { state.procedure = p; gotoCalendar(); });
        return b;
    }
    function renderProcedures(container, list, withDoctors) {
        container.innerHTML = "";
        list.forEach(function (p) { container.appendChild(procButton(p, withDoctors)); });
        container.hidden = false;
    }
    // Grouped list: full-width heading across the grid, procedures below it
    function renderGroups(container, groups) {
        container.innerHTML = "";
        groups.forEach(function (g) {
            if (!g.items.length) return;
            container.appendChild(el("h4", "evbk-group-title", g.title));
            g.items.forEach(function (p) { container.appendChild(procButton(p, true)); });
        });
        container.hidden = false;
    }
    function filterProcedures() {
        var input = q('[data-search="procedures"]');
        var needle = norm(input.value.trim());
        var list = state.options.procedures.filter(function (p) {
            return !needle || norm(p.name).indexOf(needle) !== -1 || norm(p.client_note).indexOf(needle) !== -1;
        });
        renderProcedures(q('[data-list="procedures"]'), list, true);
        q('[data-empty="search"]').hidden = list.length > 0 || !state.options.procedures.length;
    }
    function specChips(d) {
        var box = el("span", "evbk-card-specs");
        state.options.specializations.forEach(function (s) {
            if (d.specialization_ids.indexOf(s.id) === -1) return;
            if (s.icon) {
                var img = el("img", "evbk-spec-icon"); img.src = s.icon; img.alt = s.name; img.title = s.name;
                box.appendChild(img);
            } else {
                var chip = el("span", "evbk-spec-chip", s.name); chip.title = s.name;
                box.appendChild(chip);
            }
        });
        return box;
    }
    function renderStep1() {
        var o = state.options;
        filterProcedures();
        q('[data-search="procedures"]').addEventListener("input", filterProcedures);
        var dl = q('[data-list="doctors"]'); dl.innerHTML = "";
        q('[data-empty="doctors"]').hidden = o.doctors.length > 0;
        q('[data-empty="specializations"]').hidden = o.specializations.length > 0;
        o.doctors.forEach(function (d) {
            var c = el("button", "evbk-card"); c.type = "button";
            if (d.photo) { var img = el("img"); img.src = d.photo; img.alt = ""; c.appendChild(img); }
            c.appendChild(el("span", "", d.name));
            if (d.specialization_ids.length) c.appendChild(specChips(d));
            c.addEventListener("click", function () {
                state.doctor = d; state.spec = null;
                qa('[data-list="doctors"] .evbk-card').forEach(function (x) { x.classList.toggle("is-active", x === c); });
                // only procedures this doctor performs
                renderProcedures(q('[data-list="procedures-for-doctor"]'), o.procedures.filter(function (p) { return p.doctor_ids.indexOf(d.id) !== -1; }), false);
            });
            dl.appendChild(c);
        });
        var sl = q('[data-list="specializations"]'); sl.innerHTML = "";
        o.specializations.forEach(function (s) {
            var c = el("button", "evbk-card"); c.type = "button";
            if (s.icon) { var img = el("img"); img.src = s.icon; img.alt = ""; c.appendChild(img); }
            c.appendChild(el("span", "", s.name));
            c.addEventListener("click", function () {
                state.spec = s; state.doctor = null;
                qa('[data-list="specializations"] .evbk-card').forEach(function (x) { x.classList.toggle("is-active", x === c); });
                // procedures of this specialization, then general ones (any doctor performs them;
                // slots are then limited to doctors with this specialization)
                renderGroups(q('[data-list="procedures-for-spec"]'), [
                    { title: T("spec-procedures", s.name), items: o.procedures.filter(function (p) { return p.specialization_ids.indexOf(s.id) !== -1; }) },
                    { title: T("spec-general"), items: o.procedures.filter(function (p) { return p.specialization_ids.length === 0; }) }
                ]);
            });
            sl.appendChild(c);
        });
        qa(".evbk-tabs button").forEach(function (b) {
            b.disabled = false;
            b.addEventListener("click", function () {
                qa(".evbk-tabs button").forEach(function (x) { x.classList.toggle("is-active", x === b); });
                qa(".evbk-tab").forEach(function (t) { t.hidden = t.dataset.tab !== b.dataset.tab; });
                if (b.dataset.tab === "procedure") { state.doctor = null; state.spec = null; }
            });
        });
    }

    // ---------- step 2 ----------
    function filters() {
        var f = { procedure_id: state.procedure.id };
        if (state.doctor) f.doctor_id = state.doctor.id;
        if (state.spec) f.specialization_id = state.spec.id;
        return f;
    }
    // Last bookable day (today + max_days_ahead)
    function horizon() {
        var h = new Date(); h.setHours(0, 0, 0, 0);
        h.setDate(h.getDate() + ((state.options.settings || {}).max_days_ahead || 0));
        return h;
    }
    function isCurrentMonth() {
        var now = new Date();
        return state.year < now.getFullYear() || (state.year === now.getFullYear() && state.month <= now.getMonth() + 1);
    }
    function nextMonthBeyondHorizon() {
        // The first day of the next month is already past the horizon
        return new Date(state.year, state.month, 1).getTime() > horizon().getTime();
    }
    function updateArrows() {
        q('[data-cal="prev"]').disabled = state.loadingDays || isCurrentMonth();
        q('[data-cal="next"]').disabled = state.loadingDays || nextMonthBeyondHorizon();
    }
    function gotoCalendar() {
        var now = new Date();
        state.year = now.getFullYear(); state.month = now.getMonth() + 1; state.date = null; state.slot = null;
        q('[data-summary="choice"]').textContent = state.procedure.name + (state.doctor ? " · " + state.doctor.name : "") + (state.spec ? " · " + state.spec.name : "");
        seq.slots++;
        resetSlots();
        showStep(2);
        loadMonth(true);
    }
    // auto = initial load: an empty month skips to the next one (up to the horizon)
    function loadMonth(auto) {
        var start = { year: state.year, month: state.month };
        var my = ++seq.days;
        function attempt() {
            var grid = q('[data-cal="grid"]');
            q('[data-cal="title"]').textContent = months[state.month - 1] + " " + state.year;
            grid.innerHTML = ""; grid.classList.add("is-loading"); grid.appendChild(loadingEl());
            q('[data-empty="days"]').hidden = true;
            state.loadingDays = true; updateArrows();
            var p = filters(); p.year = state.year; p.month = state.month;
            return rpc("/rezervace/api/days", p).then(function (list) {
                if (my !== seq.days) return;   // a newer request was made meanwhile
                if (auto && !list.length && !nextMonthBeyondHorizon()) {
                    if (++state.month > 12) { state.month = 1; state.year++; }
                    return attempt();
                }
                if (auto && !list.length) { state.year = start.year; state.month = start.month; }
                state.loadingDays = false;
                state.daysOk = list; grid.classList.remove("is-loading");
                renderMonth(); updateArrows();
                // A selected day from another month is dropped along with its times; if this
                // month has availability, the first free day is selected automatically.
                var prefix = state.year + "-" + pad(state.month) + "-";
                if (!(state.date && state.date.indexOf(prefix) === 0)) {
                    if (state.date) {
                        state.date = null; state.slot = null; state.time = null; state.slotDoctor = null;
                        seq.slots++; resetSlots();
                    }
                    if (list.length) { state.date = list.slice().sort()[0]; renderMonth(); loadSlots(); }
                }
            });
        }
        return attempt().catch(function () {
            if (my !== seq.days) return;
            state.loadingDays = false; updateArrows(); fatal();
        });
    }
    function renderMonth() {
        var grid = q('[data-cal="grid"]'); grid.innerHTML = "";
        days.forEach(function (d) { grid.appendChild(el("div", "evbk-dow", d)); });
        var first = new Date(state.year, state.month - 1, 1);
        // Weeks start on Monday; JS getDay() has Sunday = 0, hence the (getDay()+6)%7 shift
        var offset = (first.getDay() + 6) % 7;
        for (var i = 0; i < offset; i++) grid.appendChild(el("div", "evbk-day is-pad"));
        var count = new Date(state.year, state.month, 0).getDate();
        var today = new Date(); today.setHours(0, 0, 0, 0);
        for (var d = 1; d <= count; d++) {
            var iso = state.year + "-" + pad(state.month) + "-" + pad(d);
            var cell = el("button", "evbk-day", String(d)); cell.type = "button";
            var ok = state.daysOk.indexOf(iso) !== -1;
            cell.disabled = !ok;
            if (ok) cell.classList.add("is-free");
            if (new Date(state.year, state.month - 1, d).getTime() === today.getTime()) cell.classList.add("is-today");
            if (iso === state.date) cell.classList.add("is-selected");
            (function (iso) { cell.addEventListener("click", function () { state.date = iso; renderMonth(); loadSlots(); }); })(iso);
            grid.appendChild(cell);
        }
        q('[data-empty="days"]').hidden = state.daysOk.length > 0;
    }
    function resetSlots() {
        q('[data-slots="hint"]').hidden = false;
        ["am", "pm"].forEach(function (k) { q('[data-slots="' + k + '"]').innerHTML = ""; q('[data-slots="' + k + '-title"]').hidden = true; });
        q('[data-slots="doctor-pick"]').hidden = true;
        q('[data-slots="taken"]').hidden = true;
        var old = q(".evbk-slots .evbk-loading"); if (old) old.remove();
    }
    function loadSlots() {
        resetSlots();
        return loadSlotsInner();
    }
    // Returns true if the slots were actually rendered (the response was not stale)
    function loadSlotsInner() {
        var my = ++seq.slots;
        var p = filters(); p.date = state.date;
        var hint = q('[data-slots="hint"]'); hint.hidden = true;
        var loading = loadingEl(); hint.parentNode.insertBefore(loading, hint);
        return rpc("/rezervace/api/slots", p).then(function (slots) {
            if (my !== seq.slots) return false;
            loading.remove();
            hint.hidden = slots.length > 0;
            slots.forEach(function (s) {
                // 720 minutes after midnight = noon: morning / afternoon column
                var k = s.minute < 720 ? "am" : "pm";
                q('[data-slots="' + k + '-title"]').hidden = false;
                var b = el("button", "evbk-slot", s.time); b.type = "button";
                b.addEventListener("click", function () { pickSlot(s, b); });
                q('[data-slots="' + k + '"]').appendChild(b);
            });
            return true;
        }).catch(function () {
            if (my !== seq.slots) return false;
            loading.remove(); fatal(); return false;
        });
    }
    function pickSlot(s, btn) {
        state.slot = s; state.time = s.time; state.slotDoctor = null;
        qa(".evbk-slot").forEach(function (x) { x.classList.toggle("is-selected", x === btn); });
        if (!state.doctor && s.doctor_ids.length > 1) {
            var box = q('[data-list="slot-doctors"]'); box.innerHTML = "";
            var any = el("button", "evbk-item", T("any-doctor")); any.type = "button";
            any.addEventListener("click", function () { gotoForm(); });
            box.appendChild(any);
            s.doctor_ids.forEach(function (id) {
                var d = state.options.doctors.filter(function (x) { return x.id === id; })[0];
                if (!d) return;
                var b = el("button", "evbk-item", d.name); b.type = "button";
                b.addEventListener("click", function () { state.slotDoctor = d; gotoForm(); });
                box.appendChild(b);
            });
            q('[data-slots="doctor-pick"]').hidden = false;
            return;
        }
        gotoForm();
    }

    // ---------- step 3 ----------
    function humanDate(iso) {
        var p = iso.split("-"); return p[2] + ". " + p[1] + ". " + p[0];
    }
    function summaryText() {
        var doc = state.doctor || state.slotDoctor;
        return state.procedure.name + " · " + humanDate(state.date) + " " + state.time + (doc ? " · " + doc.name : "");
    }
    function gotoForm() {
        q('[data-summary="slot"]').textContent = summaryText();
        showStep(3);
    }
    function showErrors(fields, general) {
        qa(".evbk-form .is-invalid").forEach(function (x) { x.classList.remove("is-invalid"); });
        qa(".evbk-form .evbk-field-error").forEach(function (x) { x.remove(); });
        var orphan = [];
        Object.keys(fields || {}).forEach(function (name) {
            var input = q('.evbk-form [name="' + name + '"]');
            // A field without an input (procedure_id, time...) would otherwise be lost: show it in the general error
            if (!input) { orphan.push(fields[name]); return; }
            input.classList.add("is-invalid");
            input.closest("label").appendChild(el("span", "evbk-field-error", fields[name]));
        });
        var g = q('[data-error="form"]');
        var text = [general].concat(orphan).filter(Boolean).join(" ");
        g.hidden = !text; g.textContent = text;
    }
    q(".evbk-form").addEventListener("submit", function (ev) {
        ev.preventDefault();
        var f = ev.target, data = filters();
        // hp = honeypot, sent to the server, which treats a filled one as spam
        ["contact_name", "pet_name", "pet_species", "problem", "contact_email", "contact_phone", "hp"].forEach(function (n) { data[n] = f.elements[n].value; });
        data.consent = f.elements.consent.checked;
        data.date = state.date; data.time = state.time;
        if (state.slotDoctor) data.doctor_id = state.slotDoctor.id;
        var btn = f.querySelector(".evbk-submit"); btn.disabled = true;
        rpc("/rezervace/api/submit", data).then(function (res) {
            btn.disabled = false;
            if (res.ok) { gotoDone(res); return; }
            if (res.error === "slot_taken") {
                // Slot was taken meanwhile: back to selection, redraw the month (the day may be full now) and slots
                showErrors({}, ""); showStep(2); loadMonth(false);
                loadSlots().then(function (fresh) { if (fresh) q('[data-slots="taken"]').hidden = false; });
                return;
            }
            if (res.error === "rate_limit") { showErrors({}, q('[data-error="fatal"]').textContent); return; }
            showErrors(res.fields, "");
        }).catch(function () { btn.disabled = false; fatal(); });
    });

    // ---------- step 4 ----------
    function gotoDone(res) {
        q('[data-summary="final"]').textContent = summaryText();
        var note = q('[data-done="note"]'); note.hidden = !state.procedure.client_note; note.textContent = state.procedure.client_note || "";
        q('[data-done="deposit"]').hidden = !res.deposit;
        showStep(4);
    }

    // ---------- shared ----------
    function fatal() { q('[data-error="fatal"]').hidden = false; }
    qa("[data-back]").forEach(function (b) { b.addEventListener("click", function () { showStep(Number(b.dataset.back)); }); });
    q('[data-cal="prev"]').addEventListener("click", function () {
        if (state.loadingDays || isCurrentMonth()) return;
        if (--state.month < 1) { state.month = 12; state.year--; }
        loadMonth(false);
    });
    q('[data-cal="next"]').addEventListener("click", function () {
        if (state.loadingDays || nextMonthBeyondHorizon()) return;
        if (++state.month > 12) { state.month = 1; state.year++; }
        loadMonth(false);
    });

    // Loading options: show the loading text and keep tabs disabled until data arrives
    var procList = q('[data-list="procedures"]');
    procList.appendChild(loadingEl());
    qa(".evbk-tabs button").forEach(function (b) { b.disabled = true; });
    rpc("/rezervace/api/options", {}).then(function (o) { state.options = o; renderStep1(); }).catch(function () {
        procList.innerHTML = ""; fatal();
    });
})();
