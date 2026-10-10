(function () {
    'use strict';

    function init() {
        var toggle = document.getElementById('vet-hamburger-btn');
        var menu = document.getElementById('vet-mobile-menu');
        if (toggle && menu) {
            toggle.addEventListener('click', function () {
                var isOpen = menu.classList.toggle('vet-mobile-open');
                toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
            });
            menu.querySelectorAll('a').forEach(function (link) {
                link.addEventListener('click', function () {
                    menu.classList.remove('vet-mobile-open');
                    toggle.setAttribute('aria-expanded', 'false');
                });
            });
        }

        // Smooth scroll for in-page anchors
        document.querySelectorAll('a[href^="#"]').forEach(function (link) {
            link.addEventListener('click', function (e) {
                var id = link.getAttribute('href');
                if (id && id.length > 1) {
                    var target = document.querySelector(id);
                    if (target) {
                        e.preventDefault();
                        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }
                }
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
