/* Request 26. 11.: a web reservation request is a lead - report it to Google Analytics 4 and Meta.
 *
 * The tags themselves (gtag.js with the GA4 id, the Meta Pixel) are in the website's own head code,
 * not in this module; this only sends the event when they are on the page:
 *  - GA4: "generate_lead" (a recommended event; mark it as a key event in GA4 and import it into
 *    Google Ads as a conversion);
 *  - Meta: the standard "Lead" event to every initialised pixel, with eventID for deduplication
 *    against a later server-side send (Conversions API).
 * No personal data is sent - only the event id and the procedure name.
 * `lead` is the "lead" part of the /rezervace/api/submit answer ({event_id, procedure}).
 */
(function (root) {
    "use strict";
    root.EliteVetTrackLead = function (lead) {
        if (!lead || !lead.event_id) return;
        try {
            if (typeof root.gtag === "function") {
                root.gtag("event", "generate_lead", {
                    lead_source: "rezervace_web",
                    procedure: lead.procedure || "",
                });
            }
        } catch (e) { /* tracking must never break the booking */ }
        try {
            if (typeof root.fbq === "function") {
                root.fbq("track", "Lead", { content_name: lead.procedure || "", content_category: "rezervace" },
                    { eventID: lead.event_id });
            }
        } catch (e) { /* tracking must never break the booking */ }
    };
})(window);
