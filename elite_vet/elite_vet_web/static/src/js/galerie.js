/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";

// Blok Galerie. Fotky se nacitaji az pri zobrazeni stranky, takze se do
// ulozene stranky nikdy nezapisou a zmena v adminu se projevi hned.
// V editoru widget nebezi; pred editaci se zastavi a pas vyprazdni.
publicWidget.registry.EliteVetGalerie = publicWidget.Widget.extend({
    selector: ".s_vet_galerie",
    events: {
        "click .ev-gal-arr--prev": "_onPrev",
        "click .ev-gal-arr--next": "_onNext",
    },

    async willStart() {
        // <html lang="cs-CZ"> -> cs_CZ
        const lang = (document.documentElement.lang || "").replace("-", "_");
        this.fotky = await rpc("/elite_vet/galerie", { lang });
    },

    start() {
        this.track = this.el.querySelector(".ev-gal-track");
        this.prev = this.el.querySelector(".ev-gal-arr--prev");
        this.next = this.el.querySelector(".ev-gal-arr--next");
        if (!this.fotky.length) {
            this.el.classList.add("d-none");
            return this._super(...arguments);
        }
        for (const fotka of this.fotky) {
            const img = document.createElement("img");
            img.src = fotka.src;
            img.alt = fotka.alt;
            img.width = 500;
            img.height = 667;
            img.loading = "lazy";
            img.decoding = "async";
            img.setAttribute("fetchpriority", "low");
            const item = document.createElement("div");
            item.className = "ev-gal-item";
            item.append(img);
            this.track.append(item);
        }
        this._keepAnchor();
        this._updateArrows = this._updateArrows.bind(this);
        this.track.addEventListener("scroll", this._updateArrows, { passive: true });
        window.addEventListener("resize", this._updateArrows);
        this._updateArrows();
        return this._super(...arguments);
    },

    destroy() {
        // Editor po zastaveni widgetu uklada, co v bloku zbylo. Fotky ani
        // stav sipek tam zustat nesmi, jinak by se zase zmrazily natvrdo.
        if (this.track) {
            this.track.removeEventListener("scroll", this._updateArrows);
            window.removeEventListener("resize", this._updateArrows);
            this.track.replaceChildren();
            this.prev.hidden = false;
            this.next.hidden = false;
        }
        this.el.classList.remove("d-none");
        this._super(...arguments);
    },

    /**
     * Jedno listnuti = sirka pasu + mezera, tedy presne tri fotky dal.
     * Posledni strana se zarovna na konec, protoze dal pas nepusti.
     */
    _scroll(smer) {
        const mezera = parseFloat(getComputedStyle(this.track).columnGap) || 0;
        this.track.scrollBy({ left: smer * (this.track.clientWidth + mezera), behavior: "smooth" });
    },

    _onPrev() {
        this._scroll(-1);
    },

    _onNext() {
        this._scroll(1);
    },

    /**
     * Prohlizec skoci na kotvu (/#kontakt) driv, nez sem prijdou fotky.
     * Pas pak naroste a cil odjede dolu, takze se na nej dorovna znovu.
     */
    _keepAnchor() {
        const id = decodeURIComponent(location.hash.slice(1));
        const cil = id && document.getElementById(id);
        if (cil && this.el.compareDocumentPosition(cil) & Node.DOCUMENT_POSITION_FOLLOWING) {
            cil.scrollIntoView();
        }
    },

    _updateArrows() {
        const konec = this.track.scrollWidth - this.track.clientWidth;
        this.prev.hidden = this.track.scrollLeft <= 1;
        this.next.hidden = this.track.scrollLeft >= konec - 1;
    },
});

export default publicWidget.registry.EliteVetGalerie;
