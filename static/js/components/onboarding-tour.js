/**
 * Onboarding Tour — Shepherd.js
 * Interactive guided tour for new client users
 */
(function() {
    'use strict';

    // -------------------------------------------------------------------------
    // CONFIGURATION
    // -------------------------------------------------------------------------

    // Progress bar sections (Intro and Finish are fullscreen — not shown in progress bar)
    var SECTIONS = [
        { name: 'Dashboard', steps: ['metrics', 'exclusive', 'matrix', 'exclusive-open', 'recent-orders', 'badges'] },
        { name: 'Topbar', steps: ['search', 'facebook', 'notifications', 'profile'] },
        { name: 'Menu', steps: ['nav-dashboard', 'nav-orders', 'nav-confirmations', 'nav-shipping', 'nav-collection', 'nav-achievements', 'nav-help', 'finish'] }
    ];

    // -------------------------------------------------------------------------
    // HELPERS
    // -------------------------------------------------------------------------

    function isMobile() {
        return window.matchMedia('(max-width: 768px)').matches;
    }

    function getActiveStepIds(tour) {
        return tour.steps
            .filter(function(s) { return !s.options._skipWhen || !s.options._skipWhen(); })
            .map(function(s) { return s.id; });
    }

    function buildProgressHTML(stepId, tour) {
        var activeIds = getActiveStepIds(tour);
        var segmentsHTML = '';
        var sectionName = '';
        var currentIdx = activeIds.indexOf(stepId);
        var runningIdx = 0;

        for (var s = 0; s < SECTIONS.length; s++) {
            var sec = SECTIONS[s];
            var activeInSection = sec.steps.filter(function(id) { return activeIds.indexOf(id) !== -1; });
            var count = activeInSection.length;
            var fillPercent = 0;

            if (currentIdx >= runningIdx + count) {
                fillPercent = 100;
            } else if (currentIdx >= runningIdx) {
                sectionName = sec.name;
                var posInSection = currentIdx - runningIdx;
                fillPercent = Math.round(((posInSection + 1) / count) * 100);
            }

            if (currentIdx >= runningIdx && currentIdx < runningIdx + count) {
                sectionName = sec.name;
            }

            segmentsHTML += '<div class="tour-progress-segment">' +
                '<div class="tour-progress-fill" style="width:' + fillPercent + '%"></div>' +
                '</div>';
            runningIdx += count;
        }

        return '<div class="tour-section-label">' + sectionName + '</div>' +
               '<div class="tour-progress">' + segmentsHTML + '</div>';
    }

    function makeHeader(stepId, title, tour) {
        return '<div class="tour-header">' +
               buildProgressHTML(stepId, tour) +
               '<h3 class="tour-step-title">' + title + '</h3>' +
               '</div>';
    }

    function makeBody(text) {
        return '<div class="tour-body"><p class="tour-text">' + text + '</p></div>';
    }

    function completeTour(tour) {
        tour.complete();
        // Mark tour as seen via backend
        fetch('/client/tour-completed', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        }).catch(function() {
            // Fallback: store in localStorage so tour doesn't repeat on network failure
            try { localStorage.setItem('thunderorders_tour_seen', '1'); } catch(e) {}
        });
    }

    function getCSRFToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) return meta.getAttribute('content');
        var match = document.cookie.match(/csrf_token=([^;]+)/);
        return match ? match[1] : '';
    }

    function openSidebarIfNeeded() {
        if (isMobile()) {
            var overlay = document.getElementById('mobileMenuOverlay');
            if (overlay && !overlay.classList.contains('active')) {
                var btn = document.getElementById('mobileMenuBtn');
                if (btn) btn.click();
            }
        } else {
            var sidebar = document.getElementById('sidebar');
            if (sidebar && sidebar.getAttribute('data-collapsed') === 'true') {
                var toggle = document.getElementById('sidebarToggle');
                if (toggle) toggle.click();
            }
        }
    }

    function closeSidebarIfMobile() {
        if (isMobile()) {
            var closeBtn = document.getElementById('mobileMenuClose');
            if (closeBtn) closeBtn.click();
        }
    }

    // -------------------------------------------------------------------------
    // FULLSCREEN OVERLAY
    // -------------------------------------------------------------------------

    var fullscreenEl = null;

    function showFullscreen(emoji, title, text, btnText, onBtnClick) {
        var shepherdEl = document.querySelector('.shepherd-element');
        if (shepherdEl) shepherdEl.style.display = 'none';

        fullscreenEl = document.createElement('div');
        fullscreenEl.className = 'tour-fullscreen-overlay';
        fullscreenEl.innerHTML =
            '<div class="tour-fullscreen-content">' +
                '<span class="tour-fullscreen-emoji">' + emoji + '</span>' +
                '<h2 class="tour-fullscreen-title">' + title + '</h2>' +
                '<p class="tour-fullscreen-text">' + text + '</p>' +
                '<button class="tour-fullscreen-btn">' + btnText + '</button>' +
            '</div>';

        document.body.appendChild(fullscreenEl);
        fullscreenEl.querySelector('.tour-fullscreen-btn').addEventListener('click', function() {
            removeFullscreen();
            onBtnClick();
        });
    }

    function removeFullscreen() {
        if (fullscreenEl && fullscreenEl.parentNode) {
            fullscreenEl.parentNode.removeChild(fullscreenEl);
            fullscreenEl = null;
        }
        var shepherdEl = document.querySelector('.shepherd-element');
        if (shepherdEl) shepherdEl.style.display = '';
    }


    // -------------------------------------------------------------------------
    // STEP DEFINITIONS
    // -------------------------------------------------------------------------

    function getStepDefs(tour) {
        return [
            // --- SECTION: Intro ---
            {
                id: 'welcome',
                isFullscreen: true,
                fullscreenConfig: {
                    emoji: '🎉',
                    title: 'Witaj w ThunderOrders!',
                    text: 'Cześć! Zaraz pokażę Ci co tu mamy. Spokojnie — krócej niż robienie kawy ☕',
                    btnText: 'Zaczynamy! 🚀'
                }
            },

            // --- SECTION: Dashboard ---
            {
                id: 'metrics',
                attachTo: { element: '.dashboard-metrics', on: 'bottom' },
                title: 'Twoje zamówienia w pigułce',
                text: 'Tu masz wszystko jak na dłoni — ile zamówień leci, ile dostarczonych, a ile czeka na kasę 💰'
            },
            {
                id: 'exclusive',
                attachTo: { element: '#exclusiveWidget', on: 'bottom' },
                title: 'Strony Exclusive',
                text: 'Aktywne oferty Exclusive — nie trwają wiecznie, lepiej nie przegap! 🔥 Jak działają strony Exclusive? Dowiesz się w sekcji Pomoc, o której opowiem za chwilę 😉',
                skipWhen: function() { return !document.querySelector('#exclusiveWidget'); }
            },
            {
                id: 'matrix',
                attachTo: { element: '.exclusive-matrix-btn', on: 'bottom' },
                title: 'Macierz seta',
                text: 'Sprawdź postęp w secie — jak kolekcjonowanie Pokémonów 😄',
                skipWhen: function() { return !document.querySelector('.exclusive-matrix-btn'); }
            },
            {
                id: 'exclusive-open',
                attachTo: { element: '.exclusive-action-btn', on: 'bottom' },
                title: 'Otwórz stronę Exclusive',
                text: 'Kliknij tutaj żeby przejść na stronę Exclusive i złożyć zamówienie. To Twoja brama do limitowanych produktów! 🚪',
                skipWhen: function() { return !document.querySelector('.exclusive-action-btn'); }
            },
            {
                id: 'recent-orders',
                attachTo: { element: '#recentOrdersWidget', on: 'top' },
                title: 'Ostatnie zamówienia',
                text: 'Ostatnie zamówienia ze statusami. Klik i szczegóły — bez szukania po szufladach 🗂️'
            },
            {
                id: 'badges',
                attachTo: { element: '#achievements-widget', on: 'bottom' },
                title: 'Moje odznaki',
                text: 'Twoje trofea! Za każde osiągnięcie dostajesz odznakę. Zbierasz je wszystkie? 🎖️'
            },

            // --- SECTION: Topbar ---
            {
                id: 'search',
                attachTo: {
                    element: function() { return isMobile() ? '#mobileSearchBtn' : '#globalSearchBtn'; },
                    on: 'bottom'
                },
                title: 'Wyszukiwarka',
                text: 'Szukasz czegoś konkretnego? Wpisz tutaj i znajdź zamówienie, produkt, cokolwiek 🕵️',
                beforeShowFn: function() { closeSidebarIfMobile(); }
            },
            {
                id: 'facebook',
                attachTo: { element: '.topbar-fb-btn', on: 'bottom' },
                title: 'Grupa na Facebooku',
                text: 'Tu nas znajdziesz na Facebooku — wpadaj, gadamy o nowościach i dropach 💬',
                skipWhen: function() { return isMobile(); }
            },
            {
                id: 'notifications',
                attachTo: {
                    element: function() { return isMobile() ? '#mobilePushBtn' : '.push-bell-wrapper'; },
                    on: 'bottom'
                },
                title: 'Powiadomienia',
                text: 'Dzwoneczek = Twój najlepszy kumpel 🔔 Włącz powiadomienia, a nic Ci nie umknie. Pro tip: zainstaluj aplikację (Dodaj do ekranu głównego) i miej powiadomienia push na żywo — jak SMS, tylko lepiej! 📱'
            },
            {
                id: 'profile',
                attachTo: { element: '.topbar-user-dropdown', on: 'bottom-end' },
                title: 'Mój Profil',
                text: 'Tu zarządzasz sobą 😎 Profil, tryb ciemny dla nocnych marków 🌙 i wylogowanie',
                skipWhen: function() { return isMobile(); }
            },

            // --- SECTION: Menu (Sidebar) ---
            {
                id: 'nav-dashboard',
                attachTo: { element: '.sidebar-menu .sidebar-item:nth-child(1) .sidebar-link', on: 'right' },
                title: 'Dashboard',
                text: 'Zawsze wracasz tutaj — Twoja baza wypadowa. Jak ekran główny, tylko lepszy 🏡',
                beforeShowFn: function() { openSidebarIfNeeded(); },
                noScroll: true
            },
            {
                id: 'nav-orders',
                attachTo: { element: '.sidebar-menu .sidebar-item:nth-child(2) .sidebar-link', on: 'right' },
                title: 'Moje zamówienia',
                text: 'Centrum dowodzenia — wszystkie zamówienia, filtry, statusy. Tu się dzieje magia 🚀',
                noScroll: true
            },
            {
                id: 'nav-confirmations',
                attachTo: { element: '.sidebar-menu .sidebar-item:nth-child(3) .sidebar-link', on: 'right' },
                title: 'Potwierdzenia',
                text: 'Tu potwierdzasz płatności i dostawy. Żeby było czysto i jasno kto co zapłacił 🧾',
                noScroll: true
            },
            {
                id: 'nav-shipping',
                attachTo: { element: '.sidebar-menu .sidebar-item:nth-child(4) .sidebar-category-header', on: 'right' },
                title: 'Wysyłka',
                text: 'Tu zlecasz wysyłki i zarządzasz adresami dostawy. Dwa w jednym — Zlecenia i Adresy 📬',
                noScroll: true
            },
            {
                id: 'nav-collection',
                attachTo: { element: '.sidebar-menu .sidebar-item:nth-child(5) .sidebar-link', on: 'right' },
                title: 'Moja Kolekcja',
                text: 'Twoja półka z trofeami — wszystkie produkty które już masz. Flex guaranteed 💎',
                noScroll: true
            },
            {
                id: 'nav-achievements',
                attachTo: { element: '.sidebar-menu .sidebar-item:nth-child(6) .sidebar-link', on: 'right' },
                title: 'Osiągnięcia',
                text: 'Odznaki, levele, progressy — dla tych co lubią zbierać 100% 🎮',
                noScroll: true
            },

            {
                id: 'nav-help',
                attachTo: { element: '.sidebar-menu .sidebar-item:nth-child(7) .sidebar-link', on: 'right' },
                title: 'Pomoc',
                text: 'Nie wiesz jak coś działa? Tu masz poradniki — zamówienia, płatności, wysyłka, konto. Wszystko opisane krok po kroku 📖',
                noScroll: true
            },

            // --- SECTION: Finish ---
            {
                id: 'finish',
                isFullscreen: true,
                fullscreenConfig: {
                    emoji: '🎊',
                    title: 'Gotowe!',
                    text: 'To tyle! Jesteś gotowy na zakupy 🛒 Przycisk "Przewodnik" na dashboardzie pozwoli Ci powtórzyć ten tour. Powodzenia! 💪',
                    btnText: 'Zamknij 🎉'
                },
                beforeShowFn: function() { closeSidebarIfMobile(); }
            }
        ];
    }

    // -------------------------------------------------------------------------
    // TOUR CREATION
    // -------------------------------------------------------------------------

    function createTour() {
        var tour = new Shepherd.Tour({
            useModalOverlay: true,
            defaultStepOptions: {
                cancelIcon: { enabled: false },
                scrollTo: { behavior: 'smooth', block: 'center' },
                modalOverlayOpeningPadding: 8,
                modalOverlayOpeningRadius: 12
            }
        });

        var stepDefs = getStepDefs(tour);

        stepDefs.forEach(function(def, idx) {
            var isLast = (idx === stepDefs.length - 1);

            var stepConfig = {
                id: def.id,
                _skipWhen: def.skipWhen || null
            };

            // Skip logic
            if (def.skipWhen) {
                stepConfig.showOn = function() { return !def.skipWhen(); };
            }

            // Fullscreen steps
            if (def.isFullscreen) {
                stepConfig.attachTo = undefined;
                stepConfig.scrollTo = false;
                stepConfig.buttons = [];
                stepConfig.beforeShowPromise = function() {
                    return new Promise(function(resolve) {
                        if (def.beforeShowFn) def.beforeShowFn();
                        var onAction = isLast
                            ? function() { completeTour(tour); }
                            : function() { tour.next(); };
                        showFullscreen(
                            def.fullscreenConfig.emoji,
                            def.fullscreenConfig.title,
                            def.fullscreenConfig.text,
                            def.fullscreenConfig.btnText,
                            onAction
                        );
                        setTimeout(resolve, 50);
                    });
                };
            } else {
                // Regular popover steps
                var attachConfig = def.attachTo;
                // Keep string/object selectors as-is; resolve functions in beforeShowPromise
                if (attachConfig && typeof attachConfig.element === 'function') {
                    // Store function ref, resolve lazily before each show
                    stepConfig._elemFn = attachConfig.element;
                    stepConfig._elemOn = attachConfig.on;
                    attachConfig = { element: attachConfig.element(), on: attachConfig.on };
                }
                stepConfig.attachTo = attachConfig;
                stepConfig.scrollTo = def.noScroll ? false : { behavior: 'smooth', block: 'center' };

                // beforeShowPromise: run beforeShowFn + re-resolve dynamic elements
                (function(currentDef, currentStepConfig) {
                    stepConfig.beforeShowPromise = function() {
                        return new Promise(function(resolve) {
                            if (currentDef.beforeShowFn) currentDef.beforeShowFn();
                            // Re-resolve dynamic element selector
                            if (currentStepConfig._elemFn) {
                                var el = currentStepConfig._elemFn();
                                if (el) {
                                    var step = tour.steps.find(function(s) { return s.id === currentDef.id; });
                                    if (step) {
                                        step.updateStepOptions({ attachTo: { element: el, on: currentStepConfig._elemOn } });
                                    }
                                }
                            }
                            setTimeout(resolve, currentDef.beforeShowFn ? 200 : 50);
                        });
                    };
                })(def, stepConfig);

                // Custom rendering in when.show
                (function(currentDef, currentIsLast) {
                    stepConfig.when = {
                        hide: function() {
                            if (currentDef.afterHideFn) currentDef.afterHideFn();
                        },
                        show: function() {
                            removeFullscreen();
                            var step = tour.getCurrentStep();
                            if (!step) return;
                            var el = step.getElement();
                            if (!el) return;
                            var content = el.querySelector('.shepherd-content');
                            if (!content) return;

                            content.innerHTML =
                                makeHeader(currentDef.id, currentDef.title, tour) +
                                makeBody(currentDef.text) +
                                '<div class="tour-footer"></div>';

                            var footer = content.querySelector('.tour-footer');

                            // Close button
                            var skipBtn = document.createElement('button');
                            skipBtn.textContent = 'Zamknij';
                            skipBtn.className = 'tour-btn tour-btn-skip';
                            skipBtn.addEventListener('click', function() { completeTour(tour); });
                            footer.appendChild(skipBtn);

                            // Back button (not on first regular step)
                            var currentIndex = tour.steps.indexOf(tour.getCurrentStep());
                            if (currentIndex > 1) {
                                var backBtn = document.createElement('button');
                                backBtn.textContent = '← Wstecz';
                                backBtn.className = 'tour-btn tour-btn-back';
                                backBtn.addEventListener('click', function() { tour.back(); });
                                footer.appendChild(backBtn);
                            }

                            // Next button
                            var nextBtn = document.createElement('button');
                            nextBtn.textContent = currentIsLast ? 'Zamknij 🎉' : 'Dalej →';
                            nextBtn.className = 'tour-btn tour-btn-next';
                            nextBtn.addEventListener('click', function() {
                                if (currentIsLast) {
                                    completeTour(tour);
                                } else {
                                    tour.next();
                                }
                            });
                            footer.appendChild(nextBtn);
                        }
                    };
                })(def, isLast);
            }

            tour.addStep(stepConfig);
        });

        // Cleanup on complete/cancel
        tour.on('complete', function() { removeFullscreen(); });
        tour.on('cancel', function() { removeFullscreen(); });

        // Responsive swap
        setupResponsiveSwap(tour);

        return tour;
    }

    // -------------------------------------------------------------------------
    // RESPONSIVE SWAP
    // -------------------------------------------------------------------------

    function setupResponsiveSwap(tour) {
        var mql = window.matchMedia('(max-width: 768px)');
        function onViewportChange() {
            if (!tour.isActive()) return;
            var current = tour.getCurrentStep();
            if (!current) return;
            current.hide();
            current.show();
        }
        if (mql.addEventListener) {
            mql.addEventListener('change', onViewportChange);
        } else {
            mql.addListener(onViewportChange);
        }
    }

    // -------------------------------------------------------------------------
    // PUBLIC API
    // -------------------------------------------------------------------------

    window.ThunderTour = {
        start: function() {
            if (typeof Shepherd === 'undefined') {
                console.warn('Shepherd.js not loaded');
                return;
            }
            var tour = createTour();
            tour.start();
        }
    };

    // Auto-start + restart button
    document.addEventListener('DOMContentLoaded', function() {
        var shouldShow = document.body.getAttribute('data-show-tour') === 'true';
        var localFallback = false;
        try { localFallback = localStorage.getItem('thunderorders_tour_seen') === '1'; } catch(e) {}

        if (shouldShow && !localFallback) {
            // Wait for popups to finish before starting tour
            document.addEventListener('popups-all-closed', function() {
                setTimeout(function() { window.ThunderTour.start(); }, 500);
            }, { once: true });

            // Fallback: if no popups system or it never fires, start after 5s
            setTimeout(function() {
                if (typeof Shepherd !== 'undefined' && !Shepherd.activeTour) {
                    window.ThunderTour.start();
                }
            }, 5000);
        }

        var restartBtn = document.getElementById('restartTourBtn');
        if (restartBtn) {
            restartBtn.addEventListener('click', function() {
                window.ThunderTour.start();
            });
        }
    });

})();
