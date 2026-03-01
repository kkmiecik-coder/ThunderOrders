/**
 * WMS Dashboard JavaScript
 * Packaging materials CRUD, drag & drop reorder
 */

(function() {
    'use strict';

    // ====================
    // HELPERS
    // ====================

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) return meta.getAttribute('content');
        // Cookie fallback
        const cookies = document.cookie.split(';');
        for (let c of cookies) {
            c = c.trim();
            if (c.startsWith('csrf_token=')) return c.substring('csrf_token='.length);
        }
        return '';
    }

    // ====================
    // MATERIAL MODAL
    // ====================

    function openMaterialModal(id) {
        const modal = document.getElementById('material-modal');
        const title = document.getElementById('material-modal-title');

        if (id) {
            title.textContent = 'Edytuj materiał';
            // Fetch material data
            fetch(`/api/orders/packaging-materials/${id}`, {
                headers: { 'X-CSRFToken': getCsrfToken() }
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    const m = data.material;
                    document.getElementById('material-id').value = m.id;
                    document.getElementById('material-name').value = m.name || '';
                    document.getElementById('material-type').value = m.type || 'karton';
                    document.getElementById('material-length').value = m.inner_length || '';
                    document.getElementById('material-width').value = m.inner_width || '';
                    document.getElementById('material-height').value = m.inner_height || '';
                    document.getElementById('material-max-weight').value = m.max_weight || '';
                    document.getElementById('material-own-weight').value = m.own_weight || '';
                    document.getElementById('material-stock').value = m.quantity_in_stock ?? 0;
                    document.getElementById('material-threshold').value = m.low_stock_threshold ?? 5;
                    document.getElementById('material-cost').value = m.cost || '';
                    document.getElementById('material-active').checked = m.is_active;
                }
            });
        } else {
            title.textContent = 'Dodaj materiał';
            document.getElementById('material-id').value = '';
            document.getElementById('material-name').value = '';
            document.getElementById('material-type').value = 'karton';
            document.getElementById('material-length').value = '';
            document.getElementById('material-width').value = '';
            document.getElementById('material-height').value = '';
            document.getElementById('material-max-weight').value = '';
            document.getElementById('material-own-weight').value = '';
            document.getElementById('material-stock').value = '0';
            document.getElementById('material-threshold').value = '5';
            document.getElementById('material-cost').value = '';
            document.getElementById('material-active').checked = true;
        }

        modal.classList.add('active');
    }

    function closeMaterialModal() {
        document.getElementById('material-modal').classList.remove('active');
    }

    function saveMaterial() {
        const id = document.getElementById('material-id').value;
        const name = document.getElementById('material-name').value.trim();

        if (!name) {
            if (window.Toast) window.Toast.show('Nazwa jest wymagana', 'error');
            return;
        }

        const data = {
            name: name,
            type: document.getElementById('material-type').value,
            inner_length: parseFloat(document.getElementById('material-length').value) || null,
            inner_width: parseFloat(document.getElementById('material-width').value) || null,
            inner_height: parseFloat(document.getElementById('material-height').value) || null,
            max_weight: parseFloat(document.getElementById('material-max-weight').value) || null,
            own_weight: parseFloat(document.getElementById('material-own-weight').value) || null,
            quantity_in_stock: parseInt(document.getElementById('material-stock').value) || 0,
            low_stock_threshold: parseInt(document.getElementById('material-threshold').value) || 5,
            cost: parseFloat(document.getElementById('material-cost').value) || null,
            is_active: document.getElementById('material-active').checked,
        };

        const url = id
            ? `/admin/orders/packaging-materials/${id}/update`
            : '/admin/orders/packaging-materials/create';

        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify(data),
        })
        .then(r => r.json())
        .then(result => {
            if (result.success) {
                if (window.Toast) window.Toast.show(result.message, 'success');
                closeMaterialModal();
                // Reload on materials tab
                window.location.href = window.location.pathname + '?tab=materials';
            } else {
                if (window.Toast) window.Toast.show(result.message || 'Błąd', 'error');
            }
        })
        .catch(() => {
            if (window.Toast) window.Toast.show('Błąd połączenia', 'error');
        });
    }

    function deleteMaterial(id) {
        if (!confirm('Czy na pewno chcesz usunąć ten materiał?')) return;

        fetch(`/admin/orders/packaging-materials/${id}`, {
            method: 'DELETE',
            headers: { 'X-CSRFToken': getCsrfToken() },
        })
        .then(r => r.json())
        .then(result => {
            if (result.success) {
                if (window.Toast) window.Toast.show(result.message, 'success');
                window.location.href = window.location.pathname + '?tab=materials';
            } else {
                if (window.Toast) window.Toast.show(result.message || 'Błąd', 'error');
            }
        })
        .catch(() => {
            if (window.Toast) window.Toast.show('Błąd połączenia', 'error');
        });
    }

    // ====================
    // DRAG & DROP REORDER
    // ====================

    function initDragDrop() {
        const list = document.querySelector('.materials-list');
        if (!list) return;

        let dragItem = null;

        list.addEventListener('dragstart', function(e) {
            const item = e.target.closest('.material-list-item');
            if (!item) return;
            dragItem = item;
            item.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
        });

        list.addEventListener('dragend', function(e) {
            const item = e.target.closest('.material-list-item');
            if (item) item.classList.remove('dragging');
            // Remove all drag-over states
            list.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));

            if (!dragItem) return;

            // Build new order
            const items = list.querySelectorAll('.material-list-item');
            const order = [];
            items.forEach((el, idx) => {
                order.push({
                    id: parseInt(el.dataset.materialId),
                    sort_order: idx,
                });
            });

            fetch('/admin/orders/packaging-materials/reorder', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({ order: order }),
            })
            .then(r => r.json())
            .then(result => {
                if (!result.success && window.Toast) {
                    window.Toast.show(result.message || 'Błąd zmiany kolejności', 'error');
                }
            });

            dragItem = null;
        });

        list.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';

            const target = e.target.closest('.material-list-item');
            if (!target || target === dragItem) return;

            // Remove all drag-over states first
            list.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
            target.classList.add('drag-over');
        });

        list.addEventListener('drop', function(e) {
            e.preventDefault();
            const target = e.target.closest('.material-list-item');
            if (!target || !dragItem || target === dragItem) return;

            // Insert before or after
            const rect = target.getBoundingClientRect();
            const midY = rect.top + rect.height / 2;
            if (e.clientY < midY) {
                list.insertBefore(dragItem, target);
            } else {
                list.insertBefore(dragItem, target.nextSibling);
            }

            target.classList.remove('drag-over');
        });
    }

    // ====================
    // EVENT LISTENERS
    // ====================

    document.addEventListener('DOMContentLoaded', function() {
        initDragDrop();

        // Add material button
        const addBtn = document.getElementById('add-material-btn');
        if (addBtn) {
            addBtn.addEventListener('click', function() {
                openMaterialModal(null);
            });
        }

        // Modal close / cancel / save
        const closeBtn = document.getElementById('material-modal-close');
        const cancelBtn = document.getElementById('material-modal-cancel');
        const saveBtn = document.getElementById('material-modal-save');

        if (closeBtn) closeBtn.addEventListener('click', closeMaterialModal);
        if (cancelBtn) cancelBtn.addEventListener('click', closeMaterialModal);
        if (saveBtn) saveBtn.addEventListener('click', saveMaterial);

        // Close modal on overlay click
        const modal = document.getElementById('material-modal');
        if (modal) {
            modal.addEventListener('click', function(e) {
                if (e.target === modal) closeMaterialModal();
            });
        }

        // Delegated clicks for edit/delete
        document.addEventListener('click', function(e) {
            const editBtn = e.target.closest('.material-edit');
            if (editBtn) {
                openMaterialModal(editBtn.dataset.materialId);
                return;
            }

            const deleteBtn = e.target.closest('.material-delete');
            if (deleteBtn) {
                deleteMaterial(deleteBtn.dataset.materialId);
                return;
            }
        });
    });

})();
