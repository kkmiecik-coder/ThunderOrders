/**
 * ThunderOrders - Popup Announcements Engine
 * Globalny silnik wyświetlania popupów/ogłoszeń dla zalogowanych użytkowników
 * Ładowany w base.html, pobiera aktywne popupy z API i wyświetla je kolejno.
 */

(function() {
    'use strict';

    let popupsQueue = [];
    let currentPopup = null;
    let currentUserId = null;
    let popupShownAt = null;

    // ==========================================
    // Inicjalizacja
    // ==========================================

    function init() {
        // Nasłuchuj na kliknięcia logout - czyść sessionStorage popupów
        setupLogoutCleanup();

        // Popupy wyświetlamy tylko na dashboardzie
        if (!window.location.pathname.endsWith('/dashboard')) return;

        fetchActivePopups();
    }

    /** Czyści klucze popup_seen_ z sessionStorage */
    function clearPopupKeys() {
        var keysToRemove = [];
        for (var i = 0; i < sessionStorage.length; i++) {
            var key = sessionStorage.key(i);
            if (key && key.startsWith('popup_seen_')) {
                keysToRemove.push(key);
            }
        }
        for (var j = 0; j < keysToRemove.length; j++) {
            sessionStorage.removeItem(keysToRemove[j]);
        }
        sessionStorage.removeItem('popup_user_id');
    }

    /** Nasłuchuje kliknięcia linku logout i czyści popup keys */
    function setupLogoutCleanup() {
        document.addEventListener('click', function(e) {
            var link = e.target.closest('a[href*="/auth/logout"]');
            if (link) {
                clearPopupKeys();
            }
        });
    }

    /** Czyści klucze popup_seen_ gdy zmienił się user (przelogowanie na inne konto) */
    function handleUserChange(userId) {
        var lastUser = sessionStorage.getItem('popup_user_id');
        if (lastUser && lastUser !== String(userId)) {
            clearPopupKeys();
        }
        sessionStorage.setItem('popup_user_id', String(userId));
    }

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    /** Przyciemnia kolor HEX o podany procent (0-100) */
    function darkenColor(hex, percent) {
        hex = hex.replace('#', '');
        if (hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
        const r = Math.max(0, Math.round(parseInt(hex.substring(0, 2), 16) * (1 - percent / 100)));
        const g = Math.max(0, Math.round(parseInt(hex.substring(2, 4), 16) * (1 - percent / 100)));
        const b = Math.max(0, Math.round(parseInt(hex.substring(4, 6), 16) * (1 - percent / 100)));
        return '#' + [r, g, b].map(c => c.toString(16).padStart(2, '0')).join('');
    }

    /** Zwraca kolor tekstu (biały/ciemny) na podstawie luminancji tła */
    function getContrastText(hex) {
        hex = hex.replace('#', '');
        if (hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
        const r = parseInt(hex.substring(0, 2), 16);
        const g = parseInt(hex.substring(2, 4), 16);
        const b = parseInt(hex.substring(4, 6), 16);
        const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
        return luminance > 0.55 ? '#212121' : '#ffffff';
    }

    // ==========================================
    // Pobieranie popupów z API
    // ==========================================

    function fetchActivePopups() {
        fetch('/api/popups/active')
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    // Wykryj zmianę usera i wyczyść stare klucze
                    if (data.user_id) {
                        currentUserId = data.user_id;
                        handleUserChange(data.user_id);
                    }

                    if (data.popups && data.popups.length > 0) {
                        // Filtruj every_login przez sessionStorage (deduplikacja w ramach sesji)
                        popupsQueue = data.popups.filter(popup => {
                            if (popup.display_mode === 'every_login') {
                                const key = `popup_seen_${popup.id}`;
                                if (sessionStorage.getItem(key)) {
                                    return false;
                                }
                            }
                            return true;
                        });

                        if (popupsQueue.length > 0) {
                            showNextPopup();
                        }
                    }
                }
            })
            .catch(() => {
                // Cichy błąd - nie przerywaj UX
            });
    }

    // ==========================================
    // Wyświetlanie popupa
    // ==========================================

    function showNextPopup() {
        if (popupsQueue.length === 0) return;

        currentPopup = popupsQueue.shift();
        popupShownAt = Date.now();
        renderPopup(currentPopup);
        trackAction(currentPopup.id, 'viewed');

        // Oznacz w sessionStorage (dla every_login)
        if (currentPopup.display_mode === 'every_login') {
            sessionStorage.setItem(`popup_seen_${currentPopup.id}`, '1');
        }
    }

    function renderPopup(popup) {
        // Overlay
        const overlay = document.createElement('div');
        overlay.className = 'popup-announcement-overlay';
        overlay.id = 'popupAnnouncementOverlay';

        // Modal
        const sizeClass = `popup-${popup.modal_size || 'md'}`;
        const modal = document.createElement('div');
        modal.className = `popup-announcement-modal ${sizeClass}`;

        // Kolor tła całego popupa
        const bgColor = popup.bg_color || '#5A189A';
        const textColor = getContrastText(bgColor);
        modal.style.background = bgColor;
        modal.style.color = textColor;

        // Przycisk zamknięcia (zawsze widoczny)
        const closeBtn = document.createElement('button');
        closeBtn.className = 'popup-announcement-close popup-announcement-close-float';
        closeBtn.innerHTML = '&times;';
        closeBtn.style.color = textColor;
        closeBtn.addEventListener('click', function() {
            dismissPopup();
        });
        modal.appendChild(closeBtn);

        // Nagłówek (opcjonalny - tylko gdy jest tytuł)
        if (popup.title) {
            const header = document.createElement('div');
            header.className = 'popup-announcement-header';
            header.style.background = darkenColor(bgColor, 20);

            const title = document.createElement('h3');
            title.textContent = popup.title;

            header.appendChild(title);
            modal.appendChild(header);
        }

        // Treść
        const body = document.createElement('div');
        body.className = 'popup-announcement-body';
        body.style.color = textColor;
        body.innerHTML = popup.content;

        modal.appendChild(body);

        // CTA (opcjonalny)
        if (popup.cta_text) {
            const footer = document.createElement('div');
            footer.className = 'popup-announcement-footer';

            const ctaBtn = document.createElement('a');
            ctaBtn.className = 'popup-announcement-cta';
            ctaBtn.textContent = popup.cta_text;
            ctaBtn.href = popup.cta_url || '#';
            if (popup.cta_color) {
                ctaBtn.style.background = popup.cta_color;
            }
            ctaBtn.addEventListener('click', function(e) {
                trackAction(currentPopup.id, 'cta_clicked', getDisplayDuration());
                closePopupOverlay(function() {
                    if (popup.cta_url) {
                        window.location.href = popup.cta_url;
                    }
                });
                if (popup.cta_url) {
                    e.preventDefault();
                }
            });

            footer.appendChild(ctaBtn);
            modal.appendChild(footer);
        }

        overlay.appendChild(modal);

        // Zamknięcie kliknięciem w overlay
        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) {
                dismissPopup();
            }
        });

        // Zamknięcie Escape
        document.addEventListener('keydown', handleEscape);

        document.body.appendChild(overlay);
    }

    function handleEscape(e) {
        if (e.key === 'Escape') {
            dismissPopup();
        }
    }

    // ==========================================
    // Zamykanie
    // ==========================================

    function getDisplayDuration() {
        return popupShownAt ? Date.now() - popupShownAt : null;
    }

    function dismissPopup() {
        if (currentPopup) {
            trackAction(currentPopup.id, 'dismissed', getDisplayDuration());
        }
        closePopupOverlay(function() {
            // Pokaż następny popup jeśli jest w kolejce
            if (popupsQueue.length > 0) {
                setTimeout(showNextPopup, 300);
            }
        });
    }

    function closePopupOverlay(callback) {
        const overlay = document.getElementById('popupAnnouncementOverlay');
        if (!overlay) {
            if (callback) callback();
            return;
        }

        document.removeEventListener('keydown', handleEscape);

        overlay.classList.add('closing');
        setTimeout(function() {
            overlay.remove();
            if (callback) callback();
        }, 350);
    }

    // ==========================================
    // Tracking akcji
    // ==========================================

    function trackAction(popupId, action, durationMs) {
        var payload = { action: action };
        if (durationMs != null) {
            payload.duration_ms = Math.round(durationMs);
        }
        fetch(`/api/popups/${popupId}/action`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify(payload)
        }).catch(() => {
            // Cichy błąd
        });
    }

    // ==========================================
    // Start po załadowaniu DOM
    // ==========================================

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
