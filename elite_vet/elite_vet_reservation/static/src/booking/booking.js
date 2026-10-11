/* Rezervacni pruvodce. Zadny framework: stranka uz ma vsechen text v QWeb,
   tenhle skript jen vola JSON API a prepina kroky. */
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
                  slot: null, slotDoctor: null, month: null, year: null, daysOk: [] };

    function q(sel) { return root.querySelector(sel); }
    function qa(sel) { return Array.prototype.slice.call(root.querySelectorAll(sel)); }
    function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
    function pad(n) { return (n < 10 ? "0" : "") + n; }

    function rpc(path, params) {
        return fetch(path, { method: "POST", credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jsonrpc: "2.0", method: "call", id: Date.now(), params: params || {} }) })
            .then(function (r) { return r.json(); })
            .then(function (b) { if (b.error) throw new Error(b.error.data && b.error.data.message || "rpc"); return b.result; });
    }

    function showStep(n) {
        qa(".evbk-step").forEach(function (s) { s.hidden = s.dataset.step !== String(n); });
        qa(".evbk-steps li").forEach(function (li) {
            li.classList.toggle("is-active", li.dataset.step === String(n));
            li.classList.toggle("is-done", Number(li.dataset.step) < n);
        });
        root.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    // ---------- krok 1 ----------
    function procButton(p) {
        var b = el("button", "evbk-item"); b.type = "button";
        b.appendChild(el("span", "evbk-item-name", p.name));
        b.appendChild(el("span", "evbk-item-meta", p.duration + " min" + (p.deposit ? " · " + p.deposit + " Kč" : "")));
        if (p.client_note) b.appendChild(el("span", "evbk-item-note", p.client_note));
        b.addEventListener("click", function () { state.procedure = p; gotoCalendar(); });
        return b;
    }
    function renderProcedures(container, list) {
        container.innerHTML = "";
        list.forEach(function (p) { container.appendChild(procButton(p)); });
        container.hidden = false;
    }
    function renderStep1() {
        var o = state.options;
        renderProcedures(q('[data-list="procedures"]'), o.procedures);
        var dl = q('[data-list="doctors"]'); dl.innerHTML = "";
        q('[data-empty="doctors"]').hidden = o.doctors.length > 0;
        q('[data-empty="specializations"]').hidden = o.specializations.length > 0;
        o.doctors.forEach(function (d) {
            var c = el("button", "evbk-card"); c.type = "button";
            if (d.photo) { var img = el("img"); img.src = d.photo; img.alt = ""; c.appendChild(img); }
            c.appendChild(el("span", "", d.name));
            c.addEventListener("click", function () {
                state.doctor = d; state.spec = null;
                qa('[data-list="doctors"] .evbk-card').forEach(function (x) { x.classList.toggle("is-active", x === c); });
                // jen úkony, které lékařka dělá
                renderProcedures(q('[data-list="procedures-for-doctor"]'), o.procedures.filter(function (p) { return p.doctor_ids.indexOf(d.id) !== -1; }));
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
                // úkony daného oboru, k nim obecné úkony (dělá je kterákoli lékařka, termíny se pak
                // omezí na lékařky s touto specializací)
                var list = o.procedures.filter(function (p) { return p.specialization_ids.indexOf(s.id) !== -1; })
                    .concat(o.procedures.filter(function (p) { return p.specialization_ids.length === 0; }));
                renderProcedures(q('[data-list="procedures-for-spec"]'), list);
            });
            sl.appendChild(c);
        });
        qa(".evbk-tabs button").forEach(function (b) {
            b.addEventListener("click", function () {
                qa(".evbk-tabs button").forEach(function (x) { x.classList.toggle("is-active", x === b); });
                qa(".evbk-tab").forEach(function (t) { t.hidden = t.dataset.tab !== b.dataset.tab; });
                if (b.dataset.tab === "procedure") { state.doctor = null; state.spec = null; }
            });
        });
    }

    // ---------- krok 2 ----------
    function filters() {
        var f = { procedure_id: state.procedure.id };
        if (state.doctor) f.doctor_id = state.doctor.id;
        if (state.spec) f.specialization_id = state.spec.id;
        return f;
    }
    function gotoCalendar() {
        var now = new Date();
        state.year = now.getFullYear(); state.month = now.getMonth() + 1; state.date = null; state.slot = null;
        q('[data-summary="choice"]').textContent = state.procedure.name + (state.doctor ? " · " + state.doctor.name : "") + (state.spec ? " · " + state.spec.name : "");
        resetSlots();
        showStep(2);
        loadMonth();
    }
    function loadMonth() {
        var grid = q('[data-cal="grid"]');
        q('[data-cal="title"]').textContent = months[state.month - 1] + " " + state.year;
        grid.innerHTML = ""; grid.classList.add("is-loading");
        var p = filters(); p.year = state.year; p.month = state.month;
        rpc("/rezervace/api/days", p).then(function (list) {
            state.daysOk = list; grid.classList.remove("is-loading"); renderMonth();
        }).catch(fatal);
    }
    function renderMonth() {
        var grid = q('[data-cal="grid"]'); grid.innerHTML = "";
        days.forEach(function (d) { grid.appendChild(el("div", "evbk-dow", d)); });
        var first = new Date(state.year, state.month - 1, 1);
        // Tyden zacina pondelim, JS getDay() ma nedeli = 0, proto posun (getDay()+6)%7
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
    }
    function loadSlots() {
        resetSlots();
        return loadSlotsInner();
    }
    function loadSlotsInner() {
        var p = filters(); p.date = state.date;
        return rpc("/rezervace/api/slots", p).then(function (slots) {
            q('[data-slots="hint"]').hidden = slots.length > 0;
            if (!slots.length) { q('[data-slots="hint"]').hidden = false; return; }
            slots.forEach(function (s) {
                // 720 minut = poledne od pulnoci: dopoledne / odpoledne sloupec
                var k = s.minute < 720 ? "am" : "pm";
                q('[data-slots="' + k + '-title"]').hidden = false;
                var b = el("button", "evbk-slot", s.time); b.type = "button";
                b.addEventListener("click", function () { pickSlot(s, b); });
                q('[data-slots="' + k + '"]').appendChild(b);
            });
        }).catch(fatal);
    }
    function pickSlot(s, btn) {
        state.slot = s; state.time = s.time; state.slotDoctor = null;
        qa(".evbk-slot").forEach(function (x) { x.classList.toggle("is-selected", x === btn); });
        if (!state.doctor && s.doctor_ids.length > 1) {
            var box = q('[data-list="slot-doctors"]'); box.innerHTML = "";
            var any = el("button", "evbk-item", q('[data-text="any-doctor"]').textContent); any.type = "button";
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

    // ---------- krok 3 ----------
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
            // Pole bez vstupu (procedure_id, time...) by se jinak ztratilo: ukazeme ho v obecne chybe
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
        // hp = honeypot, posila se na server, kde se vyhodnoti jako spam
        ["contact_name", "pet_name", "pet_species", "problem", "contact_email", "contact_phone", "hp"].forEach(function (n) { data[n] = f.elements[n].value; });
        data.consent = f.elements.consent.checked;
        data.date = state.date; data.time = state.time;
        if (state.slotDoctor) data.doctor_id = state.slotDoctor.id;
        var btn = f.querySelector(".evbk-submit"); btn.disabled = true;
        rpc("/rezervace/api/submit", data).then(function (res) {
            btn.disabled = false;
            if (res.ok) { gotoDone(res); return; }
            if (res.error === "slot_taken") {
                // Termin mezitim nekdo zabral: zpet na vyber, prekreslit mesic (den mohl zaplnit) a slotty
                showErrors({}, ""); showStep(2); loadMonth();
                loadSlots().then(function () { q('[data-slots="taken"]').hidden = false; });
                return;
            }
            if (res.error === "rate_limit") { showErrors({}, q('[data-error="fatal"]').textContent); return; }
            showErrors(res.fields, "");
        }).catch(function () { btn.disabled = false; fatal(); });
    });

    // ---------- krok 4 ----------
    function gotoDone(res) {
        q('[data-summary="final"]').textContent = summaryText();
        var note = q('[data-done="note"]'); note.hidden = !state.procedure.client_note; note.textContent = state.procedure.client_note || "";
        q('[data-done="deposit"]').hidden = !res.deposit;
        showStep(4);
    }

    // ---------- spolecne ----------
    function fatal() { q('[data-error="fatal"]').hidden = false; }
    qa("[data-back]").forEach(function (b) { b.addEventListener("click", function () { showStep(Number(b.dataset.back)); }); });
    q('[data-cal="prev"]').addEventListener("click", function () { if (--state.month < 1) { state.month = 12; state.year--; } loadMonth(); });
    q('[data-cal="next"]').addEventListener("click", function () { if (++state.month > 12) { state.month = 1; state.year++; } loadMonth(); });

    rpc("/rezervace/api/options", {}).then(function (o) { state.options = o; renderStep1(); }).catch(fatal);
})();
