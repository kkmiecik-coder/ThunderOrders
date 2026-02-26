/**
 * Collection Page - Moja Kolekcja
 * Obsługuje CRUD, przełączanie widoków (grid/list/carousel),
 * wyszukiwanie, zarządzanie zdjęciami, publiczną stronę i QR upload
 */

(function () {
    'use strict';

    // ---- CSRF Token ----
    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) return meta.getAttribute('content');
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var parts = cookies[i].trim().split('=');
            if (parts[0] === 'csrf_token') return decodeURIComponent(parts[1]);
        }
        var input = document.querySelector('input[name="csrf_token"]');
        if (input) return input.value;
        return '';
    }

    // ---- Search with debounce ----
    var searchTimeout = null;
    var searchInput = document.getElementById('collectionSearch');
    if (searchInput) {
        searchInput.addEventListener('input', function () {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(function () {
                applyFilters();
            }, 500);
        });
    }

    // ---- View switching (grid / list / carousel) ----
    window.setView = function (view) {
        var grid = document.getElementById('collectionGrid');
        var list = document.getElementById('collectionList');
        var carousel = document.getElementById('collectionCarousel');

        if (grid) grid.classList.toggle('hidden', view !== 'grid');
        if (list) list.classList.toggle('hidden', view !== 'list');
        if (carousel) carousel.classList.toggle('hidden', view !== 'carousel');

        // Aktywacja przycisku
        document.querySelectorAll('.view-btn').forEach(function (btn) {
            btn.classList.remove('active');
        });
        if (event && event.currentTarget) {
            event.currentTarget.classList.add('active');
        }

        // Inicjalizacja karuzeli przy pierwszym przełączeniu
        if (view === 'carousel') {
            initCarousel();
        }

        // Aktualizacja URL bez przeładowania
        var url = new URL(window.location);
        url.searchParams.set('view', view);
        history.replaceState(null, '', url);
    };

    // ---- Sort ----
    window.applySort = function () {
        applyFilters();
    };

    // ---- Clear search ----
    window.clearSearch = function () {
        if (searchInput) searchInput.value = '';
        applyFilters();
    };

    // ---- Apply filters (search + sort) ----
    function applyFilters() {
        var url = new URL(window.location);
        var search = searchInput ? searchInput.value.trim() : '';
        var sort = document.getElementById('collectionSort');
        var sortVal = sort ? sort.value : 'newest';

        if (search) {
            url.searchParams.set('search', search);
        } else {
            url.searchParams.delete('search');
        }
        url.searchParams.set('sort', sortVal);
        url.searchParams.delete('page');

        window.location.href = url.toString();
    }

    // ================================================================
    // KARUZELA 3D
    // ================================================================

    var carouselSlides = [];
    var carouselIndex = 0;
    var carouselInitialized = false;

    function initCarousel() {
        if (carouselInitialized) return;
        carouselSlides = document.querySelectorAll('#collectionCarousel .carousel-slide');
        if (carouselSlides.length === 0) return;

        carouselInitialized = true;
        carouselIndex = 0;
        updateCarouselPositions();

        // Strzałki nawigacji
        var prevBtn = document.getElementById('carouselPrev');
        var nextBtn = document.getElementById('carouselNext');

        if (prevBtn) {
            prevBtn.addEventListener('click', function () {
                carouselIndex = (carouselIndex - 1 + carouselSlides.length) % carouselSlides.length;
                updateCarouselPositions();
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener('click', function () {
                carouselIndex = (carouselIndex + 1) % carouselSlides.length;
                updateCarouselPositions();
            });
        }

        // Touch swipe
        var container = document.getElementById('collectionCarousel');
        var touchStartX = 0;
        if (container) {
            container.addEventListener('touchstart', function (e) {
                touchStartX = e.changedTouches[0].clientX;
            }, { passive: true });

            container.addEventListener('touchend', function (e) {
                var deltaX = e.changedTouches[0].clientX - touchStartX;
                if (Math.abs(deltaX) > 50) {
                    if (deltaX < 0) {
                        carouselIndex = (carouselIndex + 1) % carouselSlides.length;
                    } else {
                        carouselIndex = (carouselIndex - 1 + carouselSlides.length) % carouselSlides.length;
                    }
                    updateCarouselPositions();
                }
            }, { passive: true });
        }
    }

    function updateCarouselPositions() {
        var total = carouselSlides.length;
        var positions = ['active', 'prev', 'next', 'far-prev', 'far-next'];

        carouselSlides.forEach(function (slide, index) {
            positions.forEach(function (cls) { slide.classList.remove(cls); });
            slide.style.opacity = '';

            var diff = index - carouselIndex;
            if (diff > total / 2) diff -= total;
            if (diff < -total / 2) diff += total;

            if (diff === 0) slide.classList.add('active');
            else if (diff === -1) slide.classList.add('prev');
            else if (diff === 1) slide.classList.add('next');
            else if (diff === -2) slide.classList.add('far-prev');
            else if (diff === 2) slide.classList.add('far-next');
            else slide.style.opacity = '0';
        });
    }

    // Inicjalizacja karuzeli jeśli domyślny widok to carousel
    var urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('view') === 'carousel') {
        initCarousel();
    }

    // ================================================================
    // ADD MODAL
    // ================================================================

    window.openAddModal = function () {
        var modal = document.getElementById('addCollectionModal');
        if (modal) {
            document.getElementById('addCollectionForm').reset();
            document.getElementById('addImagePreview').innerHTML = '';
            // Resetuj sekcję QR
            resetQrSection('add');
            modal.classList.add('active');
        }
    };

    window.closeAddModal = function () {
        var modal = document.getElementById('addCollectionModal');
        if (modal) modal.classList.remove('active');
        stopQrPolling('add');
    };

    window.submitAddForm = function (e) {
        e.preventDefault();

        var form = document.getElementById('addCollectionForm');
        var btn = document.getElementById('addSubmitBtn');
        var formData = new FormData(form);

        btn.disabled = true;
        btn.textContent = 'Dodawanie...';

        fetch('/client/collection/add', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken()
            },
            body: formData
        })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                if (data.success) {
                    if (window.Toast) window.Toast.show(data.message, 'success');
                    closeAddModal();
                    window.location.reload();
                } else {
                    if (window.Toast) window.Toast.show(data.message, 'error');
                }
            })
            .catch(function () {
                if (window.Toast) window.Toast.show('Wystąpił błąd', 'error');
            })
            .finally(function () {
                btn.disabled = false;
                btn.textContent = 'Dodaj do kolekcji';
            });
    };

    // ---- Image preview for add modal ----
    window.handleImagePreview = function (input, previewContainerId) {
        var container = document.getElementById(previewContainerId);
        container.innerHTML = '';

        var files = Array.from(input.files).slice(0, 3);

        if (input.files.length > 3) {
            if (window.Toast) window.Toast.show('Maksymalnie 3 zdjęcia', 'warning');
            var dt = new DataTransfer();
            for (var i = 0; i < 3; i++) {
                dt.items.add(input.files[i]);
            }
            input.files = dt.files;
            files = Array.from(input.files);
        }

        files.forEach(function (file, idx) {
            var reader = new FileReader();
            reader.onload = function (e) {
                var div = document.createElement('div');
                div.className = 'preview-item';
                div.innerHTML = '<img src="' + e.target.result + '" alt="Preview">' +
                    '<button type="button" class="preview-remove" onclick="removePreviewImage(' + idx + ', \'' + previewContainerId + '\', \'' + input.id + '\')">&times;</button>';
                container.appendChild(div);
            };
            reader.readAsDataURL(file);
        });
    };

    window.removePreviewImage = function (index, previewContainerId, inputId) {
        var input = document.getElementById(inputId);
        var dt = new DataTransfer();
        var files = Array.from(input.files);
        files.splice(index, 1);
        files.forEach(function (f) { dt.items.add(f); });
        input.files = dt.files;
        handleImagePreview(input, previewContainerId);
    };

    // ================================================================
    // EDIT MODAL
    // ================================================================

    var currentEditItem = null;

    window.openEditModal = function (itemId) {
        var modal = document.getElementById('editCollectionModal');
        if (!modal) return;

        // Resetuj QR sekcję
        resetQrSection('edit');

        fetch('/client/collection/' + itemId + '/edit', {
            method: 'GET',
            headers: { 'Accept': 'application/json' }
        })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                if (!data.success) {
                    if (window.Toast) window.Toast.show(data.message || 'Błąd', 'error');
                    return;
                }

                currentEditItem = data.item;
                document.getElementById('editItemId').value = data.item.id;
                document.getElementById('editName').value = data.item.name;
                document.getElementById('editPrice').value = data.item.market_price || '';
                document.getElementById('editNotes').value = data.item.notes || '';

                renderEditImages(data.item.images, data.item.id, data.item.can_add_image);

                modal.classList.add('active');
            })
            .catch(function () {
                if (window.Toast) window.Toast.show('Błąd ładowania danych', 'error');
            });
    };

    function renderEditImages(images, itemId, canAdd) {
        var container = document.getElementById('editExistingImages');
        var addWrapper = document.getElementById('editAddImageWrapper');
        container.innerHTML = '';

        if (images) {
            images.forEach(function (img) {
                var div = document.createElement('div');
                div.className = 'existing-image-item' + (img.is_primary ? ' primary' : '');
                div.innerHTML = '<img src="' + img.url + '" alt="Image">' +
                    (img.is_primary ? '<span class="primary-indicator">Główne</span>' : '') +
                    '<div class="image-actions">' +
                    (!img.is_primary ? '<button type="button" class="btn-set-primary" onclick="setEditPrimary(' + itemId + ',' + img.id + ')" title="Ustaw jako główne">&#9733;</button>' : '') +
                    '<button type="button" class="btn-remove-image" onclick="deleteEditImage(' + itemId + ',' + img.id + ')" title="Usuń">&times;</button>' +
                    '</div>';
                container.appendChild(div);
            });
        }

        if (addWrapper) {
            addWrapper.style.display = canAdd ? 'flex' : 'none';
        }
    }

    window.closeEditModal = function () {
        var modal = document.getElementById('editCollectionModal');
        if (modal) modal.classList.remove('active');
        currentEditItem = null;
        stopQrPolling('edit');
    };

    window.submitEditForm = function (e) {
        e.preventDefault();

        var itemId = document.getElementById('editItemId').value;
        var btn = document.getElementById('editSubmitBtn');
        var formData = new FormData(document.getElementById('editCollectionForm'));

        btn.disabled = true;
        btn.textContent = 'Zapisywanie...';

        fetch('/client/collection/' + itemId + '/edit', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken()
            },
            body: formData
        })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                if (data.success) {
                    if (window.Toast) window.Toast.show(data.message, 'success');
                    closeEditModal();
                    window.location.reload();
                } else {
                    if (window.Toast) window.Toast.show(data.message, 'error');
                }
            })
            .catch(function () {
                if (window.Toast) window.Toast.show('Wystąpił błąd', 'error');
            })
            .finally(function () {
                btn.disabled = false;
                btn.textContent = 'Zapisz zmiany';
            });
    };

    // ---- Edit modal: Upload additional image ----
    window.uploadEditImage = function (input) {
        if (!input.files.length || !currentEditItem) return;

        var itemId = currentEditItem.id;
        var formData = new FormData();
        formData.append('image', input.files[0]);

        fetch('/client/collection/' + itemId + '/images', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken()
            },
            body: formData
        })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                if (data.success) {
                    if (window.Toast) window.Toast.show(data.message, 'success');
                    openEditModal(itemId);
                } else {
                    if (window.Toast) window.Toast.show(data.message, 'error');
                }
            })
            .catch(function () {
                if (window.Toast) window.Toast.show('Błąd uploadu', 'error');
            });

        input.value = '';
    };

    // ---- Edit modal: Delete image ----
    window.deleteEditImage = function (itemId, imageId) {
        fetch('/client/collection/' + itemId + '/images/' + imageId, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': getCsrfToken(),
                'Content-Type': 'application/json'
            }
        })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                if (data.success) {
                    if (window.Toast) window.Toast.show(data.message, 'success');
                    openEditModal(itemId);
                } else {
                    if (window.Toast) window.Toast.show(data.message, 'error');
                }
            })
            .catch(function () {
                if (window.Toast) window.Toast.show('Błąd', 'error');
            });
    };

    // ---- Edit modal: Set primary image ----
    window.setEditPrimary = function (itemId, imageId) {
        fetch('/client/collection/' + itemId + '/images/' + imageId + '/primary', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken(),
                'Content-Type': 'application/json'
            }
        })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                if (data.success) {
                    if (window.Toast) window.Toast.show(data.message, 'success');
                    openEditModal(itemId);
                } else {
                    if (window.Toast) window.Toast.show(data.message, 'error');
                }
            })
            .catch(function () {
                if (window.Toast) window.Toast.show('Błąd', 'error');
            });
    };

    // ================================================================
    // DELETE MODAL
    // ================================================================

    window.openDeleteModal = function (itemId, itemName) {
        var modal = document.getElementById('deleteCollectionModal');
        if (modal) {
            document.getElementById('deleteItemId').value = itemId;
            document.getElementById('deleteItemName').textContent = itemName;
            modal.classList.add('active');
        }
    };

    window.closeDeleteModal = function () {
        var modal = document.getElementById('deleteCollectionModal');
        if (modal) modal.classList.remove('active');
    };

    window.confirmDelete = function () {
        var itemId = document.getElementById('deleteItemId').value;
        var btn = document.getElementById('deleteConfirmBtn');

        btn.disabled = true;
        btn.textContent = 'Usuwanie...';

        fetch('/client/collection/' + itemId + '/delete', {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': getCsrfToken(),
                'Content-Type': 'application/json'
            }
        })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                if (data.success) {
                    if (window.Toast) window.Toast.show(data.message, 'success');
                    closeDeleteModal();
                    var elements = document.querySelectorAll('[data-item-id="' + itemId + '"]');
                    elements.forEach(function (el) { el.remove(); });
                    var remaining = document.querySelectorAll('.collection-card, .collection-row');
                    if (remaining.length === 0) {
                        window.location.reload();
                    }
                } else {
                    if (window.Toast) window.Toast.show(data.message, 'error');
                }
            })
            .catch(function () {
                if (window.Toast) window.Toast.show('Wystąpił błąd', 'error');
            })
            .finally(function () {
                btn.disabled = false;
                btn.textContent = 'Usuń';
            });
    };

    // ================================================================
    // PUBLIC CONFIG MODAL
    // ================================================================

    window.openPublicConfigModal = function () {
        var modal = document.getElementById('publicConfigModal');
        if (!modal) return;
        modal.classList.add('active');
        loadPublicConfig();
    };

    window.closePublicConfigModal = function () {
        var modal = document.getElementById('publicConfigModal');
        if (modal) modal.classList.remove('active');
    };

    function loadPublicConfig() {
        fetch('/client/collection/public/config', {
            headers: { 'Accept': 'application/json' }
        })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                var createSection = document.getElementById('publicConfigCreate');
                var settingsSection = document.getElementById('publicConfigSettings');
                var urlSection = document.getElementById('publicUrlSection');

                if (!data.exists) {
                    // Brak konfiguracji - pokaż przycisk tworzenia
                    createSection.style.display = '';
                    settingsSection.style.display = 'none';
                    urlSection.style.display = 'none';
                } else {
                    // Konfiguracja istnieje - pokaż ustawienia
                    createSection.style.display = 'none';
                    settingsSection.style.display = '';
                    urlSection.style.display = '';

                    // URL
                    var fullUrl = window.location.origin + data.config.url;
                    document.getElementById('publicUrlInput').value = fullUrl;

                    // Checkboxy
                    document.getElementById('configShowPrices').checked = data.config.show_prices;
                    document.getElementById('configIsActive').checked = data.config.is_active;

                    // Lista itemów
                    renderConfigItems(data.items);
                }
            })
            .catch(function () {
                if (window.Toast) window.Toast.show('Błąd ładowania konfiguracji', 'error');
            });
    }

    function renderConfigItems(items) {
        var list = document.getElementById('configItemsList');
        var selectAll = document.getElementById('configSelectAll');
        list.innerHTML = '';

        if (!items || items.length === 0) {
            list.innerHTML = '<p style="padding: 12px; text-align: center; color: var(--text-tertiary);">Brak przedmiotów w kolekcji</p>';
            return;
        }

        var allPublic = true;
        items.forEach(function (item) {
            if (!item.is_public) allPublic = false;

            var row = document.createElement('label');
            row.className = 'config-item-row';
            row.innerHTML =
                '<input type="checkbox" ' + (item.is_public ? 'checked' : '') +
                ' onchange="toggleItemPublic(' + item.id + ', this.checked)">' +
                (item.image_url
                    ? '<img src="' + item.image_url + '" class="config-item-thumb" alt="">'
                    : '<div class="config-item-thumb"></div>') +
                '<span class="config-item-name">' + escapeHtml(item.name) + '</span>';
            list.appendChild(row);
        });

        if (selectAll) selectAll.checked = allPublic;
    }

    window.createPublicConfig = function () {
        fetch('/client/collection/public/create', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken(),
                'Content-Type': 'application/json'
            }
        })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                if (data.success) {
                    if (window.Toast) window.Toast.show(data.message, 'success');
                    loadPublicConfig();
                } else {
                    if (window.Toast) window.Toast.show(data.message, 'error');
                }
            })
            .catch(function () {
                if (window.Toast) window.Toast.show('Wystąpił błąd', 'error');
            });
    };

    window.updatePublicConfig = function () {
        var showPrices = document.getElementById('configShowPrices').checked;
        var isActive = document.getElementById('configIsActive').checked;

        fetch('/client/collection/public/config', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken(),
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                show_prices: showPrices,
                is_active: isActive
            })
        })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                if (data.success) {
                    if (window.Toast) window.Toast.show(data.message, 'success');
                } else {
                    if (window.Toast) window.Toast.show(data.message, 'error');
                }
            })
            .catch(function () {
                if (window.Toast) window.Toast.show('Wystąpił błąd', 'error');
            });
    };

    window.toggleItemPublic = function (itemId, isPublic) {
        fetch('/client/collection/' + itemId + '/toggle-public', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken(),
                'Content-Type': 'application/json'
            }
        })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                if (!data.success) {
                    if (window.Toast) window.Toast.show(data.message, 'error');
                }
                // Aktualizuj "Zaznacz wszystkie"
                updateSelectAllState();
            })
            .catch(function () {
                if (window.Toast) window.Toast.show('Wystąpił błąd', 'error');
            });
    };

    window.toggleAllPublicItems = function (isPublic) {
        fetch('/client/collection/public/toggle-all', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken(),
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ is_public: isPublic })
        })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                if (data.success) {
                    // Zaznacz/odznacz wszystkie checkboxy
                    var checkboxes = document.querySelectorAll('#configItemsList input[type="checkbox"]');
                    checkboxes.forEach(function (cb) { cb.checked = isPublic; });
                    if (window.Toast) window.Toast.show(data.message, 'success');
                } else {
                    if (window.Toast) window.Toast.show(data.message, 'error');
                }
            })
            .catch(function () {
                if (window.Toast) window.Toast.show('Wystąpił błąd', 'error');
            });
    };

    function updateSelectAllState() {
        var checkboxes = document.querySelectorAll('#configItemsList input[type="checkbox"]');
        var selectAll = document.getElementById('configSelectAll');
        if (!selectAll || checkboxes.length === 0) return;

        var allChecked = true;
        checkboxes.forEach(function (cb) {
            if (!cb.checked) allChecked = false;
        });
        selectAll.checked = allChecked;
    }

    window.copyPublicUrl = function () {
        var input = document.getElementById('publicUrlInput');
        if (!input) return;

        navigator.clipboard.writeText(input.value).then(function () {
            if (window.Toast) window.Toast.show('Link skopiowany', 'success');
        }).catch(function () {
            // Fallback
            input.select();
            document.execCommand('copy');
            if (window.Toast) window.Toast.show('Link skopiowany', 'success');
        });
    };

    // ================================================================
    // QR UPLOAD
    // ================================================================

    var qrPollingIntervals = {};

    window.startQrSession = function (context) {
        var data = {};

        // Jeśli edycja - przekaż item_id
        if (context === 'edit' && currentEditItem) {
            data.item_id = currentEditItem.id;
        }

        fetch('/client/collection/qr-session', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken(),
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        })
            .then(function (resp) { return resp.json(); })
            .then(function (result) {
                if (!result.success) {
                    if (window.Toast) window.Toast.show(result.message, 'error');
                    return;
                }

                // Pokaż QR code
                var qrDisplay = document.getElementById(context + 'QrDisplay');
                var qrImage = document.getElementById(context + 'QrImage');

                if (qrDisplay) qrDisplay.style.display = '';
                if (qrImage) qrImage.src = result.qr_data_uri;

                // Zapisz session token (dla add modal - do formularza)
                if (context === 'add') {
                    var tokenInput = document.getElementById('addQrSessionToken');
                    if (tokenInput) tokenInput.value = result.session_token;
                }

                // Startuj polling co 3 sekundy
                startQrPolling(context, result.session_token);
            })
            .catch(function () {
                if (window.Toast) window.Toast.show('Błąd tworzenia sesji QR', 'error');
            });
    };

    function startQrPolling(context, sessionToken) {
        stopQrPolling(context);

        qrPollingIntervals[context] = setInterval(function () {
            fetch('/client/collection/qr-session/' + sessionToken + '/status')
                .then(function (resp) { return resp.json(); })
                .then(function (data) {
                    if (!data.success) {
                        stopQrPolling(context);
                        return;
                    }

                    var statusEl = document.getElementById(context + 'QrStatus');

                    if (data.status === 'uploaded') {
                        stopQrPolling(context);

                        if (context === 'add') {
                            // Schowaj QR, pokaż podgląd
                            var qrDisplay = document.getElementById('addQrDisplay');
                            var uploaded = document.getElementById('addQrUploaded');
                            var uploadedImg = document.getElementById('addQrUploadedImage');

                            if (qrDisplay) qrDisplay.style.display = 'none';
                            if (uploaded) uploaded.style.display = '';
                            if (uploadedImg && data.image_url) uploadedImg.src = data.image_url;
                        } else if (context === 'edit') {
                            // Odśwież modal edycji - nowe zdjęcie dodane
                            if (statusEl) {
                                statusEl.textContent = 'Zdjęcie dodane!';
                                statusEl.className = 'qr-status uploaded';
                            }
                            if (window.Toast) window.Toast.show('Zdjęcie dodane z telefonu', 'success');
                            // Odśwież dane edycji po 1s
                            setTimeout(function () {
                                if (currentEditItem) openEditModal(currentEditItem.id);
                            }, 1000);
                        }
                    } else if (data.status === 'expired') {
                        stopQrPolling(context);
                        if (statusEl) {
                            statusEl.textContent = 'Sesja wygasła';
                            statusEl.className = 'qr-status expired';
                        }
                    }
                })
                .catch(function () {
                    // Cichy błąd - polling kontynuuje
                });
        }, 3000);
    }

    function stopQrPolling(context) {
        if (qrPollingIntervals[context]) {
            clearInterval(qrPollingIntervals[context]);
            delete qrPollingIntervals[context];
        }
    }

    function resetQrSection(context) {
        stopQrPolling(context);

        var qrDisplay = document.getElementById(context + 'QrDisplay');
        if (qrDisplay) qrDisplay.style.display = 'none';

        var statusEl = document.getElementById(context + 'QrStatus');
        if (statusEl) {
            statusEl.textContent = 'Oczekiwanie na upload...';
            statusEl.className = 'qr-status';
        }

        if (context === 'add') {
            var uploaded = document.getElementById('addQrUploaded');
            if (uploaded) uploaded.style.display = 'none';
            var tokenInput = document.getElementById('addQrSessionToken');
            if (tokenInput) tokenInput.value = '';
        }
    }

    // ================================================================
    // HELPERS
    // ================================================================

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ---- Close modals on overlay click ----
    document.querySelectorAll('.modal-overlay').forEach(function (overlay) {
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) {
                overlay.classList.remove('active');
                // Zatrzymaj polling przy zamknięciu
                stopQrPolling('add');
                stopQrPolling('edit');
            }
        });
    });

    // ---- Close modals on Escape key ----
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal-overlay.active').forEach(function (modal) {
                modal.classList.remove('active');
            });
            stopQrPolling('add');
            stopQrPolling('edit');
        }
    });

})();
