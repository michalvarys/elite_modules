(function () {
    "use strict";

    const STORAGE_KEY = "elite_trafika_catalog_likes";

    function readLikes() {
        try {
            return new Set(JSON.parse(localStorage.getItem(STORAGE_KEY)) || []);
        } catch {
            return new Set();
        }
    }

    function saveLikes(likes) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify([...likes]));
        } catch {
            // Without storage the heart only forgets its state after a reload.
        }
    }

    async function sendLike(itemId, liked, source) {
        const response = await fetch("/katalog/zajem", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                id: Date.now(),
                params: { item_id: itemId, liked, source },
            }),
        });
        const data = await response.json();
        return Boolean(data.result && data.result.ok);
    }

    function setupLikes(page) {
        const likes = readLikes();
        for (const button of page.querySelectorAll(".o_tc_like")) {
            const itemId = Number(button.dataset.item);
            button.setAttribute("aria-pressed", String(likes.has(itemId)));
            button.addEventListener("click", async () => {
                const liked = !likes.has(itemId);
                button.disabled = true;
                button.setAttribute("aria-pressed", String(liked));
                let saved = false;
                try {
                    saved = await sendLike(itemId, liked, page.dataset.source);
                } catch {
                    saved = false;
                }
                if (saved) {
                    if (liked) {
                        likes.add(itemId);
                    } else {
                        likes.delete(itemId);
                    }
                    saveLikes(likes);
                } else {
                    button.setAttribute("aria-pressed", String(!liked));
                }
                button.disabled = false;
            });
        }
    }

    function setupFilters(page) {
        const filters = page.querySelectorAll(".o_tc_filter");
        const cards = page.querySelectorAll(".o_tc_card");
        for (const filter of filters) {
            filter.addEventListener("click", () => {
                const value = filter.dataset.filter;
                for (const other of filters) {
                    other.classList.toggle("active", other === filter);
                    other.setAttribute("aria-pressed", String(other === filter));
                }
                for (const card of cards) {
                    card.hidden = !(value === "all"
                        || card.dataset.kind === value
                        || (value === "in_store" && card.dataset.inStore === "1"));
                }
            });
        }
    }

    function start() {
        const page = document.querySelector(".o_tc_page");
        if (page) {
            setupLikes(page);
            setupFilters(page);
        }
    }

    // The frontend bundle loads lazily, usually after the document is parsed.
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})();
