/**
 * Client Order Detail
 */
document.addEventListener('DOMContentLoaded', function () {

    /* ---- Keyboard: Alt+Left = back ---- */
    document.addEventListener('keydown', function (e) {
        if (e.altKey && e.key === 'ArrowLeft') {
            var back = document.querySelector('.od-back');
            if (back) window.location.href = back.href;
        }
    });

    /* ---- Collapsible sections (event delegation) ---- */
    document.addEventListener('click', function (e) {
        var trigger = e.target.closest('[data-action="toggle-section"]');
        if (!trigger) return;
        var section = trigger.closest('.od-collapse');
        if (section) section.classList.toggle('open');
    });

    /* ---- Custom Name popover ---- */
    var container = document.getElementById('custom-name-container');
    if (!container) return;

    var orderId = container.dataset.orderId;
    var popover = null;

    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) return meta.content;
        var match = document.cookie.match(/csrf_token=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function closePopover() {
        if (popover) {
            popover.remove();
            popover = null;
        }
    }

    function showPopover(currentName) {
        closePopover();
        popover = document.createElement('div');
        popover.className = 'od-custom-name-popover';
        popover.innerHTML =
            '<input type="text" class="od-custom-name-popover__input" maxlength="50" placeholder="Nazwa własna..." value="' + (currentName || '').replace(/"/g, '&quot;') + '">' +
            '<div class="od-custom-name-popover__actions">' +
                '<button type="button" class="od-custom-name-popover__btn od-custom-name-popover__btn--save">Zapisz</button>' +
                '<button type="button" class="od-custom-name-popover__btn od-custom-name-popover__btn--cancel">Anuluj</button>' +
            '</div>';

        container.appendChild(popover);
        var input = popover.querySelector('input');
        input.focus();
        input.select();

        popover.querySelector('.od-custom-name-popover__btn--cancel').addEventListener('click', closePopover);
        popover.querySelector('.od-custom-name-popover__btn--save').addEventListener('click', function () {
            saveName(input.value.trim());
        });
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') saveName(input.value.trim());
            if (e.key === 'Escape') closePopover();
        });
    }

    function saveName(name) {
        fetch('/client/orders/' + orderId + '/custom-name', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ custom_name: name })
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.success) {
                if (window.Toast) window.Toast.show(data.error || 'Błąd', 'error');
                return;
            }
            closePopover();
            renderName(data.custom_name);
            if (window.Toast) window.Toast.show('Nazwa zapisana', 'success');
        })
        .catch(function () {
            if (window.Toast) window.Toast.show('Błąd połączenia', 'error');
        });
    }

    function renderName(name) {
        var heroEl = document.getElementById('hero-custom-name');

        if (name) {
            container.innerHTML =
                '<span class="od-custom-name__text" id="custom-name-text">' + escapeHtml(name) + '</span>' +
                '<button type="button" class="od-custom-name__edit" id="custom-name-edit-btn" title="Edytuj nazwę">' +
                    '<svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>' +
                '</button>';

            if (heroEl) {
                heroEl.textContent = name;
            } else {
                var heroNumber = document.querySelector('.od-hero__number');
                if (heroNumber) {
                    var span = document.createElement('span');
                    span.className = 'od-hero__custom-name';
                    span.id = 'hero-custom-name';
                    span.textContent = name;
                    heroNumber.insertAdjacentElement('afterend', span);
                }
            }
        } else {
            container.innerHTML =
                '<button type="button" class="od-custom-name__add" id="custom-name-add-btn">Dodaj</button>';
            if (heroEl) heroEl.remove();
        }
        bindButtons();
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function bindButtons() {
        var addBtn = document.getElementById('custom-name-add-btn');
        var editBtn = document.getElementById('custom-name-edit-btn');
        if (addBtn) addBtn.addEventListener('click', function () { showPopover(''); });
        if (editBtn) {
            editBtn.addEventListener('click', function () {
                var textEl = document.getElementById('custom-name-text');
                showPopover(textEl ? textEl.textContent : '');
            });
        }
    }

    bindButtons();

    document.addEventListener('click', function (e) {
        if (popover && !popover.contains(e.target) && !e.target.closest('.od-custom-name__edit, .od-custom-name__add')) {
            closePopover();
        }
    });
});
