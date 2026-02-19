/**
 * Admin Payment Confirmations
 * Lightbox, modals odrzucenia/akceptacji, AJAX akcje
 */

(function() {
    'use strict';

    // ================================
    // CSRF Token
    // ================================
    function getCSRFToken() {
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag) return metaTag.getAttribute('content');
        const csrfInput = document.querySelector('input[name="csrf_token"]');
        if (csrfInput) return csrfInput.value;
        return '';
    }

    // ================================
    // State
    // ================================
    let currentConfirmationId = null;
    let currentOrderNumber = null;

    // ================================
    // LIGHTBOX
    // ================================
    const lightbox = document.getElementById('pcLightbox');
    const lightboxImage = document.getElementById('pcLightboxImage');
    const lightboxPdf = document.getElementById('pcLightboxPdf');
    const lightboxInfo = document.getElementById('pcLightboxInfo');
    const lightboxApproveBtn = document.getElementById('pcLightboxApprove');
    const lightboxRejectBtn = document.getElementById('pcLightboxReject');

    window.openLightbox = function(proofUrl, confirmationId, orderNumber, amount, isPdf) {
        if (!lightbox) return;

        currentConfirmationId = confirmationId;
        currentOrderNumber = orderNumber;
        // Sync z globalnymi zmiennymi dla inline onclick
        window.currentConfirmationId = confirmationId;
        window.currentOrderNumber = orderNumber;

        // Pokaż obrazek lub PDF
        if (isPdf) {
            if (lightboxImage) lightboxImage.style.display = 'none';
            if (lightboxPdf) {
                lightboxPdf.src = proofUrl;
                lightboxPdf.style.display = 'block';
            }
        } else {
            if (lightboxPdf) lightboxPdf.style.display = 'none';
            if (lightboxImage) {
                lightboxImage.src = proofUrl;
                lightboxImage.style.display = 'block';
            }
        }

        // Info
        if (lightboxInfo) {
            lightboxInfo.innerHTML = '<strong>' + orderNumber + '</strong> &mdash; ' + amount + ' PLN';
        }

        lightbox.classList.add('active');
        document.body.style.overflow = 'hidden';
    };

    window.closeLightbox = function() {
        if (!lightbox) return;
        lightbox.classList.remove('active');
        document.body.style.overflow = '';
        if (lightboxImage) lightboxImage.src = '';
        if (lightboxPdf) {
            lightboxPdf.src = '';
            lightboxPdf.style.display = 'none';
        }
    };

    // Zamknij lightbox kliknięciem w tło
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
    const confirmModal = document.getElementById('pcConfirmModal');
    const confirmOrderInfo = document.getElementById('pcConfirmOrderInfo');

    window.openConfirmApprove = function(confirmationId, orderNumber) {
        currentConfirmationId = confirmationId;
        currentOrderNumber = orderNumber;
        window.currentConfirmationId = confirmationId;
        window.currentOrderNumber = orderNumber;

        if (confirmOrderInfo) {
            confirmOrderInfo.textContent = orderNumber;
        }

        // Zamknij lightbox jeśli otwarty
        closeLightbox();

        if (confirmModal) {
            confirmModal.classList.add('active');
        }
    };

    window.closeConfirmModal = function() {
        if (confirmModal) {
            confirmModal.classList.remove('active');
        }
    };

    // Zamknij confirm modal kliknięciem w tło (modal-overlay)
    if (confirmModal) {
        confirmModal.addEventListener('click', function(e) {
            if (e.target === confirmModal) {
                closeConfirmModal();
            }
        });
    }

    window.submitApprove = function() {
        if (!currentConfirmationId) return;

        const btn = document.getElementById('pcConfirmApproveBtn');
        if (btn) {
            btn.classList.add('loading');
            btn.disabled = true;
        }

        fetch('/admin/payment-confirmations/' + currentConfirmationId + '/approve', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        })
        .then(function(response) { return response.json(); })
        .then(function(data) {
            if (data.success) {
                if (typeof window.showToast === 'function') {
                    window.showToast(data.message, 'success');
                }
                // Odśwież stronę po chwili
                setTimeout(function() {
                    location.reload();
                }, 1000);
            } else {
                if (typeof window.showToast === 'function') {
                    window.showToast(data.message || 'Wystąpił błąd', 'error');
                }
                if (btn) {
                    btn.classList.remove('loading');
                    btn.disabled = false;
                }
            }
        })
        .catch(function(error) {
            console.error('Error:', error);
            if (typeof window.showToast === 'function') {
                window.showToast('Wystąpił błąd połączenia', 'error');
            }
            if (btn) {
                btn.classList.remove('loading');
                btn.disabled = false;
            }
        });
    };

    // ================================
    // REJECT MODAL
    // ================================
    const rejectModal = document.getElementById('pcRejectModal');
    const rejectTextarea = document.getElementById('pcRejectReason');
    const rejectError = document.getElementById('pcRejectError');

    window.openRejectModal = function(confirmationId, orderNumber) {
        currentConfirmationId = confirmationId;
        currentOrderNumber = orderNumber;
        window.currentConfirmationId = confirmationId;
        window.currentOrderNumber = orderNumber;

        // Zamknij lightbox jeśli otwarty
        closeLightbox();

        if (rejectTextarea) {
            rejectTextarea.value = '';
            rejectTextarea.classList.remove('error');
        }
        if (rejectError) {
            rejectError.classList.remove('visible');
        }

        if (rejectModal) {
            rejectModal.classList.add('active');
            // Focus na textarea
            setTimeout(function() {
                if (rejectTextarea) rejectTextarea.focus();
            }, 100);
        }
    };

    window.closeRejectModal = function() {
        if (rejectModal) {
            rejectModal.classList.remove('active');
        }
    };

    // Zamknij reject modal kliknięciem w tło (modal-overlay)
    if (rejectModal) {
        rejectModal.addEventListener('click', function(e) {
            if (e.target === rejectModal) {
                closeRejectModal();
            }
        });
    }

    window.submitReject = function() {
        if (!currentConfirmationId) return;

        var reason = rejectTextarea ? rejectTextarea.value.trim() : '';

        // Walidacja
        if (!reason || reason.length < 10) {
            if (rejectTextarea) rejectTextarea.classList.add('error');
            if (rejectError) {
                rejectError.textContent = 'Podaj powód odrzucenia (min. 10 znaków). Aktualnie: ' + reason.length;
                rejectError.classList.add('visible');
            }
            return;
        }

        const btn = document.getElementById('pcRejectSubmitBtn');
        if (btn) {
            btn.classList.add('loading');
            btn.disabled = true;
        }

        fetch('/admin/payment-confirmations/' + currentConfirmationId + '/reject', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                rejection_reason: reason
            })
        })
        .then(function(response) { return response.json(); })
        .then(function(data) {
            if (data.success) {
                if (typeof window.showToast === 'function') {
                    window.showToast(data.message, 'success');
                }
                setTimeout(function() {
                    location.reload();
                }, 1000);
            } else {
                if (typeof window.showToast === 'function') {
                    window.showToast(data.message || 'Wystąpił błąd', 'error');
                }
                if (btn) {
                    btn.classList.remove('loading');
                    btn.disabled = false;
                }
            }
        })
        .catch(function(error) {
            console.error('Error:', error);
            if (typeof window.showToast === 'function') {
                window.showToast('Wystąpił błąd połączenia', 'error');
            }
            if (btn) {
                btn.classList.remove('loading');
                btn.disabled = false;
            }
        });
    };

    // Walidacja na bieżąco
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
        // ESC - zamknij modals/lightbox
        if (e.key === 'Escape') {
            if (rejectModal && rejectModal.classList.contains('active')) {
                closeRejectModal();
            } else if (confirmModal && confirmModal.classList.contains('active')) {
                closeConfirmModal();
            } else if (lightbox && lightbox.classList.contains('active')) {
                closeLightbox();
            }
        }
    });

    // ================================
    // FILTERS (auto-submit on change)
    // ================================
    var filterSelects = document.querySelectorAll('.pc-filter-select');
    filterSelects.forEach(function(select) {
        select.addEventListener('change', function() {
            // Build URL with current filter values
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
