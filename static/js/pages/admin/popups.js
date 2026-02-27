/**
 * ThunderOrders - Popups Admin
 * Obsługa listy i formularza popupów w panelu admina
 */

(function() {
    'use strict';

    // ==========================================
    // Helpers
    // ==========================================

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    /** Przyciemnia kolor HEX o podany procent (0-100) */
    function darkenColor(hex, percent) {
        hex = hex.replace('#', '');
        if (hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
        const r = Math.max(0, Math.round(parseInt(hex.substring(0, 2), 16) * (1 - percent / 100)));
        const g = Math.max(0, Math.round(parseInt(hex.substring(2, 4), 16) * (1 - percent / 100)));
        const b = Math.max(0, Math.round(parseInt(hex.substring(4, 6), 16) * (1 - percent / 100)));
        return '#' + [r, g, b].map(c => c.toString(16).padStart(2, '0')).join('');
    }

    /** Formatuje milisekundy na czytelny czas (np. "3.2s", "1m 15s") */
    function formatDuration(ms) {
        if (!ms || ms <= 0) return '--';
        var seconds = ms / 1000;
        if (seconds < 60) return seconds.toFixed(1) + 's';
        var minutes = Math.floor(seconds / 60);
        var secs = Math.round(seconds % 60);
        return minutes + 'm ' + secs + 's';
    }

    /** Zwraca kolor tekstu (biały/ciemny) na podstawie luminancji tła */
    function getContrastText(hex) {
        hex = hex.replace('#', '');
        if (hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
        const r = parseInt(hex.substring(0, 2), 16);
        const g = parseInt(hex.substring(2, 4), 16);
        const b = parseInt(hex.substring(4, 6), 16);
        // Wzór na postrzeganą luminancję
        const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
        return luminance > 0.55 ? '#212121' : '#ffffff';
    }

    // ==========================================
    // Strona listy popupów
    // ==========================================

    function initPopupsList() {
        const table = document.querySelector('.popups-table');
        if (!table) return;

        // Załaduj statystyki dla każdego popupa
        loadAllStats();

        // Obsługa toggle statusu
        document.querySelectorAll('.btn-toggle-status').forEach(btn => {
            btn.addEventListener('click', function() {
                const popupId = this.dataset.popupId;
                togglePopupStatus(popupId);
            });
        });

        // Obsługa usuwania
        document.querySelectorAll('.btn-delete-popup').forEach(btn => {
            btn.addEventListener('click', function() {
                const popupId = this.dataset.popupId;
                openDeleteModal(popupId);
            });
        });

        // Obsługa resetu
        document.querySelectorAll('.btn-reset-popup').forEach(btn => {
            btn.addEventListener('click', function() {
                const popupId = this.dataset.popupId;
                openResetModal(popupId);
            });
        });
    }

    function loadAllStats() {
        document.querySelectorAll('.popup-stats').forEach(el => {
            const popupId = el.dataset.popupId;
            loadPopupStats(popupId, el);
        });
    }

    function loadPopupStats(popupId, container) {
        fetch(`/admin/popups/${popupId}/stats`)
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    const s = data.stats;
                    container.querySelector('.stat-unique').textContent = s.unique_viewers;
                    container.querySelector('.stat-views').textContent = s.views;
                    container.querySelector('.stat-dismissed').textContent = s.dismissed;
                    container.querySelector('.stat-cta').textContent = s.cta_clicked;
                    container.querySelector('.stat-avg-time').textContent = formatDuration(s.avg_display_time_ms);
                }
            })
            .catch(() => {});
    }

    function togglePopupStatus(popupId) {
        fetch(`/admin/popups/${popupId}/toggle`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken(),
                'Content-Type': 'application/json'
            }
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                if (typeof window.showToast === 'function') window.showToast(data.message, 'success');
                // Przeładuj stronę, żeby odświeżyć badge i ikony
                setTimeout(() => location.reload(), 500);
            } else {
                if (typeof window.showToast === 'function') window.showToast(data.message, 'error');
            }
        })
        .catch(() => {
            if (typeof window.showToast === 'function') window.showToast('Błąd komunikacji z serwerem', 'error');
        });
    }

    // Modal usuwania
    let deletePopupId = null;

    window.openDeleteModal = function(popupId) {
        deletePopupId = popupId;
        const modal = document.getElementById('deletePopupModal');
        if (modal) modal.classList.add('active');
    };

    window.closeDeleteModal = function() {
        const modal = document.getElementById('deletePopupModal');
        if (modal) {
            modal.classList.add('closing');
            setTimeout(() => {
                modal.classList.remove('active', 'closing');
            }, 350);
        }
        deletePopupId = null;
    };

    const confirmBtn = document.getElementById('confirmDeleteBtn');
    if (confirmBtn) {
        confirmBtn.addEventListener('click', function() {
            if (!deletePopupId) return;

            fetch(`/admin/popups/${deletePopupId}/delete`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                    'Content-Type': 'application/json'
                }
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'success');
                    // Usuń wiersz z tabeli
                    const row = document.querySelector(`tr[data-popup-id="${deletePopupId}"]`);
                    if (row) row.remove();
                    closeDeleteModal();
                } else {
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'error');
                }
            })
            .catch(() => {
                if (typeof window.showToast === 'function') window.showToast('Błąd komunikacji z serwerem', 'error');
            });
        });
    }

    // Modal resetu
    let resetPopupId = null;

    window.openResetModal = function(popupId) {
        resetPopupId = popupId;
        const modal = document.getElementById('resetPopupModal');
        if (modal) modal.classList.add('active');
    };

    window.closeResetModal = function() {
        const modal = document.getElementById('resetPopupModal');
        if (modal) {
            modal.classList.add('closing');
            setTimeout(() => {
                modal.classList.remove('active', 'closing');
            }, 350);
        }
        resetPopupId = null;
    };

    const confirmResetBtn = document.getElementById('confirmResetBtn');
    if (confirmResetBtn) {
        confirmResetBtn.addEventListener('click', function() {
            if (!resetPopupId) return;

            fetch(`/admin/popups/${resetPopupId}/reset`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                    'Content-Type': 'application/json'
                }
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'success');
                    // Wyzeruj statystyki w wierszu
                    const row = document.querySelector(`tr[data-popup-id="${resetPopupId}"]`);
                    if (row) {
                        const stats = row.querySelector('.popup-stats');
                        if (stats) {
                            stats.querySelector('.stat-unique').textContent = '0';
                            stats.querySelector('.stat-views').textContent = '0';
                            stats.querySelector('.stat-dismissed').textContent = '0';
                            stats.querySelector('.stat-cta').textContent = '0';
                            stats.querySelector('.stat-avg-time').textContent = '--';
                        }
                    }
                    closeResetModal();
                } else {
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'error');
                }
            })
            .catch(() => {
                if (typeof window.showToast === 'function') window.showToast('Błąd komunikacji z serwerem', 'error');
            });
        });
    }

    // ==========================================
    // Formularz popupa - TinyMCE + Live Preview
    // ==========================================

    function initPopupForm() {
        const form = document.getElementById('popupForm');
        if (!form) return;

        // Inicjalizacja TinyMCE
        initTinyMCE();

        // Live preview - aktualizacja przy zmianie pól
        initLivePreview();

        // Synchronizacja color pickerów
        initColorPickers();
    }

    function initTinyMCE() {
        const textarea = document.getElementById('popupContent');
        if (!textarea) return;

        // Wykryj dark mode
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';

        tinymce.init({
            selector: '#popupContent',
            base_url: '/static/vendor/tinymce',
            suffix: '.min',
            height: 300,
            menubar: false,
            plugins: 'lists link image code table',
            toolbar: 'undo redo | blocks | bold italic underline | forecolor backcolor | alignleft aligncenter alignright | bullist numlist | link image | hr | code',
            skin: isDark ? 'oxide-dark' : 'oxide',
            content_css: isDark ? 'dark' : 'default',
            branding: false,
            promotion: false,
            statusbar: true,
            resize: true,
            // Upload obrazków - wybór pliku z komputera
            images_upload_url: '/admin/popups/upload-image',
            images_upload_credentials: true,
            automatic_uploads: true,
            file_picker_types: 'image',
            file_picker_callback: function(callback, value, meta) {
                if (meta.filetype === 'image') {
                    var input = document.createElement('input');
                    input.setAttribute('type', 'file');
                    input.setAttribute('accept', 'image/png,image/jpeg,image/gif,image/webp');
                    input.addEventListener('change', function() {
                        var file = this.files[0];
                        if (!file) return;

                        var formData = new FormData();
                        formData.append('file', file);

                        fetch('/admin/popups/upload-image', {
                            method: 'POST',
                            headers: { 'X-CSRFToken': getCsrfToken() },
                            body: formData
                        })
                        .then(function(r) { return r.json(); })
                        .then(function(data) {
                            if (data.location) {
                                callback(data.location, { alt: file.name });
                            } else {
                                if (typeof window.showToast === 'function') window.showToast(data.error || 'Błąd uploadu', 'error');
                            }
                        })
                        .catch(function() {
                            if (typeof window.showToast === 'function') window.showToast('Błąd komunikacji z serwerem', 'error');
                        });
                    });
                    input.click();
                }
            },
            images_upload_handler: function(blobInfo, progress) {
                return new Promise(function(resolve, reject) {
                    var formData = new FormData();
                    formData.append('file', blobInfo.blob(), blobInfo.filename());

                    var xhr = new XMLHttpRequest();
                    xhr.open('POST', '/admin/popups/upload-image');
                    xhr.setRequestHeader('X-CSRFToken', getCsrfToken());

                    xhr.upload.addEventListener('progress', function(e) {
                        if (e.lengthComputable) {
                            progress(Math.round(e.loaded / e.total * 100));
                        }
                    });

                    xhr.addEventListener('load', function() {
                        if (xhr.status === 200) {
                            var json = JSON.parse(xhr.responseText);
                            if (json.location) {
                                resolve(json.location);
                            } else {
                                reject('Upload nie zwrócił URL: ' + (json.error || ''));
                            }
                        } else {
                            reject('Błąd HTTP: ' + xhr.status);
                        }
                    });

                    xhr.addEventListener('error', function() {
                        reject('Błąd połączenia z serwerem');
                    });

                    xhr.send(formData);
                });
            },
            setup: function(editor) {
                editor.on('Change KeyUp', function() {
                    updatePreviewBody(editor.getContent());
                });
            }
        });
    }

    // Mapa rozmiarów → etykiety
    const SIZE_LABELS = { sm: '400px', md: '560px', lg: '720px' };

    function initLivePreview() {
        // Tytuł - ukryj/pokaż nagłówek w zależności od treści
        const titleInput = document.getElementById('popupTitle');
        if (titleInput) {
            titleInput.addEventListener('input', function() {
                updatePreviewHeader(this.value);
            });
            // Inicjalizacja z aktualną wartością
            updatePreviewHeader(titleInput.value);
        }

        // Rozmiar modala → przełączanie klasy w podglądzie
        document.querySelectorAll('input[name="modal_size"]').forEach(radio => {
            radio.addEventListener('change', function() {
                updatePreviewSize(this.value);
            });
        });
        // Inicjalizacja rozmiaru z aktualnego zaznaczenia
        const checkedSize = document.querySelector('input[name="modal_size"]:checked');
        if (checkedSize) updatePreviewSize(checkedSize.value);

        // CTA
        const ctaText = document.getElementById('popupCtaText');
        const ctaUrl = document.getElementById('popupCtaUrl');
        if (ctaText) {
            ctaText.addEventListener('input', updatePreviewCta);
        }
        if (ctaUrl) {
            ctaUrl.addEventListener('input', updatePreviewCta);
        }
        // Inicjalizacja CTA
        updatePreviewCta();
    }

    function updatePreviewHeader(titleValue) {
        const header = document.getElementById('previewHeader');
        const titleEl = document.getElementById('previewTitle');
        if (!header) return;

        if (titleValue && titleValue.trim()) {
            header.style.display = '';
            if (titleEl) titleEl.textContent = titleValue;
        } else {
            header.style.display = 'none';
        }
    }

    function updatePreviewSize(size) {
        const popup = document.getElementById('previewPopup');
        const label = document.getElementById('previewSizeLabel');
        if (!popup) return;

        // Zamień klasę rozmiaru
        popup.classList.remove('popup-sm', 'popup-md', 'popup-lg');
        popup.classList.add('popup-' + size);

        // Aktualizuj etykietę wymiarów
        if (label) label.textContent = SIZE_LABELS[size] || size;
    }

    function updatePreviewBody(html) {
        const el = document.getElementById('previewBody');
        if (el) {
            el.innerHTML = html || '<p>Treść popupa pojawi się tutaj...</p>';
        }
    }

    function updatePreviewCta() {
        const ctaText = document.getElementById('popupCtaText');
        const footer = document.getElementById('previewFooter');
        const ctaBtn = document.getElementById('previewCta');

        if (!footer || !ctaBtn) return;

        if (ctaText && ctaText.value.trim()) {
            footer.style.display = 'flex';
            ctaBtn.textContent = ctaText.value;

            const ctaColor = document.getElementById('popupCtaColor');
            if (ctaColor) {
                ctaBtn.style.background = ctaColor.value;
            }
        } else {
            footer.style.display = 'none';
        }
    }

    /** Aplikuje bg_color na cały popup (body + nagłówek ciemniejszy) */
    function applyPreviewBgColor(color) {
        const popup = document.getElementById('previewPopup');
        const header = document.getElementById('previewHeader');
        const body = document.getElementById('previewBody');
        const closeBtn = popup ? popup.querySelector('.popup-announcement-close-float') : null;
        const textColor = getContrastText(color);

        if (popup) {
            popup.style.background = color;
            popup.style.color = textColor;
        }
        if (body) {
            body.style.color = textColor;
        }
        if (header) {
            header.style.background = darkenColor(color, 20);
        }
        if (closeBtn) {
            closeBtn.style.color = textColor;
        }
    }

    function initColorPickers() {
        // CTA color
        syncColorPicker('popupCtaColor', 'popupCtaColorHex', function(color) {
            const ctaBtn = document.getElementById('previewCta');
            if (ctaBtn) ctaBtn.style.background = color;
        });

        // BG color → cały popup + nagłówek ciemniejszy
        syncColorPicker('popupBgColor', 'popupBgColorHex', function(color) {
            applyPreviewBgColor(color);
        });

        // Inicjalizacja kolorów podglądu
        const bgColor = document.getElementById('popupBgColor');
        if (bgColor) applyPreviewBgColor(bgColor.value);

        const ctaColor = document.getElementById('popupCtaColor');
        const ctaBtn = document.getElementById('previewCta');
        if (ctaColor && ctaBtn) {
            ctaBtn.style.background = ctaColor.value;
        }
    }

    function syncColorPicker(pickerId, hexId, onChange) {
        const picker = document.getElementById(pickerId);
        const hex = document.getElementById(hexId);
        if (!picker || !hex) return;

        picker.addEventListener('input', function() {
            hex.value = this.value;
            if (onChange) onChange(this.value);
        });

        hex.addEventListener('input', function() {
            if (/^#[0-9a-fA-F]{6}$/.test(this.value)) {
                picker.value = this.value;
                if (onChange) onChange(this.value);
            }
        });
    }

    // ==========================================
    // Inicjalizacja
    // ==========================================

    document.addEventListener('DOMContentLoaded', function() {
        initPopupsList();
        initPopupForm();
    });

})();
