/**
 * BULK TOOLBAR — wspólna logika pływającego paska akcji.
 *
 * JEDNO ŹRÓDŁO PRAWDY dla pokazywania/ukrywania paska i licznika
 * zaznaczonych. Wcześniej ten sam kawałek kodu był przepisany w pięciu
 * plikach JS; jeśli dodajesz pasek na nowej stronie, użyj tego modułu
 * zamiast kopiować `classList.add('hidden')` po raz kolejny.
 *
 * Użycie:
 *     var pasek = BulkToolbar.init('productsBulkToolbar');
 *     pasek.update(liczbaZaznaczonych);          // pokazuje albo ukrywa
 *     pasek.update(3, '150.00 zł');              // z drugą linią (suma)
 *     pasek.hide();                              // wymuszone ukrycie
 *     pasek.onAction(function (akcja, przycisk) { ... });  // data-action
 *
 * init() zwraca null, jeśli paska nie ma w DOM — strony renderują go
 * warunkowo (rola, aktywna zakładka), więc to normalny przypadek, nie błąd.
 */
(function (global) {
    'use strict';

    // Odmiana rzeczownika przez liczbę: 1 zaznaczone, 2-4 zaznaczone, 5+ zaznaczonych.
    function tekstLicznika(n) {
        if (n === 1) return '1 zaznaczone';
        var reszta10 = n % 10;
        var reszta100 = n % 100;
        if (reszta10 >= 2 && reszta10 <= 4 && !(reszta100 >= 12 && reszta100 <= 14)) {
            return n + ' zaznaczone';
        }
        return n + ' zaznaczonych';
    }

    function BulkToolbarInstance(el) {
        this.el = el;
        this.countEl = el.querySelector('[data-bulk-count]') || el.querySelector('.selected-count');
        this.totalEl = el.querySelector('[data-bulk-total]') || el.querySelector('.selected-total');
    }

    /**
     * Pokazuje pasek z licznikiem albo go ukrywa, gdy nic nie zaznaczono.
     * @param {number} count liczba zaznaczonych elementów
     * @param {string} [totalText] opcjonalna druga linia (np. "150.00 zł")
     */
    BulkToolbarInstance.prototype.update = function (count, totalText) {
        if (count > 0) {
            if (this.countEl) this.countEl.textContent = tekstLicznika(count);
            if (this.totalEl) this.totalEl.textContent = totalText || '';
            this.show();
        } else {
            this.hide();
        }
    };

    BulkToolbarInstance.prototype.show = function () {
        this.el.classList.remove('hidden');
    };

    BulkToolbarInstance.prototype.hide = function () {
        this.el.classList.add('hidden');
        this.closeMenu();
    };

    BulkToolbarInstance.prototype.isVisible = function () {
        return !this.el.classList.contains('hidden');
    };

    /**
     * Podpina obsługę kliknięć w przyciski z atrybutem data-action.
     * Działa przez delegację, więc obejmuje też przyciski w rozwijanym menu
     * i te dorenderowane po inicjalizacji.
     * @param {function(string, HTMLElement, Event)} handler
     */
    BulkToolbarInstance.prototype.onAction = function (handler) {
        var self = this;
        this.el.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-action]');
            if (!btn || !self.el.contains(btn)) return;
            if (btn.disabled || btn.classList.contains('is-disabled')) return;
            handler(btn.dataset.action, btn, e);
        });
    };

    /* --- Rozwijane menu akcji (opcjonalne) --- */

    BulkToolbarInstance.prototype.initMenu = function (menuId, toggleId, listId) {
        var self = this;
        this.menu = document.getElementById(menuId);
        this.menuToggle = document.getElementById(toggleId);
        this.menuList = document.getElementById(listId);
        if (!this.menu || !this.menuToggle || !this.menuList) return this;

        this.menuToggle.addEventListener('click', function (e) {
            e.stopPropagation();
            self.toggleMenu();
        });

        document.addEventListener('click', function (e) {
            if (!self.menu.contains(e.target)) self.closeMenu();
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') self.closeMenu();
        });

        return this;
    };

    BulkToolbarInstance.prototype.toggleMenu = function () {
        if (!this.menuList) return;
        if (this.menuList.hidden) {
            this.menuList.hidden = false;
            this.menu.classList.add('open');
            this.menuToggle.setAttribute('aria-expanded', 'true');
        } else {
            this.closeMenu();
        }
    };

    BulkToolbarInstance.prototype.closeMenu = function () {
        if (!this.menuList) return;
        this.menuList.hidden = true;
        this.menu.classList.remove('open');
        this.menuToggle.setAttribute('aria-expanded', 'false');
    };

    global.BulkToolbar = {
        /**
         * @param {string} id id kontenera paska
         * @returns {BulkToolbarInstance|null} null, gdy paska nie ma na stronie
         */
        init: function (id) {
            var el = document.getElementById(id);
            if (!el) return null;
            return new BulkToolbarInstance(el);
        },
        tekstLicznika: tekstLicznika
    };
})(window);
