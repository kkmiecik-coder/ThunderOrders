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
        // Collect from both table rows and mobile cards, deduplicate by ids
        var seen = {};
        document.querySelectorAll('[data-status="pending"][data-confirmation-ids]').forEach(function(el) {
            var key = el.dataset.confirmationIds;
            if (seen[key]) return;
            // Skip hidden elements (mobile cards hidden on desktop, table rows hidden on mobile)
            if (el.offsetParent === null) return;
            seen[key] = true;
            pendingList.push({
                ids: key.split(',').map(Number),
                proofUrl: el.dataset.proofUrl,
                orderNumbers: el.dataset.orderNumbers.split(','),
                totalAmount: el.dataset.totalAmount,
                isPdf: el.dataset.isPdf === 'true',
                proofFile: el.dataset.proofFile,
                row: el
            });
        });
    }

    buildPendingList();

    // ================================
    // LIGHTBOX
    // ================================
    var lightbox = document.getElementById('pcLightbox');
    var lightboxImage = document.getElementById('pcLightboxImage');
    var lightboxImageWrap = document.getElementById('pcLightboxImageWrap');
    var lightboxPdf = document.getElementById('pcLightboxPdf');
    var lightboxInfo = document.getElementById('pcLightboxInfo');
    var lightboxCounter = document.getElementById('pcLightboxCounter');
    var lightboxActions = document.getElementById('pcLightboxActions');
    var lightboxLoading = document.getElementById('pcLightboxLoading');
    var lightboxOpenPdf = document.getElementById('pcLightboxOpenPdf');

    // Token do anulowania nieaktualnych requestów, gdy user szybko przeskakuje między obrazami
    var currentImageLoadToken = 0;
    var currentPdfUrl = null;
    var lightboxPanzoom = null;
    var wheelHandlerAttached = false;

    function destroyPanzoom() {
        if (lightboxPanzoom) {
            try { lightboxPanzoom.destroy(); } catch (e) { /* ignore */ }
            lightboxPanzoom = null;
        }
        if (lightboxImage) {
            lightboxImage.style.transform = '';
        }
    }

    function initPanzoomForImage() {
        destroyPanzoom();
        if (typeof Panzoom !== 'function' || !lightboxImage) return;

        lightboxPanzoom = Panzoom(lightboxImage, {
            maxScale: 6,
            minScale: 1,
            step: 0.3,
            animate: true,
            cursor: 'grab',
            origin: '50% 50%'  // Zoom/pan z centrum elementu (bez tego Panzoom używa '0 0' i rośnie w prawo-dół)
        });

        // Wheel zoom — zawsze z centrum obrazu (ignorujemy pozycję kursora)
        if (lightbox && !wheelHandlerAttached) {
            lightbox.addEventListener('wheel', function(e) {
                if (!lightboxPanzoom) return;
                if (!lightboxImage || lightboxImage.style.display === 'none') return;
                e.preventDefault();

                var currentScale = lightboxPanzoom.getScale();
                var step = 0.15;
                var newScale = e.deltaY < 0
                    ? currentScale * (1 + step)
                    : currentScale / (1 + step);

                newScale = Math.max(1, Math.min(6, newScale));
                lightboxPanzoom.zoom(newScale, { animate: false });
            }, { passive: false });
            wheelHandlerAttached = true;
        }
    }

    window.openLightboxPdfInNewTab = function() {
        if (currentPdfUrl) {
            window.open(currentPdfUrl, '_blank', 'noopener,noreferrer');
        }
    };

    function loadLightboxImage(url) {
        if (!lightboxImage) return;

        var token = ++currentImageLoadToken;

        destroyPanzoom();
        lightboxImage.style.display = 'none';
        if (lightboxImageWrap) lightboxImageWrap.style.display = 'none';
        if (lightboxLoading) {
            lightboxLoading.classList.remove('error');
            var textEl = lightboxLoading.querySelector('.pc-lightbox-loading-text');
            if (textEl) textEl.textContent = 'Ładowanie obrazu...';
            lightboxLoading.classList.add('active');
        }

        if (!url) {
            if (lightboxLoading) {
                lightboxLoading.classList.add('error');
                var errText = lightboxLoading.querySelector('.pc-lightbox-loading-text');
                if (errText) errText.textContent = 'Brak pliku do wyświetlenia';
            }
            return;
        }

        var preloader = new Image();
        preloader.onload = function() {
            if (token !== currentImageLoadToken) return;
            lightboxImage.src = url;
            lightboxImage.style.display = 'block';
            if (lightboxImageWrap) lightboxImageWrap.style.display = 'flex';
            if (lightboxLoading) lightboxLoading.classList.remove('active');
            initPanzoomForImage();
        };
        preloader.onerror = function() {
            if (token !== currentImageLoadToken) return;
            if (lightboxLoading) {
                lightboxLoading.classList.add('error');
                var errText = lightboxLoading.querySelector('.pc-lightbox-loading-text');
                if (errText) errText.textContent = 'Nie udało się załadować obrazu';
            }
        };
        preloader.src = url;
    }

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
            destroyPanzoom();
            if (lightboxLoading) lightboxLoading.classList.remove('active');
            if (lightboxImage) lightboxImage.style.display = 'none';
            if (lightboxImageWrap) lightboxImageWrap.style.display = 'none';
            if (lightboxPdf) {
                lightboxPdf.src = item.proofUrl;
                lightboxPdf.style.display = 'block';
            }
            currentPdfUrl = item.proofUrl;
            if (lightboxOpenPdf) lightboxOpenPdf.style.display = 'inline-flex';
        } else {
            if (lightboxPdf) { lightboxPdf.src = ''; lightboxPdf.style.display = 'none'; }
            currentPdfUrl = null;
            if (lightboxOpenPdf) lightboxOpenPdf.style.display = 'none';
            loadLightboxImage(item.proofUrl);
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

        // Pokaż przyciski akcji (oba — pending ma approve + reject)
        if (lightboxActions) {
            lightboxActions.style.display = '';
            var approveBtn = lightboxActions.querySelector('.pc-btn-approve');
            var rejectBtn = lightboxActions.querySelector('.pc-btn-reject');
            if (approveBtn) approveBtn.style.display = '';
            if (rejectBtn) rejectBtn.style.display = '';
        }
    }

    // Otwórz lightbox z wiersza tabeli lub karty mobilnej
    window.openLightboxFromRow = function(el) {
        if (!lightbox) return;
        var row = el.closest('tr') || el.closest('.pc-card');
        if (!row) return;

        var ids = row.dataset.confirmationIds.split(',').map(Number);
        var item = pendingList.find(function(p) { return p.ids.join(',') === ids.join(','); });

        if (item) {
            updateLightboxContent(item);
        } else {
            // Nie-pending — podgląd z ograniczonymi akcjami
            var proofUrl = row.dataset.proofUrl;
            var isPdf = row.dataset.isPdf === 'true';
            var orderNumbers = row.dataset.orderNumbers.split(',');
            var totalAmount = row.dataset.totalAmount;
            var status = row.dataset.status;

            // Store as currentItem so approve/reject actions can use it
            currentItem = {
                ids: ids,
                proofUrl: proofUrl,
                orderNumbers: orderNumbers,
                totalAmount: totalAmount,
                isPdf: isPdf,
                proofFile: row.dataset.proofFile,
                row: row
            };
            currentPendingIndex = -1;

            if (isPdf) {
                destroyPanzoom();
                if (lightboxLoading) lightboxLoading.classList.remove('active');
                if (lightboxImage) lightboxImage.style.display = 'none';
                if (lightboxImageWrap) lightboxImageWrap.style.display = 'none';
                if (lightboxPdf) { lightboxPdf.src = proofUrl; lightboxPdf.style.display = 'block'; }
                currentPdfUrl = proofUrl;
                if (lightboxOpenPdf) lightboxOpenPdf.style.display = 'inline-flex';
            } else {
                if (lightboxPdf) { lightboxPdf.src = ''; lightboxPdf.style.display = 'none'; }
                currentPdfUrl = null;
                if (lightboxOpenPdf) lightboxOpenPdf.style.display = 'none';
                loadLightboxImage(proofUrl);
            }
            if (lightboxInfo) {
                var ordersHtml = orderNumbers.map(function(n) { return '<strong>' + n + '</strong>'; }).join(', ');
                lightboxInfo.innerHTML = ordersHtml + ' &mdash; ' + totalAmount + ' PLN';
            }
            if (lightboxCounter) lightboxCounter.style.display = 'none';

            // Show actions for non-rejected items
            if (lightboxActions) {
                if (status === 'rejected') {
                    lightboxActions.style.display = 'none';
                } else {
                    lightboxActions.style.display = '';
                    // For approved: hide approve button, show only reject
                    var approveBtn = lightboxActions.querySelector('.pc-btn-approve');
                    var rejectBtn = lightboxActions.querySelector('.pc-btn-reject');
                    if (status === 'approved') {
                        if (approveBtn) approveBtn.style.display = 'none';
                        if (rejectBtn) rejectBtn.style.display = '';
                    } else {
                        if (approveBtn) approveBtn.style.display = '';
                        if (rejectBtn) rejectBtn.style.display = '';
                    }
                }
            }
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
        currentImageLoadToken++;
        destroyPanzoom();
        lightbox.classList.remove('active');
        document.body.style.overflow = '';
        if (lightboxImage) lightboxImage.src = '';
        if (lightboxPdf) { lightboxPdf.src = ''; lightboxPdf.style.display = 'none'; }
        if (lightboxLoading) lightboxLoading.classList.remove('active', 'error');
        if (lightboxOpenPdf) lightboxOpenPdf.style.display = 'none';
        currentPdfUrl = null;
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

    // Otwórz approve z wiersza tabeli lub karty mobilnej
    window.openConfirmApproveFromRow = function(el) {
        var row = el.closest('tr') || el.closest('.pc-card');
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

        // Reset przycisku — może zostać w stanie loading po poprzednim odrzuceniu
        var submitBtn = document.getElementById('pcRejectSubmitBtn');
        if (submitBtn) {
            submitBtn.classList.remove('loading');
            submitBtn.disabled = false;
        }

        if (rejectModal) {
            rejectModal.classList.add('active');
            setTimeout(function() {
                if (rejectTextarea) rejectTextarea.focus();
            }, 100);
        }
    };

    // Otwórz reject z wiersza tabeli lub karty mobilnej
    window.openRejectFromRow = function(el) {
        var row = el.closest('tr') || el.closest('.pc-card');
        if (!row) return;
        var ids = row.dataset.confirmationIds.split(',').map(Number);
        var item = pendingList.find(function(p) { return p.ids.join(',') === ids.join(','); });
        if (item) {
            currentItem = item;
            currentPendingIndex = pendingList.indexOf(item);
        } else {
            // Approved item — not in pendingList, build temporary item from row data
            currentItem = {
                ids: ids,
                proofUrl: row.dataset.proofUrl,
                orderNumbers: row.dataset.orderNumbers ? row.dataset.orderNumbers.split(',') : [],
                totalAmount: row.dataset.totalAmount,
                isPdf: row.dataset.isPdf === 'true',
                proofFile: row.dataset.proofFile,
                row: row,
                isApproved: true
            };
            currentPendingIndex = -1;
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

                if (itemToReject.isApproved) {
                    // Odrzucono zatwierdzone — aktualizuj wiersz
                    updateRowToRejected(itemToReject);
                } else {
                    // Odrzucono pending — standardowy flow
                    removeGroupFromPendingAndDomRejected(itemToReject);
                    showNextPending();
                }
                closeRejectModal();
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

    function updateRowToRejected(item) {
        var row = item.row;
        if (!row) return;
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
        updateFilterCounts();
    }

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

    // ================================
    // OCR DETAILS TOOLTIP
    // ================================

    var activeTooltip = null;

    function closeOcrTooltip() {
        if (activeTooltip) {
            activeTooltip.remove();
            activeTooltip = null;
        }
    }

    function getScoreIcon(score, max) {
        if (score >= max * 0.8) return '<span style="color:#10b981">&#10003;</span>';
        if (score > 0) return '<span style="color:#f59e0b">~</span>';
        return '<span style="color:#ef4444">&#10007;</span>';
    }

    function formatAmountDetail(info) {
        if (!info) return '';
        if (info.match === 'none' || !info.best_match) return 'nie znaleziono';
        var label = info.precise === false ? ' (bez groszy)' : '';
        return 'znaleziono ' + info.best_match + ' PLN' + label;
    }

    function formatTitleDetail(info) {
        if (!info) return '';
        if (info.match === 'none' || !info.found || info.found.length === 0) return 'nie znaleziono';
        return 'znaleziono ' + info.found.join(', ');
    }

    function formatRecipientDetail(info) {
        if (!info) return '';
        if (info.match === 'no_method') return 'brak metody';
        if (info.match === 'none' || !info.found || info.found.length === 0) return 'nie znaleziono';
        var labels = info.found.map(function(f) {
            return f.replace(/^(keyword|account|recipient|recipient_word|code):/, '');
        });
        return 'znaleziono ' + labels.join(', ');
    }

    function formatReadabilityDetail(info) {
        if (!info) return '';
        var q = info.quality || 'poor';
        if (q === 'good') return 'dobra';
        if (q === 'fair') return 'średnia';
        return 'słaba';
    }

    function showOcrTooltip(btn) {
        closeOcrTooltip();

        var raw = btn.getAttribute('data-ocr-details');
        if (!raw) return;

        var details;
        try {
            details = JSON.parse(raw);
        } catch (e) {
            return;
        }

        var amount = details.amount || {};
        var title = details.title || {};
        var recipient = details.recipient || {};
        var readability = details.readability || {};

        var html = '<div class="ocr-tooltip">';

        html += '<div class="ocr-tooltip-row">';
        html += '<span class="ocr-tooltip-label">Kwota</span>';
        html += '<span class="ocr-tooltip-value">' + (amount.score || 0) + '/40 pkt. ' + getScoreIcon(amount.score || 0, 40);
        html += '<span class="ocr-tooltip-detail">(' + formatAmountDetail(amount) + ')</span></span>';
        html += '</div>';

        html += '<div class="ocr-tooltip-row">';
        html += '<span class="ocr-tooltip-label">Tytuł</span>';
        html += '<span class="ocr-tooltip-value">' + (title.score || 0) + '/30 pkt. ' + getScoreIcon(title.score || 0, 30);
        html += '<span class="ocr-tooltip-detail">(' + formatTitleDetail(title) + ')</span></span>';
        html += '</div>';

        html += '<div class="ocr-tooltip-row">';
        html += '<span class="ocr-tooltip-label">Odbiorca</span>';
        html += '<span class="ocr-tooltip-value">' + (recipient.score || 0) + '/20 pkt. ' + getScoreIcon(recipient.score || 0, 20);
        html += '<span class="ocr-tooltip-detail">(' + formatRecipientDetail(recipient) + ')</span></span>';
        html += '</div>';

        html += '<div class="ocr-tooltip-row">';
        html += '<span class="ocr-tooltip-label">Czytelność</span>';
        html += '<span class="ocr-tooltip-value">' + (readability.score || 0) + '/10 pkt. ' + getScoreIcon(readability.score || 0, 10);
        html += '<span class="ocr-tooltip-detail">(' + formatReadabilityDetail(readability) + ')</span></span>';
        html += '</div>';

        html += '</div>';

        var tooltip = document.createElement('div');
        tooltip.innerHTML = html;
        activeTooltip = tooltip.firstChild;

        document.body.appendChild(activeTooltip);

        // Position below the button
        var rect = btn.getBoundingClientRect();
        activeTooltip.style.position = 'fixed';
        activeTooltip.style.top = (rect.bottom + 6) + 'px';
        activeTooltip.style.left = Math.max(8, rect.left - 100) + 'px';
    }

    // Event delegation for OCR info buttons
    document.addEventListener('click', function(e) {
        var btn = e.target.closest('.ocr-info-btn');
        if (btn) {
            e.preventDefault();
            e.stopPropagation();
            if (activeTooltip) {
                closeOcrTooltip();
            } else {
                showOcrTooltip(btn);
            }
            return;
        }
        // Close tooltip when clicking outside
        if (activeTooltip && !e.target.closest('.ocr-tooltip')) {
            closeOcrTooltip();
        }

        // Close filter dropdown when clicking outside
        var filterWrapper = document.querySelector('.pc-filter-dropdown-wrapper');
        if (filterWrapper && filterWrapper.classList.contains('open') && !e.target.closest('.pc-filter-dropdown-wrapper')) {
            filterWrapper.classList.remove('open');
        }
    });

    // ================================
    // HIGHLIGHT CONFIRMATION (from order detail link)
    // ================================
    (function highlightFromUrl() {
        var params = new URLSearchParams(window.location.search);
        var highlightId = params.get('highlight');
        if (!highlightId) return;

        // Find ALL matching elements (desktop <tr> + mobile .pc-card)
        var elements = document.querySelectorAll('[data-confirmation-ids]');
        var matches = [];
        for (var i = 0; i < elements.length; i++) {
            var ids = elements[i].getAttribute('data-confirmation-ids').split(',');
            if (ids.indexOf(highlightId) !== -1) {
                matches.push(elements[i]);
            }
        }
        if (matches.length === 0) return;

        // Pick the visible one for scrolling (offsetParent !== null)
        var scrollTarget = null;
        for (var i = 0; i < matches.length; i++) {
            if (matches[i].offsetParent !== null) {
                scrollTarget = matches[i];
                break;
            }
        }
        if (!scrollTarget) scrollTarget = matches[0];

        // Scroll and pulse immediately
        scrollTarget.scrollIntoView({ behavior: 'smooth', block: 'center' });

        requestAnimationFrame(function() {
            for (var i = 0; i < matches.length; i++) {
                var el = matches[i];
                el.classList.add('pc-highlight-pulse');

                if (el.tagName === 'TR') {
                    var cells = el.querySelectorAll('td');
                    for (var j = 0; j < cells.length; j++) {
                        cells[j].classList.add('pc-highlight-pulse-cell');
                    }
                }
            }

            // Clean up after animation (2s)
            setTimeout(function() {
                for (var i = 0; i < matches.length; i++) {
                    matches[i].classList.remove('pc-highlight-pulse');
                    var marked = matches[i].querySelectorAll('.pc-highlight-pulse-cell');
                    for (var j = 0; j < marked.length; j++) {
                        marked[j].classList.remove('pc-highlight-pulse-cell');
                    }
                }
            }, 2200);
        });
    })();

    // ================================
    // FILTER DROPDOWN TOGGLE
    // ================================
    var filterToggle = document.getElementById('pcFilterToggle');
    if (filterToggle) {
        filterToggle.addEventListener('click', function(e) {
            e.stopPropagation();
            var wrapper = this.closest('.pc-filter-dropdown-wrapper');
            wrapper.classList.toggle('open');
        });
    }

})();
