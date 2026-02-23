/**
 * Admin Payment Confirmations
 * Lightbox z sekwencyjnym zatwierdzaniem, grupowanie dowodów, obsługa klawiatury
 */

(function() {
    'use strict';

    // ================================
    // CSRF Token
    // ================================
    function getCSRFToken() {
        var metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag) return metaTag.getAttribute('content');
        var csrfInput = document.querySelector('input[name="csrf_token"]');
        if (csrfInput) return csrfInput.value;
        return '';
    }

    // ================================
    // State
    // ================================
    var pendingList = [];
    var currentPendingIndex = -1;
    var currentItem = null; // aktualnie wyświetlany element (grupa)

    // ================================
    // BUILD PENDING LIST FROM DOM (groups)
    // ================================
    function buildPendingList() {
        pendingList = [];
        document.querySelectorAll('tr[data-status="pending"]').forEach(function(row) {
            pendingList.push({
                ids: row.dataset.confirmationIds.split(',').map(Number),
                proofUrl: row.dataset.proofUrl,
                orderNumbers: row.dataset.orderNumbers.split(','),
                totalAmount: row.dataset.totalAmount,
                isPdf: row.dataset.isPdf === 'true',
                proofFile: row.dataset.proofFile,
                row: row
            });
        });
    }

    buildPendingList();

    // ================================
    // LIGHTBOX
    // ================================
    var lightbox = document.getElementById('pcLightbox');
    var lightboxImage = document.getElementById('pcLightboxImage');
    var lightboxPdf = document.getElementById('pcLightboxPdf');
    var lightboxInfo = document.getElementById('pcLightboxInfo');
    var lightboxCounter = document.getElementById('pcLightboxCounter');
    var lightboxActions = document.getElementById('pcLightboxActions');

    function findPendingIndex(ids) {
        var key = ids.join(',');
        return pendingList.findIndex(function(item) {
            return item.ids.join(',') === key;
        });
    }

    function updateLightboxContent(item) {
        if (!item || !lightbox) return;

        currentItem = item;
        currentPendingIndex = pendingList.indexOf(item);

        // Obrazek lub PDF
        if (item.isPdf) {
            if (lightboxImage) lightboxImage.style.display = 'none';
            if (lightboxPdf) {
                lightboxPdf.src = item.proofUrl;
                lightboxPdf.style.display = 'block';
            }
        } else {
            if (lightboxPdf) { lightboxPdf.src = ''; lightboxPdf.style.display = 'none'; }
            if (lightboxImage) {
                lightboxImage.src = item.proofUrl;
                lightboxImage.style.display = 'block';
            }
        }

        // Info — lista zamówień
        if (lightboxInfo) {
            var ordersHtml = item.orderNumbers.map(function(n) { return '<strong>' + n + '</strong>'; }).join(', ');
            lightboxInfo.innerHTML = ordersHtml + ' &mdash; ' + item.totalAmount + ' PLN';
            if (item.ids.length > 1) {
                lightboxInfo.innerHTML += ' <small>(' + item.ids.length + ' zamówień)</small>';
            }
        }

        // Counter: "2 z 8 oczekujących"
        if (lightboxCounter) {
            if (pendingList.length > 1) {
                lightboxCounter.textContent = (currentPendingIndex + 1) + ' z ' + pendingList.length + ' oczekujących';
                lightboxCounter.style.display = '';
            } else if (pendingList.length === 1) {
                lightboxCounter.textContent = '1 z 1 oczekujących';
                lightboxCounter.style.display = '';
            } else {
                lightboxCounter.style.display = 'none';
            }
        }

        // Pokaż przyciski akcji
        if (lightboxActions) {
            lightboxActions.style.display = '';
        }
    }

    // Otwórz lightbox z wiersza tabeli
    window.openLightboxFromRow = function(el) {
        if (!lightbox) return;
        var row = el.closest('tr');
        if (!row) return;

        var ids = row.dataset.confirmationIds.split(',').map(Number);
        var item = pendingList.find(function(p) { return p.ids.join(',') === ids.join(','); });

        if (item) {
            updateLightboxContent(item);
        } else {
            // Nie-pending — podgląd bez akcji
            currentItem = null;
            currentPendingIndex = -1;
            var proofUrl = row.dataset.proofUrl;
            var isPdf = row.dataset.isPdf === 'true';
            var orderNumbers = row.dataset.orderNumbers.split(',');
            var totalAmount = row.dataset.totalAmount;

            if (isPdf) {
                if (lightboxImage) lightboxImage.style.display = 'none';
                if (lightboxPdf) { lightboxPdf.src = proofUrl; lightboxPdf.style.display = 'block'; }
            } else {
                if (lightboxPdf) { lightboxPdf.src = ''; lightboxPdf.style.display = 'none'; }
                if (lightboxImage) { lightboxImage.src = proofUrl; lightboxImage.style.display = 'block'; }
            }
            if (lightboxInfo) {
                var ordersHtml = orderNumbers.map(function(n) { return '<strong>' + n + '</strong>'; }).join(', ');
                lightboxInfo.innerHTML = ordersHtml + ' &mdash; ' + totalAmount + ' PLN';
            }
            if (lightboxCounter) lightboxCounter.style.display = 'none';
            if (lightboxActions) lightboxActions.style.display = 'none';
        }

        lightbox.classList.add('active');
        document.body.style.overflow = 'hidden';
    };

    function showNextPending() {
        var lightboxWasOpen = lightbox && lightbox.classList.contains('active');

        if (pendingList.length === 0) {
            closeLightbox();
            if (typeof window.showToast === 'function') {
                window.showToast('Wszystkie potwierdzenia rozpatrzone!', 'success');
            }
            return;
        }

        // Przełączaj na następny pending tylko jeśli lightbox był otwarty
        if (!lightboxWasOpen) return;

        var nextIndex = currentPendingIndex;
        if (nextIndex >= pendingList.length) nextIndex = 0;
        if (nextIndex < 0) nextIndex = 0;
        updateLightboxContent(pendingList[nextIndex]);
    }

    function removeGroupFromPendingAndDom(item) {
        var idx = pendingList.indexOf(item);
        if (idx !== -1) {
            var row = item.row;
            if (row) {
                row.classList.remove('row-pending');
                row.dataset.status = 'approved';
                var badge = row.querySelector('.status-badge');
                if (badge) {
                    badge.className = 'badge status-badge pc-badge-approved';
                    badge.textContent = 'Zaakceptowane';
                }
                var actions = row.querySelector('.pc-actions');
                if (actions) {
                    actions.innerHTML = '<span class="text-muted">Zatwierdzono</span>';
                }
            }
            pendingList.splice(idx, 1);
        }
        updateFilterCounts();
    }

    function removeGroupFromPendingAndDomRejected(item) {
        var idx = pendingList.indexOf(item);
        if (idx !== -1) {
            var row = item.row;
            if (row) {
                row.classList.remove('row-pending');
                row.dataset.status = 'rejected';
                var badge = row.querySelector('.status-badge');
                if (badge) {
                    badge.className = 'badge status-badge pc-badge-rejected';
                    badge.textContent = 'Odrzucone';
                }
                var actions = row.querySelector('.pc-actions');
                if (actions) {
                    actions.innerHTML = '<span class="text-muted">Odrzucono</span>';
                }
            }
            pendingList.splice(idx, 1);
        }
        updateFilterCounts();
    }

    function updateFilterCounts() {
        var pendingCount = pendingList.length;
        var filterBtns = document.querySelectorAll('.filter-btn');
        filterBtns.forEach(function(btn) {
            var href = btn.getAttribute('href') || '';
            var countEl = btn.querySelector('.filter-count');
            if (!countEl) return;
            if (href.indexOf('status=pending') !== -1) {
                countEl.textContent = pendingCount;
            }
            if (href.indexOf('status=') === -1) {
                var totalRows = document.querySelectorAll('tr[data-confirmation-ids]').length;
                countEl.textContent = totalRows;
            }
        });
    }

    window.closeLightbox = function() {
        if (!lightbox) return;
        lightbox.classList.remove('active');
        document.body.style.overflow = '';
        if (lightboxImage) lightboxImage.src = '';
        if (lightboxPdf) { lightboxPdf.src = ''; lightboxPdf.style.display = 'none'; }
    };

    if (lightbox) {
        lightbox.addEventListener('click', function(e) {
            if (e.target === lightbox) {
                closeLightbox();
            }
        });
    }

    // ================================
    // CONFIRM MODAL (Approve)
    // ================================
    var confirmModal = document.getElementById('pcConfirmModal');
    var confirmOrderInfo = document.getElementById('pcConfirmOrderInfo');

    window.openConfirmApprove = function() {
        if (!currentItem) return;

        if (confirmOrderInfo) {
            var text = currentItem.orderNumbers.join(', ');
            if (currentItem.ids.length > 1) {
                text += ' (' + currentItem.ids.length + ' potwierdzeń)';
            }
            confirmOrderInfo.textContent = text;
        }

        if (confirmModal) {
            confirmModal.classList.add('active');
        }
    };

    // Otwórz approve z wiersza tabeli (przycisk w tabeli)
    window.openConfirmApproveFromRow = function(el) {
        var row = el.closest('tr');
        if (!row) return;
        var ids = row.dataset.confirmationIds.split(',').map(Number);
        var item = pendingList.find(function(p) { return p.ids.join(',') === ids.join(','); });
        if (item) {
            currentItem = item;
            currentPendingIndex = pendingList.indexOf(item);
        }
        openConfirmApprove();
    };

    window.closeConfirmModal = function() {
        if (confirmModal) {
            confirmModal.classList.remove('active');
        }
    };

    if (confirmModal) {
        confirmModal.addEventListener('click', function(e) {
            if (e.target === confirmModal) {
                closeConfirmModal();
            }
        });
    }

    // ================================
    // APPROVE SUBMISSION (always bulk)
    // ================================
    window.submitApprove = function() {
        if (!currentItem) return;

        var btn = document.getElementById('pcConfirmApproveBtn');
        if (btn) {
            btn.classList.add('loading');
            btn.disabled = true;
        }

        var itemToApprove = currentItem;

        fetch('/admin/payment-confirmations/bulk-approve', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ confirmation_ids: itemToApprove.ids })
        })
        .then(function(response) { return response.json(); })
        .then(function(data) {
            if (data.success) {
                if (typeof window.showToast === 'function') {
                    window.showToast(data.message, 'success');
                }
                removeGroupFromPendingAndDom(itemToApprove);
                closeConfirmModal();
                showNextPending();
            } else {
                if (typeof window.showToast === 'function') {
                    window.showToast(data.message || 'Wystąpił błąd', 'error');
                }
            }
            if (btn) { btn.classList.remove('loading'); btn.disabled = false; }
        })
        .catch(function(error) {
            console.error('Error:', error);
            if (typeof window.showToast === 'function') {
                window.showToast('Wystąpił błąd połączenia', 'error');
            }
            if (btn) { btn.classList.remove('loading'); btn.disabled = false; }
        });
    };

    // ================================
    // REJECT MODAL
    // ================================
    var rejectModal = document.getElementById('pcRejectModal');
    var rejectTextarea = document.getElementById('pcRejectReason');
    var rejectError = document.getElementById('pcRejectError');

    window.openRejectModal = function() {
        if (!currentItem) return;

        if (rejectTextarea) {
            rejectTextarea.value = '';
            rejectTextarea.classList.remove('error');
        }
        if (rejectError) {
            rejectError.classList.remove('visible');
        }

        if (rejectModal) {
            rejectModal.classList.add('active');
            setTimeout(function() {
                if (rejectTextarea) rejectTextarea.focus();
            }, 100);
        }
    };

    // Otwórz reject z wiersza tabeli
    window.openRejectFromRow = function(el) {
        var row = el.closest('tr');
        if (!row) return;
        var ids = row.dataset.confirmationIds.split(',').map(Number);
        var item = pendingList.find(function(p) { return p.ids.join(',') === ids.join(','); });
        if (item) {
            currentItem = item;
            currentPendingIndex = pendingList.indexOf(item);
        }
        openRejectModal();
    };

    window.closeRejectModal = function() {
        if (rejectModal) {
            rejectModal.classList.remove('active');
        }
    };

    if (rejectModal) {
        rejectModal.addEventListener('click', function(e) {
            if (e.target === rejectModal) {
                closeRejectModal();
            }
        });
    }

    // ================================
    // REJECT SUBMISSION (bulk)
    // ================================
    window.submitReject = function() {
        if (!currentItem) return;

        var reason = rejectTextarea ? rejectTextarea.value.trim() : '';

        if (!reason || reason.length < 10) {
            if (rejectTextarea) rejectTextarea.classList.add('error');
            if (rejectError) {
                rejectError.textContent = 'Podaj powód odrzucenia (min. 10 znaków). Aktualnie: ' + reason.length;
                rejectError.classList.add('visible');
            }
            return;
        }

        var btn = document.getElementById('pcRejectSubmitBtn');
        if (btn) {
            btn.classList.add('loading');
            btn.disabled = true;
        }

        var itemToReject = currentItem;

        fetch('/admin/payment-confirmations/bulk-reject', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                confirmation_ids: itemToReject.ids,
                rejection_reason: reason
            })
        })
        .then(function(response) { return response.json(); })
        .then(function(data) {
            if (data.success) {
                if (typeof window.showToast === 'function') {
                    window.showToast(data.message, 'success');
                }
                removeGroupFromPendingAndDomRejected(itemToReject);
                closeRejectModal();
                showNextPending();
            } else {
                if (typeof window.showToast === 'function') {
                    window.showToast(data.message || 'Wystąpił błąd', 'error');
                }
                if (btn) { btn.classList.remove('loading'); btn.disabled = false; }
            }
        })
        .catch(function(error) {
            console.error('Error:', error);
            if (typeof window.showToast === 'function') {
                window.showToast('Wystąpił błąd połączenia', 'error');
            }
            if (btn) { btn.classList.remove('loading'); btn.disabled = false; }
        });
    };

    if (rejectTextarea) {
        rejectTextarea.addEventListener('input', function() {
            this.classList.remove('error');
            if (rejectError) rejectError.classList.remove('visible');
        });
    }

    // ================================
    // KEYBOARD NAVIGATION
    // ================================
    document.addEventListener('keydown', function(e) {
        // ESC - zamknij modals/lightbox (priorytet: reject > confirm > lightbox)
        if (e.key === 'Escape') {
            if (rejectModal && rejectModal.classList.contains('active')) {
                closeRejectModal();
            } else if (confirmModal && confirmModal.classList.contains('active')) {
                closeConfirmModal();
            } else if (lightbox && lightbox.classList.contains('active')) {
                closeLightbox();
            }
        }

        // ENTER - akceptacja
        if (e.key === 'Enter') {
            // Nie reaguj gdy reject modal jest otwarty (textarea potrzebuje Enter)
            if (rejectModal && rejectModal.classList.contains('active')) {
                return;
            }
            // W confirm modal → zatwierdź
            if (confirmModal && confirmModal.classList.contains('active')) {
                e.preventDefault();
                submitApprove();
                return;
            }
            // W lightboxie → otwórz confirm
            if (lightbox && lightbox.classList.contains('active') && currentItem) {
                e.preventDefault();
                openConfirmApprove();
                return;
            }
        }
    });

    // ================================
    // FILTERS (auto-submit on change)
    // ================================
    var filterSelects = document.querySelectorAll('.pc-filter-select');
    filterSelects.forEach(function(select) {
        select.addEventListener('change', function() {
            var statusFilter = document.getElementById('pcStatusFilter');
            var stageFilter = document.getElementById('pcStageFilter');

            var params = new URLSearchParams();
            if (statusFilter && statusFilter.value !== 'all') {
                params.set('status', statusFilter.value);
            }
            if (stageFilter && stageFilter.value !== 'all') {
                params.set('stage', stageFilter.value);
            }

            var url = window.location.pathname;
            var queryString = params.toString();
            if (queryString) {
                url += '?' + queryString;
            }

            window.location.href = url;
        });
    });

})();
