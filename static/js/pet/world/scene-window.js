/**
 * Okno sceny (spec v3.1 §3.4) — jeden wzorzec okien kontekstowych świata pupili: panel pupila w domku,
 * okna szpitala, album i nagrobki w ogrodzie. Okno żyje W scenie (position: absolute w section.pets-scene):
 *   - ≥ 1024 px: karta przy prawej krawędzi sceny (360 px, margines 16 px, przewijanie w środku);
 *     scena właściwa (.pets-stage) rezerwuje wtedy prawe 376 px (CSS: .pets-scene.has-window);
 *   - < 1024 px: arkusz od dołu sceny (max. 75% jej wysokości), uchwyt 44 px, przeciągnięcie w dół zamyka.
 *     Wysokość arkusza trafia do zmiennej --window-h na scenie (0 w trybie karty) — sceny mogą przesunąć
 *     wybrany obiekt nad arkusz (domek: pokój jedzie w górę).
 * Style: components/modals.css „Okno sceny (v3.1)”.
 *
 * API (kontrakt planu Task 4 → Task 5):
 *   PetsSceneWindow.attach(sceneEl) -> win        (ponowny attach tej samej sceny zwraca to samo okno)
 *     win.open({content, labelledBy, returnFocus, onClose, focus?, closeLabel?})
 *         otwiera; przy otwartym oknie podmienia treść bez animacji zamknięcia (poprzedni onClose NIE jest
 *         wołany). Fokus: domyślnie pierwszy fokusowalny element treści (albo samo okno); `focus: false` —
 *         fokus zostaje, gdzie był (np. klik w pupila, drugi klik = pat pat); `focus: <element>` — ten element.
 *     win.replace(content)  — podmiana treści przy otwartym oknie; fokus z usuniętej treści wraca na element
 *                             nowej treści o tym samym `data-window-key` (jeśli jest), inaczej na okno
 *     win.close({restoreFocus})  — zamyka, woła onClose, oddaje fokus na returnFocus (jeśli nadal w DOM)
 *                             albo na scenę; fokusu nie kradnie (tylko gdy był w oknie albo przepadł)
 *     win.isOpen() · win.body (kontener treści) · win.el (okno) · win.destroy()
 *   Zamykanie: przycisk ×, Esc, klik w puste tło sceny (sam sceneEl albo element z data-window-backdrop,
 *   poza przyciskami/linkami/polami), przeciągnięcie arkusza w dół. Klasa .has-window na scenie przy otwartym.
 * Bezpieczeństwo: okno nie wstawia HTML-a treści — dostaje gotowe węzły (dane użytkownika przez textContent
 * po stronie sceny); zero inline onclick.
 */
