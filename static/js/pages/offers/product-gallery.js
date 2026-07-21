/**
 * Galeria produktu na stronie ofertowej.
 * Pionowy (desktop) / poziomy (mobile ≤640px) pasek miniaturek z chevronami.
 * Klik chevronu/miniaturki przełącza aktywne zdjęcie, podmienia duże zdjęcie
 * i dociąga aktywną miniaturkę na środek (skrajne bez wymuszania środka).
 */
(function () {
    'use strict';

    var mobile = window.matchMedia('(max-width: 640px)');

    function initGallery(root) {
        var strip = root.querySelector('.gallery-strip');
        var viewport = root.querySelector('.gallery-strip-viewport');
        var thumbs = Array.prototype.slice.call(root.querySelectorAll('.gallery-thumb'));
        var prevBtn = root.querySelector('.gallery-chevron-prev');
        var nextBtn = root.querySelector('.gallery-chevron-next');
        var fadeStart = root.querySelector('.gallery-fade-start');
        var fadeEnd = root.querySelector('.gallery-fade-end');
        var mainImg = root.querySelector('.gallery-main-image');
        if (!strip || thumbs.length === 0) return;

        var active = 0;

        function vertical() { return !mobile.matches; }

        function render() {
            var isV = vertical();
            var t0 = thumbs[0];
            var size = isV ? t0.offsetHeight : t0.offsetWidth;
            var gap = parseFloat(getComputedStyle(strip).gap) || 0;
            var step = size + gap;
            var vpSize = isV ? viewport.clientHeight : viewport.clientWidth;
            var content = thumbs.length * size + (thumbs.length - 1) * gap;
            var maxScroll = Math.max(0, content - vpSize);

            var target = active * step + size / 2 - vpSize / 2;
            if (target < 0) target = 0;
            if (target > maxScroll) target = maxScroll;

            strip.style.transform = isV
                ? 'translateY(' + (-Math.round(target)) + 'px)'
                : 'translateX(' + (-Math.round(target)) + 'px)';

            thumbs.forEach(function (t, i) {
                t.classList.toggle('active', i === active);
            });

            if (prevBtn) prevBtn.disabled = (active === 0);
            if (nextBtn) nextBtn.disabled = (active === thumbs.length - 1);

            if (fadeStart) fadeStart.style.opacity = (target > 0.5) ? '1' : '0';
            if (fadeEnd) fadeEnd.style.opacity = (target < maxScroll - 0.5) ? '1' : '0';

            if (mainImg) {
                var src = thumbs[active].getAttribute('data-src');
                var full = thumbs[active].getAttribute('data-full-src');
                if (src) mainImg.setAttribute('src', src);
                if (full) mainImg.setAttribute('data-full-src', full);
            }
        }

        function setActive(i) {
            if (i < 0) i = 0;
            if (i > thumbs.length - 1) i = thumbs.length - 1;
            active = i;
            render();
        }

        thumbs.forEach(function (t, i) {
            t.addEventListener('click', function () { setActive(i); });
        });
        if (prevBtn) prevBtn.addEventListener('click', function () { setActive(active - 1); });
        if (nextBtn) nextBtn.addEventListener('click', function () { setActive(active + 1); });

        var resizeTimer;
        window.addEventListener('resize', function () {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(render, 120);
        });
        if (mobile.addEventListener) {
            mobile.addEventListener('change', render);
        }

        render();
    }

    function initAll() {
        document.querySelectorAll('[data-gallery]').forEach(initGallery);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
})();
