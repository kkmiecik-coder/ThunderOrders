/**
 * Searchable Select - progressive enhancement dla natywnych <select class="searchable-select">.
 * Natywny <select> pozostaje źródłem prawdy; po kliknięciu .custom-select-display
 * pokazuje się panel z inputem wyszukiwarki i listą opcji budowaną na żywo z selecta.
 * Wybór ustawia select.value, dispatchuje natywny 'change' i aktualizuje tekst triggera.
 * Cała logika na delegacji zdarzeń -> działa dla dynamicznie dodawanych sekcji.
 */
(function () {
    'use strict';

    let openWrapper = null;

    function getSelect(wrapper) {
        return wrapper.querySelector('select.searchable-select');
    }

    function syncDisplay(select) {
        const wrapper = select.closest('.custom-select-wrapper');
        if (!wrapper) return;
        const text = wrapper.querySelector('.custom-select-display .selected-text');
        if (!text) return;
        const opt = select.options[select.selectedIndex];
        if (opt && opt.value) {
            text.textContent = opt.text;
        } else if (select.options[0]) {
            text.textContent = select.options[0].text;
        }
    }

    function closePanel() {
        if (!openWrapper) return;
        const panel = openWrapper.querySelector('.searchable-select-panel');
        if (panel) panel.remove();
        openWrapper.classList.remove('is-open');
        openWrapper = null;
    }

    function openPanel(wrapper) {
        closePanel();
        const select = getSelect(wrapper);
        if (!select) return;

        const panel = document.createElement('div');
        panel.className = 'searchable-select-panel';

        const searchWrap = document.createElement('div');
        searchWrap.className = 'searchable-select-search';
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'searchable-select-input';
        input.placeholder = 'Szukaj...';
        searchWrap.appendChild(input);

        const list = document.createElement('ul');
        list.className = 'searchable-select-options';

        // Buduj opcje na zywo z natywnego selecta (pomijaj placeholder z pustym value)
        Array.from(select.options).forEach(function (opt) {
            if (!opt.value) return;
            const li = document.createElement('li');
            li.className = 'searchable-select-option';
            li.dataset.value = opt.value;
            li.textContent = opt.text;
            if (opt.value === select.value) li.classList.add('is-selected');
            list.appendChild(li);
        });

        const empty = document.createElement('li');
        empty.className = 'searchable-select-empty';
        empty.textContent = 'Brak wyników';
        empty.style.display = 'none';
        list.appendChild(empty);

        panel.appendChild(searchWrap);
        panel.appendChild(list);
        wrapper.appendChild(panel);
        wrapper.classList.add('is-open');
        openWrapper = wrapper;
        input.focus();

        let highlighted = -1;

        function visibleOptions() {
            return Array.from(list.querySelectorAll('.searchable-select-option'))
                .filter(function (li) { return li.style.display !== 'none'; });
        }

        function filter() {
            const q = input.value.trim().toLowerCase();
            let any = false;
            list.querySelectorAll('.searchable-select-option').forEach(function (li) {
                const match = li.textContent.toLowerCase().indexOf(q) !== -1;
                li.style.display = match ? '' : 'none';
                li.classList.remove('is-highlighted');
                if (match) any = true;
            });
            highlighted = -1;
            empty.style.display = any ? 'none' : '';
        }

        function choose(li) {
            select.value = li.dataset.value;
            select.dispatchEvent(new Event('change', { bubbles: true }));
            syncDisplay(select);
            closePanel();
        }

        function setHighlight(idx) {
            const opts = visibleOptions();
            opts.forEach(function (o) { o.classList.remove('is-highlighted'); });
            if (idx < 0 || idx >= opts.length) { highlighted = -1; return; }
            opts[idx].classList.add('is-highlighted');
            opts[idx].scrollIntoView({ block: 'nearest' });
            highlighted = idx;
        }

        input.addEventListener('input', filter);
        input.addEventListener('keydown', function (e) {
            const opts = visibleOptions();
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                setHighlight(Math.min(highlighted + 1, opts.length - 1));
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setHighlight(Math.max(highlighted - 1, 0));
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (highlighted >= 0 && opts[highlighted]) choose(opts[highlighted]);
            } else if (e.key === 'Escape') {
                e.preventDefault();
                closePanel();
            }
        });
        list.addEventListener('click', function (e) {
            const li = e.target.closest('.searchable-select-option');
            if (li) choose(li);
        });
    }

    // Delegacja: klik na .custom-select-display, ktorego wrapper ma searchable-select
    document.addEventListener('click', function (e) {
        const display = e.target.closest('.custom-select-display');
        if (display) {
            const wrapper = display.closest('.custom-select-wrapper');
            if (wrapper && getSelect(wrapper)) {
                e.preventDefault();
                if (openWrapper === wrapper) {
                    closePanel();
                } else {
                    openPanel(wrapper);
                }
                return;
            }
        }
        // Klik poza panelem i poza triggerem -> zamknij
        if (openWrapper &&
            !e.target.closest('.searchable-select-panel') &&
            !e.target.closest('.custom-select-display')) {
            closePanel();
        }
    });

    // Sync tekstu triggera gdy value zmieni sie (nasz dispatch lub programowo)
    document.addEventListener('change', function (e) {
        if (e.target.matches && e.target.matches('select.searchable-select')) {
            syncDisplay(e.target);
        }
    });

    // Poczatkowy sync dla server-renderowanych selectow
    function initialSync() {
        document.querySelectorAll('select.searchable-select').forEach(syncDisplay);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialSync);
    } else {
        initialSync();
    }
})();