(function () {
    'use strict';

    if (window.PetsSceneWindow) return;

    var DESKTOP = '(min-width: 1024px)';
    var DRAG_CLOSE_PX = 90;
    var FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), ' +
        'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
    var OBJECT = 'a, button, input, select, textarea, label, summary, [role="button"], [data-window-ignore]';
    var CLOSE_SVG = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false" fill="none" ' +
        'stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';

    var windows = [];

    function isDesktop() {
        return !!(window.matchMedia && window.matchMedia(DESKTOP).matches);
    }

    function focusEl(node) {
        if (!node || typeof node.focus !== 'function') return;
        try { node.focus({ preventScroll: true }); } catch (e) { node.focus(); }
    }

    function visible(node) {
        return !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length);
    }

    function attach(sceneEl) {
        if (!sceneEl) return null;
        for (var i = 0; i < windows.length; i++) if (windows[i].scene === sceneEl) return windows[i];

        var panel = document.createElement('div');
        panel.className = 'pets-window';
        panel.setAttribute('role', 'dialog');
        panel.tabIndex = -1;
        panel.hidden = true;
        var grip = document.createElement('div');
        grip.className = 'pets-window__grip';
        grip.setAttribute('aria-hidden', 'true');
        var bar = document.createElement('span');
        bar.className = 'pets-window__grip-bar';
        grip.appendChild(bar);
        var closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'pets-window__close';
        closeBtn.innerHTML = CLOSE_SVG;
        var body = document.createElement('div');
        body.className = 'pets-window__body';
        panel.appendChild(grip);
        panel.appendChild(closeBtn);
        panel.appendChild(body);
        sceneEl.appendChild(panel);
        // Fokus po zamknięciu, gdy obiekt, który otworzył okno, zniknął
        if (!sceneEl.hasAttribute('tabindex')) sceneEl.setAttribute('tabindex', '-1');

        var open = false;
        var destroyed = false;
        var opts = {};
        var drag = null;
        var mq = window.matchMedia ? window.matchMedia(DESKTOP) : null;
        var resizeObs = null;

        var win = { scene: sceneEl, el: panel, body: body };

        // --- wysokość arkusza dla sceny (0 w trybie karty) ---------------------------------
        function syncHeight() {
            var h = open && !isDesktop() ? panel.offsetHeight : 0;
            sceneEl.style.setProperty('--window-h', h + 'px');
        }

        function onMode() {
            if (drag) endDrag(null, true);
            syncHeight();
        }

        // --- treść i fokus -----------------------------------------------------------------
        function setContent(content) {
            while (body.firstChild) body.removeChild(body.firstChild);
            if (content) body.appendChild(content);
        }

        function firstFocusable() {
            var list = body.querySelectorAll(FOCUSABLE);
            for (var k = 0; k < list.length; k++) if (visible(list[k])) return list[k];
            return null;
        }

        function applyFocus(target) {
            if (target === false) return;
            if (target && target.nodeType === 1 && body.contains(target)) focusEl(target);
            else focusEl(firstFocusable() || panel);
        }

        function setLabels(o) {
            if (o.labelledBy) panel.setAttribute('aria-labelledby', o.labelledBy);
            else panel.removeAttribute('aria-labelledby');
            closeBtn.setAttribute('aria-label', o.closeLabel || 'Zamknij okno');
        }

        win.open = function (o) {
            if (destroyed) return win;
            o = o || {};
            opts = {
                labelledBy: o.labelledBy || null,
                returnFocus: o.returnFocus || null,
                onClose: typeof o.onClose === 'function' ? o.onClose : null,
                closeLabel: o.closeLabel || null
            };
            setLabels(opts);
            setContent(o.content || null);
            if (!open) {
                open = true;
                panel.hidden = false;
                panel.classList.remove('is-dragging');
                panel.style.removeProperty('--drag');
                void panel.offsetWidth;        // start przejścia arkusza z pozycji „pod sceną”
                panel.classList.add('is-open');
                sceneEl.classList.add('has-window');
                if (window.ResizeObserver && !resizeObs) {
                    resizeObs = new ResizeObserver(syncHeight);
                    resizeObs.observe(panel);
                }
            }
            syncHeight();
            applyFocus(o.focus === undefined ? true : o.focus);
            return win;
        };

        win.replace = function (content) {
            if (destroyed || !open) return win;
            var active = document.activeElement;
            var hadFocus = !!(active && body.contains(active));
            var key = hadFocus && active.getAttribute ? active.getAttribute('data-window-key') : null;
            setContent(content || null);
            if (hadFocus) {
                var same = key ? body.querySelector('[data-window-key="' + key.replace(/["\\]/g, '\\$&') + '"]') : null;
                focusEl(same && visible(same) ? same : panel);
            }
            syncHeight();
            return win;
        };

        win.close = function (o) {
            if (destroyed || !open) return win;
            o = o || {};
            var active = document.activeElement;
            var focusInside = !!(active && (panel.contains(active)));
            var focusLost = !active || active === document.body;
            open = false;
            drag = null;
            panel.classList.remove('is-open', 'is-dragging');
            panel.style.removeProperty('--drag');
            panel.hidden = true;
            sceneEl.classList.remove('has-window');
            if (resizeObs) {
                resizeObs.disconnect();
                resizeObs = null;
            }
            syncHeight();
            var done = opts;
            opts = {};
            if (done.onClose) {
                try { done.onClose(); } catch (err) { if (window.console) console.error(err); }
            }
            setContent(null);
            if (o.restoreFocus !== false && (focusInside || focusLost || document.activeElement === document.body)) {
                var back = done.returnFocus;
                focusEl(back && document.body.contains(back) && visible(back) ? back : sceneEl);
            }
            return win;
        };

        win.isOpen = function () { return open; };

        // --- zamykanie: ×, Esc, tło sceny ---------------------------------------------------
        closeBtn.addEventListener('click', function () { win.close({ restoreFocus: true }); });

        function onKey(e) {
            if (e.key !== 'Escape' || !open || e.defaultPrevented || sceneEl.hidden) return;
            e.preventDefault();
            win.close({ restoreFocus: true });
        }
        document.addEventListener('keydown', onKey);

        // Faza przechwytywania: klik, który dopiero otwiera okno (obiekt sceny), widzi je jeszcze zamknięte
        function onBackdrop(e) {
            if (!open || panel.contains(e.target)) return;
            var t = e.target;
            var backdrop = t === sceneEl || (t.closest && t.closest('[data-window-backdrop]'));
            if (!backdrop || (t !== sceneEl && t.closest(OBJECT))) return;
            win.close({ restoreFocus: true });
        }
        sceneEl.addEventListener('click', onBackdrop, true);

        // --- arkusz: przeciągnięcie uchwytu w dół (pointer events = mysz, dotyk, rysik) -------
        grip.addEventListener('pointerdown', function (e) {
            if (!open || isDesktop()) return;
            drag = { y0: e.clientY, dy: 0, id: e.pointerId };
            try { grip.setPointerCapture(e.pointerId); } catch (err) { /* stare przeglądarki */ }
            panel.classList.add('is-dragging');
        });
        grip.addEventListener('pointermove', function (e) {
            if (!drag || e.pointerId !== drag.id) return;
            drag.dy = Math.max(0, e.clientY - drag.y0);
            panel.style.setProperty('--drag', drag.dy + 'px');
        });
        function endDrag(e, cancel) {
            if (!drag || (e && e.pointerId !== drag.id)) return;
            var dy = drag.dy;
            drag = null;
            panel.classList.remove('is-dragging');
            panel.style.removeProperty('--drag');
            if (!cancel && dy > DRAG_CLOSE_PX) win.close({ restoreFocus: true });
        }
        grip.addEventListener('pointerup', function (e) { endDrag(e, false); });
        grip.addEventListener('pointercancel', function (e) { endDrag(e, true); });

        // Zmiana trybu karta ↔ arkusz przy otwartym oknie (sidebar, obrót, przejście przez 1024 px):
        // treść i fokus zostają w tym samym węźle, przelicza się tylko wysokość dla sceny
        if (mq) {
            if (mq.addEventListener) mq.addEventListener('change', onMode);
            else if (mq.addListener) mq.addListener(onMode);
        }

        win.destroy = function () {
            if (destroyed) return;
            win.close({ restoreFocus: false });
            destroyed = true;
            document.removeEventListener('keydown', onKey);
            sceneEl.removeEventListener('click', onBackdrop, true);
            if (mq) {
                if (mq.removeEventListener) mq.removeEventListener('change', onMode);
                else if (mq.removeListener) mq.removeListener(onMode);
            }
            if (panel.parentNode) panel.parentNode.removeChild(panel);
            sceneEl.style.removeProperty('--window-h');
            windows = windows.filter(function (w) { return w !== win; });
        };

        windows.push(win);
        return win;
    }

    window.PetsSceneWindow = { attach: attach };
})();
