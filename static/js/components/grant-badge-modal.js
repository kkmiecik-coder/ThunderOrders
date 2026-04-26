/**
 * Grant Badge Modal — admin/clients/detail.html
 *
 * Obsługuje:
 * - Otwieranie/zamykanie modala "Przyznaj specjalną odznakę"
 * - Escape keybinding
 * - Focus trap (focus zostaje wewnątrz modala podczas Tab/Shift+Tab)
 * - Zwracanie focusu do triggera po zamknięciu
 */
(function() {
    'use strict';

    const MODAL_ID = 'grant-badge-modal';
    const ACTIVE_CLASS = 'active';

    let lastFocusedElement = null;

    function getModal() {
        return document.getElementById(MODAL_ID);
    }

    function getFocusableElements(modal) {
        return modal.querySelectorAll(
            'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
    }

    function openModal() {
        const modal = getModal();
        if (!modal) return;

        lastFocusedElement = document.activeElement;
        modal.classList.add(ACTIVE_CLASS);
        modal.setAttribute('aria-hidden', 'false');

        // Focus pierwszego elementu (zazwyczaj select)
        const focusable = getFocusableElements(modal);
        if (focusable.length > 0) {
            // Czekaj na transition (jeśli jest)
            setTimeout(() => focusable[0].focus(), 50);
        }
    }

    function closeModal() {
        const modal = getModal();
        if (!modal) return;

        modal.classList.remove(ACTIVE_CLASS);
        modal.setAttribute('aria-hidden', 'true');

        if (lastFocusedElement && typeof lastFocusedElement.focus === 'function') {
            lastFocusedElement.focus();
        }
    }

    function handleKeydown(e) {
        const modal = getModal();
        if (!modal || !modal.classList.contains(ACTIVE_CLASS)) return;

        if (e.key === 'Escape') {
            e.preventDefault();
            closeModal();
            return;
        }

        // Focus trap
        if (e.key === 'Tab') {
            const focusable = getFocusableElements(modal);
            if (focusable.length === 0) return;

            const first = focusable[0];
            const last = focusable[focusable.length - 1];

            if (e.shiftKey && document.activeElement === first) {
                e.preventDefault();
                last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first.focus();
            }
        }
    }

    function init() {
        const modal = getModal();
        if (!modal) return;

        // Initial state
        modal.setAttribute('aria-hidden', 'true');

        // Click overlay -> close (klik poza modal-content zamyka)
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeModal();
            }
        });

        // Listenery na elementy z data-attribute
        document.querySelectorAll('[data-grant-badge-open]').forEach(el => {
            el.addEventListener('click', function(e) {
                e.preventDefault();
                openModal();
            });
        });

        document.querySelectorAll('[data-grant-badge-close]').forEach(el => {
            el.addEventListener('click', function(e) {
                e.preventDefault();
                closeModal();
            });
        });

        // Global keydown listener (Escape, focus trap)
        document.addEventListener('keydown', handleKeydown);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
