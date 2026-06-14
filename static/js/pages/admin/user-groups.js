/**
 * user-groups.js
 * Obsługa zakładek Użytkownicy/Grupy oraz CRUD grup użytkowników.
 *
 * CSRF: używa istniejącego meta[name="csrf-token"] — ten sam mechanizm co
 * reszta panelu admina (np. clients/list.html, stock-orders.js).
 */

(function () {
    'use strict';

    // ========================================
    // CSRF Token
    // ========================================

    function getCsrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.content || '';
    }

    // ========================================
    // Przełączanie zakładek (wzorzec ze statistics.js)
    // ========================================

    function initTabs() {
        var tabs = document.querySelectorAll('.users-tab');
        var panels = document.querySelectorAll('.users-tab-panel');

        tabs.forEach(function (tab) {
            tab.addEventListener('click', function () {
                var targetTab = this.getAttribute('data-tab');

                tabs.forEach(function (t) { t.classList.remove('active'); });
                panels.forEach(function (p) { p.classList.remove('active'); });

                this.classList.add('active');
                var panel = document.getElementById('tab-' + targetTab);
                if (panel) {
                    panel.classList.add('active');
                }

                var url = new URL(window.location);
                url.searchParams.set('tab', targetTab);
                window.history.replaceState({}, '', url);
            });
        });

        // Odczyt parametru ?tab= z URL na start
        var params = new URLSearchParams(window.location.search);
        var initialTab = params.get('tab') || 'users';
        var targetBtn = document.querySelector('.users-tab[data-tab="' + initialTab + '"]');
        if (targetBtn) {
            targetBtn.click();
        }
    }

    // ========================================
    // Modal grupy
    // ========================================

    var currentGroupId = null;
    var selectedMembers = []; // [{id, name}]

    function openGroupModal(groupId, groupName) {
        currentGroupId = groupId || null;
        selectedMembers = [];

        var nameInput = document.getElementById('groupName');
        if (nameInput) nameInput.value = groupName || '';

        var searchInput = document.getElementById('groupMemberSearch');
        if (searchInput) searchInput.value = '';

        renderChips();

        var modal = document.getElementById('groupModal');
        if (!modal) return;

        var title = modal.querySelector('.modal-title');
        if (title) title.textContent = groupId ? 'Edytuj grupę' : 'Nowa grupa';

        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    function closeGroupModal() {
        var modal = document.getElementById('groupModal');
        if (!modal) return;
        modal.classList.add('closing');
        setTimeout(function () {
            modal.classList.remove('active', 'closing');
            document.body.style.overflow = '';
            currentGroupId = null;
            selectedMembers = [];
        }, 350);
        closeSearchDropdown();
    }

    // ========================================
    // Chipy członków
    // ========================================

    function renderChips() {
        var container = document.getElementById('groupMemberChips');
        if (!container) return;
        container.innerHTML = '';
        selectedMembers.forEach(function (m) {
            var chip = document.createElement('span');
            chip.className = 'member-chip';
            chip.innerHTML =
                '<span class="chip-label">' + escapeHtml(m.name) + '</span>' +
                '<button type="button" class="chip-remove" data-id="' + m.id + '">&times;</button>';
            container.appendChild(chip);
        });

        container.querySelectorAll('.chip-remove').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var id = parseInt(this.getAttribute('data-id'), 10);
                selectedMembers = selectedMembers.filter(function (m) { return m.id !== id; });
                renderChips();
            });
        });
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(String(str)));
        return div.innerHTML;
    }

    // ========================================
    // Wyszukiwanie członków
    // ========================================

    var searchDebounceTimer = null;
    var searchDropdown = null;

    function initMemberSearch() {
        var input = document.getElementById('groupMemberSearch');
        if (!input) return;

        input.addEventListener('input', function () {
            clearTimeout(searchDebounceTimer);
            var q = this.value.trim();
            if (q.length < 2) {
                closeSearchDropdown();
                return;
            }
            var capturedInput = this;
            searchDebounceTimer = setTimeout(function () {
                doSearch(q, capturedInput);
            }, 300);
        });

        input.addEventListener('blur', function () {
            setTimeout(closeSearchDropdown, 200);
        });
    }

    function doSearch(q, inputEl) {
        fetch('/admin/users/api/search?q=' + encodeURIComponent(q), {
            headers: { 'X-CSRFToken': getCsrfToken() }
        })
            .then(function (r) { return r.json(); })
            .then(function (users) {
                // API zwraca płaską tablicę [{id, name, email, avatar}]
                showSearchDropdown(Array.isArray(users) ? users : [], inputEl);
            })
            .catch(function (err) {
                console.error('Błąd wyszukiwania użytkowników:', err);
            });
    }

    function showSearchDropdown(users, inputEl) {
        closeSearchDropdown();

        // Odfiltruj już wybranych
        var candidates = users.filter(function (u) {
            return !selectedMembers.some(function (m) { return m.id === u.id; });
        });
        if (!candidates.length) return;

        var rect = inputEl.getBoundingClientRect();
        var dropdown = document.createElement('div');
        dropdown.className = 'member-search-results';
        dropdown.style.position = 'fixed';
        dropdown.style.top = rect.bottom + 'px';
        dropdown.style.left = rect.left + 'px';
        dropdown.style.width = rect.width + 'px';
        dropdown.style.zIndex = '20000';

        candidates.forEach(function (u) {
            var item = document.createElement('div');
            item.className = 'member-result';
            item.innerHTML =
                '<span class="result-name">' + escapeHtml(u.name || u.email) + '</span>' +
                '<span class="result-email">' + escapeHtml(u.email) + '</span>';
            item.addEventListener('mousedown', function (e) {
                // mousedown przed blur, żeby nie zgubić kliknięcia
                e.preventDefault();
                selectedMembers.push({ id: u.id, name: u.name || u.email });
                renderChips();
                var searchInput = document.getElementById('groupMemberSearch');
                if (searchInput) searchInput.value = '';
                closeSearchDropdown();
            });
            dropdown.appendChild(item);
        });

        document.body.appendChild(dropdown);
        searchDropdown = dropdown;
    }

    function closeSearchDropdown() {
        if (searchDropdown) {
            searchDropdown.remove();
            searchDropdown = null;
        }
    }

    // ========================================
    // Zapis grupy (create lub update)
    // ========================================

    function saveGroup() {
        var name = (document.getElementById('groupName')?.value || '').trim();
        if (!name) {
            alert('Nazwa grupy jest wymagana.');
            return;
        }

        var url = currentGroupId
            ? '/admin/user-groups/' + currentGroupId + '/update'
            : '/admin/user-groups/create';

        var body = {
            name: name,
            member_ids: selectedMembers.map(function (m) { return m.id; })
        };

        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify(body)
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    if (window.Toast) {
                        window.Toast.show(
                            currentGroupId ? 'Grupa zaktualizowana.' : 'Grupa utworzona.',
                            'success'
                        );
                    }
                    window.location.href = window.location.pathname + '?tab=groups';
                } else {
                    var msg = data.error || 'Wystąpił błąd.';
                    if (window.Toast) window.Toast.show(msg, 'error');
                    else alert(msg);
                }
            })
            .catch(function (err) {
                console.error('Błąd zapisu grupy:', err);
                alert('Błąd połączenia z serwerem.');
            });
    }

    // ========================================
    // Usunięcie grupy
    // ========================================

    function deleteGroup(groupId, groupName) {
        if (!confirm('Czy na pewno chcesz usunąć grupę "' + groupName + '"?')) return;

        fetch('/admin/user-groups/' + groupId + '/delete', {
            method: 'POST',
            headers: { 'X-CSRFToken': getCsrfToken() }
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    if (window.Toast) window.Toast.show('Grupa usunięta.', 'success');
                    window.location.href = window.location.pathname + '?tab=groups';
                } else {
                    var msg = data.error || 'Błąd usuwania grupy.';
                    if (window.Toast) window.Toast.show(msg, 'error');
                    else alert(msg);
                }
            })
            .catch(function (err) {
                console.error('Błąd usuwania grupy:', err);
                alert('Błąd połączenia z serwerem.');
            });
    }

    // ========================================
    // Globalne API (wywoływane z atrybutów onclick)
    // ========================================

    window.openGroupModal = function (groupId, groupName) {
        openGroupModal(groupId, groupName);
    };
    window.editGroup = function (id, name) {
        openGroupModal(id, name);
    };
    window.deleteGroup = deleteGroup;
    window.saveGroup = saveGroup;
    window.closeGroupModal = closeGroupModal;

    // ========================================
    // Inicjalizacja
    // ========================================

    document.addEventListener('DOMContentLoaded', function () {
        initTabs();
        initMemberSearch();

        // Zamknij modal klikając w overlay
        var groupModal = document.getElementById('groupModal');
        if (groupModal) {
            groupModal.addEventListener('click', function (e) {
                if (e.target === this) closeGroupModal();
            });
        }

        // Zamknij modal klawiszem Escape
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeGroupModal();
        });
    });

})();
