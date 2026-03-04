/**
 * Admin Broadcasts – list & form logic
 */
(function () {
    'use strict';

    /* ───── Helpers ───── */

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) return meta.getAttribute('content');
        const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrf_token='));
        return cookie ? decodeURIComponent(cookie.split('=')[1]) : '';
    }

    function toast(msg, type) {
        if (window.Toast) window.Toast.show(msg, type);
    }

    /* ═══════════════════════════════════════
       LIST PAGE – delete broadcast
       ═══════════════════════════════════════ */

    const deleteModal = document.getElementById('deleteBroadcastModal');
    const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');
    let pendingDeleteId = null;

    function openDeleteModal(id) {
        pendingDeleteId = id;
        if (deleteModal) deleteModal.classList.add('active');
    }

    function closeDeleteModal() {
        pendingDeleteId = null;
        if (deleteModal) {
            deleteModal.classList.add('closing');
            setTimeout(() => {
                deleteModal.classList.remove('active', 'closing');
            }, 200);
        }
    }
    window.closeDeleteModal = closeDeleteModal;

    // Attach delete buttons
    document.querySelectorAll('.btn-delete-broadcast').forEach(btn => {
        btn.addEventListener('click', () => openDeleteModal(btn.dataset.broadcastId));
    });

    if (confirmDeleteBtn) {
        confirmDeleteBtn.addEventListener('click', async () => {
            if (!pendingDeleteId) return;
            confirmDeleteBtn.disabled = true;
            try {
                const res = await fetch(`/admin/broadcasts/${pendingDeleteId}/delete`, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': getCsrfToken() }
                });
                const data = await res.json();
                if (data.success) {
                    const row = document.querySelector(`tr[data-broadcast-id="${pendingDeleteId}"]`);
                    if (row) row.remove();
                    toast('Broadcast usunięty.', 'success');

                    // If table is now empty, reload for empty state
                    if (!document.querySelector('.broadcasts-table tbody tr')) {
                        location.reload();
                    }
                } else {
                    toast(data.message || 'Błąd usuwania.', 'error');
                }
            } catch {
                toast('Błąd połączenia.', 'error');
            } finally {
                confirmDeleteBtn.disabled = false;
                closeDeleteModal();
            }
        });
    }

    // Close modal on overlay click
    if (deleteModal) {
        deleteModal.addEventListener('click', e => {
            if (e.target === deleteModal) closeDeleteModal();
        });
    }

    /* ═══════════════════════════════════════
       FORM PAGE – compose & send
       ═══════════════════════════════════════ */

    const form = document.getElementById('broadcastForm');
    if (!form) return; // Not on form page

    const sendBtn = document.getElementById('sendBtn');
    const rolesSelector = document.getElementById('rolesSelector');
    const usersSelector = document.getElementById('usersSelector');
    const userSearchInput = document.getElementById('userSearchInput');
    const userSearchResults = document.getElementById('userSearchResults');
    const selectedUsersTags = document.getElementById('selectedUsersTags');

    let selectedUsers = []; // [{id, name, email}]
    let searchTimeout = null;

    /* Target type toggle */
    document.querySelectorAll('input[name="target_type"]').forEach(radio => {
        radio.addEventListener('change', () => {
            const val = radio.value;
            rolesSelector.style.display = val === 'roles' ? 'block' : 'none';
            usersSelector.style.display = val === 'users' ? 'block' : 'none';
        });
    });

    /* User search */
    if (userSearchInput) {
        userSearchInput.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            const q = userSearchInput.value.trim();
            if (q.length < 2) {
                userSearchResults.innerHTML = '';
                userSearchResults.style.display = 'none';
                return;
            }
            searchTimeout = setTimeout(() => searchUsers(q), 300);
        });

        // Close dropdown on outside click
        document.addEventListener('click', e => {
            if (!e.target.closest('.user-search-container')) {
                userSearchResults.style.display = 'none';
            }
        });
    }

    async function searchUsers(q) {
        try {
            const res = await fetch(`/admin/broadcasts/search-users?q=${encodeURIComponent(q)}`);
            const data = await res.json();
            renderSearchResults(data.users || []);
        } catch {
            userSearchResults.innerHTML = '<div class="search-no-results">Błąd wyszukiwania</div>';
            userSearchResults.style.display = 'block';
        }
    }

    function renderSearchResults(users) {
        // Filter out already selected
        const selectedIds = new Set(selectedUsers.map(u => u.id));
        const filtered = users.filter(u => !selectedIds.has(u.id));

        if (filtered.length === 0) {
            userSearchResults.innerHTML = '<div class="search-no-results">Brak wyników</div>';
            userSearchResults.style.display = 'block';
            return;
        }

        const roleLabels = { admin: 'Admin', mod: 'Moderator', client: 'Klient' };

        userSearchResults.innerHTML = filtered.map(u => `
            <div class="search-result-item" data-user='${JSON.stringify(u).replace(/'/g, '&#39;')}'>
                <span class="search-result-name">${escapeHtml(u.name)}</span>
                <span class="search-result-meta">${escapeHtml(u.email)} &middot; ${roleLabels[u.role] || u.role}</span>
            </div>
        `).join('');
        userSearchResults.style.display = 'block';

        // Attach click handlers
        userSearchResults.querySelectorAll('.search-result-item').forEach(item => {
            item.addEventListener('click', () => {
                const user = JSON.parse(item.dataset.user);
                addUser(user);
                userSearchInput.value = '';
                userSearchResults.style.display = 'none';
            });
        });
    }

    function addUser(user) {
        if (selectedUsers.find(u => u.id === user.id)) return;
        selectedUsers.push(user);
        renderSelectedUsers();
    }

    function removeUser(userId) {
        selectedUsers = selectedUsers.filter(u => u.id !== userId);
        renderSelectedUsers();
    }

    function renderSelectedUsers() {
        if (!selectedUsersTags) return;
        selectedUsersTags.innerHTML = selectedUsers.map(u => `
            <span class="user-tag">
                ${escapeHtml(u.name)}
                <button type="button" class="user-tag-remove" data-user-id="${u.id}">&times;</button>
            </span>
        `).join('');

        selectedUsersTags.querySelectorAll('.user-tag-remove').forEach(btn => {
            btn.addEventListener('click', () => removeUser(parseInt(btn.dataset.userId)));
        });
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    /* Form submit */
    form.addEventListener('submit', async e => {
        e.preventDefault();

        const title = document.getElementById('broadcastTitle').value.trim();
        const body = document.getElementById('broadcastBody').value.trim();
        const url = document.getElementById('broadcastUrl').value.trim();
        const targetType = document.querySelector('input[name="target_type"]:checked').value;

        if (!title) {
            toast('Tytuł jest wymagany.', 'error');
            document.getElementById('broadcastTitle').focus();
            return;
        }

        let targetData = null;
        if (targetType === 'roles') {
            const checked = Array.from(document.querySelectorAll('input[name="roles"]:checked'));
            targetData = checked.map(cb => cb.value);
            if (targetData.length === 0) {
                toast('Wybierz co najmniej jedną rolę.', 'error');
                return;
            }
        } else if (targetType === 'users') {
            targetData = selectedUsers.map(u => u.id);
            if (targetData.length === 0) {
                toast('Wybierz co najmniej jednego użytkownika.', 'error');
                return;
            }
        }

        sendBtn.disabled = true;
        sendBtn.textContent = 'Wysyłanie...';

        try {
            const res = await fetch('/admin/broadcasts/send', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({ title, body, url, target_type: targetType, target_data: targetData })
            });
            const data = await res.json();

            if (data.success) {
                toast(data.message || 'Wysłano!', 'success');
                setTimeout(() => {
                    window.location.href = '/admin/broadcasts';
                }, 800);
            } else {
                toast(data.message || 'Błąd wysyłki.', 'error');
                sendBtn.disabled = false;
                sendBtn.textContent = 'Wyślij powiadomienie';
            }
        } catch {
            toast('Błąd połączenia z serwerem.', 'error');
            sendBtn.disabled = false;
            sendBtn.textContent = 'Wyślij powiadomienie';
        }
    });

})();
