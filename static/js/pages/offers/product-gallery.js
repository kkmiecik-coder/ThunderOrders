/**
 * Galeria produktu na stronie ofertowej.
 * Pionowy (desktop) / poziomy (mobile ≤640px) pasek miniaturek z chevronami.
 * Klik chevronu/miniaturki przełącza aktywne zdjęcie, podmienia duże zdjęcie
 * i dociąga aktywną miniaturkę na środek (skrajne bez wymuszania środka).
 *
 * Dodatkowo: nawigacja w powiększeniu (lightbox) — strzałki po bokach + klawisze
 * ← →, zapętlanie na końcach, a wybór synchronizuje się z dużym podglądem.
 */
(function () {
    'use strict';

    var mobile = window.matchMedia('(max-width: 640px)');

    // ---- Wspólny stan lightboxa ----
    var lb = { box: null, img: null, prev: null, next: null, state: null };

    function showLbNav(show) {
        if (lb.prev) lb.prev.style.display = show ? '' : 'none';
        if (lb.next) lb.next.style.display = show ? '' : 'none';
    }

    function lbStep(dir) {
        if (!lb.state || !lb.img) return;
        var imgs = lb.state.images;
        var n = imgs.length;
        if (n < 2) return;
        lb.state.index = (lb.state.index + dir + n) % n; // zapętlanie
        lb.img.setAttribute('src', imgs[lb.state.index]);
        // synchronizacja z dużym podglądem (po zamknięciu zostaje ostatnio oglądane)
        if (typeof lb.state.setActive === 'function') {
            lb.state.setActive(lb.state.index);
        }
    }

    function ensureLightboxNav() {
        lb.box = document.getElementById('imageLightbox');
        if (!lb.box) return;
        lb.img = document.getElementById('lightboxImage');
        lb.prev = lb.box.querySelector('.image-lightbox-prev');
        lb.next = lb.box.querySelector('.image-lightbox-next');
        if (lb.prev && lb.next) return; // już utworzone

        var prevSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="22" height="22"><polyline points="15 18 9 12 15 6"/></svg>';
        var nextSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="22" height="22"><polyline points="9 18 15 12 9 6"/></svg>';

        lb.prev = document.createElement('button');
        lb.prev.type = 'button';
        lb.prev.className = 'image-lightbox-nav image-lightbox-prev';
        lb.prev.setAttribute('aria-label', 'Poprzednie zdjęcie');
        lb.prev.innerHTML = prevSvg;

        lb.next = document.createElement('button');
        lb.next.type = 'button';
        lb.next.className = 'image-lightbox-nav image-lightbox-next';
        lb.next.setAttribute('aria-label', 'Następne zdjęcie');
        lb.next.innerHTML = nextSvg;

        lb.box.appendChild(lb.prev);
        lb.box.appendChild(lb.next);

        lb.prev.addEventListener('click', function (e) { e.stopPropagation(); lbStep(-1); });
        lb.next.addEventListener('click', function (e) { e.stopPropagation(); lbStep(1); });

        showLbNav(false);
    }

    function initGallery(root) {
        var strip = root.querySelector('.gallery-strip');
        var viewport = root.querySelector('.gallery-strip-viewport');
        var thumbs = Array.prototype.slice.call(root.querySelectorAll('.gallery-thumb'));
        var prevBtn = root.querySelector('.gallery-chevron-prev');
        var nextBtn = root.querySelector('.gallery-chevron-next');
        var fadeStart = root.querySelector('.gallery-fade-start');
        var fadeEnd = root.querySelector('.gallery-fade-end');
        var mainImg = root.querySelector('.gallery-main-image');
        var mainWrap = root.querySelector('.gallery-main');
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

        // Klik w duże zdjęcie otwiera lightbox (przez openLightbox) — tu tylko
        // podpinamy nawigację: lista pełnych zdjęć + aktualny indeks + sync.
        if (mainWrap) {
            mainWrap.addEventListener('click', function () {
                lb.state = {
                    images: thumbs.map(function (t) { return t.getAttribute('data-full-src'); }),
                    index: active,
                    setActive: setActive
                };
                showLbNav(thumbs.length > 1);
            });
        }

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
        ensureLightboxNav();
        document.querySelectorAll('[data-gallery]').forEach(initGallery);

        // Klik w zdjęcie NIEbędące galerią (warianty, pojedyncze zdjęcia) —
        // ukryj strzałki lightboxa (te obrazki nie mają nawigacji).
        document.addEventListener('click', function (e) {
            var wrap = e.target.closest ? e.target.closest('.zoomable-image-wrapper') : null;
            if (!wrap) return;
            if (wrap.classList.contains('gallery-main')) return; // obsłużone przez galerię
            lb.state = null;
            showLbNav(false);
        });

        // Strzałki klawiatury w otwartym lightboxie
        document.addEventListener('keydown', function (e) {
            if (!lb.box || !lb.box.classList.contains('active') || !lb.state) return;
            if (e.key === 'ArrowLeft') { e.preventDefault(); lbStep(-1); }
            else if (e.key === 'ArrowRight') { e.preventDefault(); lbStep(1); }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
})();
