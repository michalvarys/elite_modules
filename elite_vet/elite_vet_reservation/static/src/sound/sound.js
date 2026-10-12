/** @odoo-module **/
/**
 * Sound for a new web request – across all of Odoo, not just the board, so
 * reception hears it from any screen. The server sends the message over the bus
 * (models/live.py).
 *
 * Only requests this browser tab has not announced yet are announced: after a
 * page load the bus redelivers recent messages, so the chime and notification
 * would otherwise repeat on every refresh.
 *
 * The tone is generated with Web Audio (no sound file). Browsers only allow audio
 * after the first user interaction, so the first click "unlocks" it.
 * It can be muted with a button on the board; the choice applies to this browser.
 */
import { registry } from "@web/core/registry";

const SOUND_KEY = "elite_vet_reservation.sound";

export function isSoundOn() {
    try {
        return localStorage.getItem(SOUND_KEY) !== "0";
    } catch {
        return true;
    }
}

export function setSoundOn(enabled) {
    try {
        localStorage.setItem(SOUND_KEY, enabled ? "1" : "0");
    } catch {
        // private window / storage disabled: sound stays on
    }
}

const ANNOUNCED_KEY = "elite_vet_reservation.announced";

/** Return the ids this tab has not announced yet, and remember them. */
export function takeUnannounced(ids) {
    let announced = [];
    try {
        announced = JSON.parse(sessionStorage.getItem(ANNOUNCED_KEY) || "[]");
    } catch {
        announced = [];
    }
    const fresh = (ids || []).filter((id) => !announced.includes(id));
    if (fresh.length) {
        try {
            sessionStorage.setItem(ANNOUNCED_KEY, JSON.stringify([...announced, ...fresh].slice(-300)));
        } catch {
            // no storage: worst case it is announced again after a refresh
        }
    }
    return fresh;
}

let ctx = null;
function audioContext() {
    if (!ctx) {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) return null;
        ctx = new AC();
    }
    return ctx;
}

/** Short two-tone "ding-dong" (A5 → E6). */
export function playChime() {
    const c = audioContext();
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
        const unlockAudio = () => {
            const c = audioContext();
            if (c && c.state === "suspended") c.resume();
        };
        document.addEventListener("pointerdown", unlockAudio, { once: true, capture: true });
        bus_service.subscribe("elite_vet_reservation/changed", (payload) => {
            if (!payload?.new_web) return;
            const ids = payload.web_ids || [];
            const fresh = takeUnannounced(ids);
            if (!fresh.length) return;
            (payload.web || []).forEach((label, i) => {
                if (fresh.includes(ids[i])) {
                    notification.add("Nová žádost z webu: " + label, { type: "info", sticky: true });
                }
            });
            if (isSoundOn()) playChime();
        });
        bus_service.start();
    },
};

registry.category("services").add("elite_vet_reservation_sound", soundService);
