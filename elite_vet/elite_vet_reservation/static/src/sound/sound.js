/** @odoo-module **/
/**
 * Zvuk při nové žádosti z webu – v celém Odoo, nejen na tabuli, aby ho recepce
 * slyšela i z jiné obrazovky. Zprávu posílá server přes bus (models/live.py).
 *
 * Ohlásí se jen žádost, kterou tento panel prohlížeče ještě neohlásil: bus po
 * načtení stránky doručí znovu i zprávy z poslední chvíle a znělka ani zpráva
 * by se jinak opakovaly při každém obnovení.
 *
 * Tón se generuje přes Web Audio (žádný zvukový soubor). Prohlížeč pustí zvuk až
 * po prvním kliknutí na stránku, proto se audio „odemkne“ prvním kliknutím.
 * Vypnout jde tlačítkem na tabuli; volba platí pro tento prohlížeč.
 */
import { registry } from "@web/core/registry";

const KLIC = "elite_vet_reservation.sound";

export function isSoundOn() {
    try {
        return localStorage.getItem(KLIC) !== "0";
    } catch {
        return true;
    }
}

export function setSoundOn(zapnuto) {
    try {
        localStorage.setItem(KLIC, zapnuto ? "1" : "0");
    } catch {
        // soukromé okno / zakázané úložiště: zvuk zůstane zapnutý
    }
}

const ANNOUNCED_KEY = "elite_vet_reservation.announced";

/** Ze seznamu id vrátí ta, která tento panel ještě neohlásil, a poznamená si je. */
export function takeUnannounced(ids) {
    let videne = [];
    try {
        videne = JSON.parse(sessionStorage.getItem(ANNOUNCED_KEY) || "[]");
    } catch {
        videne = [];
    }
    const nove = (ids || []).filter((id) => !videne.includes(id));
    if (nove.length) {
        try {
            sessionStorage.setItem(ANNOUNCED_KEY, JSON.stringify([...videne, ...nove].slice(-300)));
        } catch {
            // bez úložiště: v nejhorším se po obnovení ohlásí znovu
        }
    }
    return nove;
}

let ctx = null;
function kontext() {
    if (!ctx) {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) return null;
        ctx = new AC();
    }
    return ctx;
}

/** Krátký dvoutónový „ding-dong“ (A5 → E6). */
export function playChime() {
    const c = kontext();
    if (!c) return;
    if (c.state === "suspended") c.resume();
    const t0 = c.currentTime + 0.02;
    for (const [freq, delay] of [[880, 0], [1318.5, 0.18]]) {
        const osc = c.createOscillator();
        const gain = c.createGain();
        osc.type = "sine";
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.0001, t0 + delay);
        gain.gain.exponentialRampToValueAtTime(0.35, t0 + delay + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t0 + delay + 0.45);
        osc.connect(gain).connect(c.destination);
        osc.start(t0 + delay);
        osc.stop(t0 + delay + 0.5);
    }
}

export const soundService = {
    dependencies: ["bus_service", "notification"],
    start(env, { bus_service, notification }) {
        const odemknout = () => {
            const c = kontext();
            if (c && c.state === "suspended") c.resume();
        };
        document.addEventListener("pointerdown", odemknout, { once: true, capture: true });
        bus_service.subscribe("elite_vet_reservation/changed", (payload) => {
            if (!payload?.new_web) return;
            const ids = payload.web_ids || [];
            const nove = takeUnannounced(ids);
            if (!nove.length) return;
            (payload.web || []).forEach((label, i) => {
                if (nove.includes(ids[i])) {
                    notification.add("Nová žádost z webu: " + label, { type: "info", sticky: true });
                }
            });
            if (isSoundOn()) playChime();
        });
        bus_service.start();
    },
};

registry.category("services").add("elite_vet_reservation_sound", soundService);
