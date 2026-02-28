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
    // KARUZELA - dynamiczny rozmiar + fade
    // ================================================================

    var carouselSlides = [];
    var carouselIndex = 0;
    var carouselInitialized = false;
    var carouselResizeTimer = null;

    /**
     * Oblicza dynamiczny layout karuzeli na podstawie dostępnego miejsca.
     * Ustawia CSS custom properties na .carousel-track.
     */
    function computeCarouselLayout() {
        var track = document.querySelector('#collectionCarousel .carousel-track');
        var container = document.getElementById('collectionCarousel');
        if (!track || !container) return;

        var containerWidth = container.clientWidth;
        var gap = 12;

        // Szerokość karty na podstawie dostępnej szerokości (5 kart widocznych)
        var widthBased = (containerWidth - 4 * gap) / 4.1;

        // Rzeczywista pozycja karuzeli na stronie (pod nagłówkiem, statystykami, toolbarem)
        var containerTop = container.getBoundingClientRect().top + window.scrollY;
        // Dostępna wysokość = viewport - pozycja karuzeli - margines dolny (np. padding strony)
        var availableHeight = window.innerHeight - containerTop + window.scrollY - 16;
        // Karuzela ma padding: 20px góra + 70px dół (przyciski), odejmij to
        var usableHeight = availableHeight - 90;
        // Karta ma proporcję 4:3 + ~55px na tekst pod obrazkiem
        // cardHeight = cardWidth * (4/3) + 55, więc cardWidth = (usableHeight - 55) * 0.75
        var heightBased = (usableHeight - 55) * 0.75;

        // Wybierz mniejszą z dwóch wartości, ogranicz zakresem 160-380px
        var cardWidth = Math.max(160, Math.min(380, Math.round(Math.min(widthBased, heightBased))));

        // Oblicz offsety pozycji
        var prevOffset = Math.round(cardWidth * 0.925 + gap);
        var farOffset = Math.round(prevOffset + cardWidth * 0.775 + gap);

        // Wysokość tracka: karta (proporcja 4:3 + tekst)
        var trackHeight = Math.round(cardWidth * (4 / 3) + 55);

        // Ustaw CSS custom properties
        track.style.setProperty('--slide-width', cardWidth + 'px');
        track.style.setProperty('--prev-offset', prevOffset + 'px');
        track.style.setProperty('--prev-offset-neg', '-' + prevOffset + 'px');
        track.style.setProperty('--far-offset', farOffset + 'px');
        track.style.setProperty('--far-offset-neg', '-' + farOffset + 'px');
        track.style.setProperty('--track-height', trackHeight + 'px');
    }

    function initCarousel() {
        if (carouselInitialized) return;
        carouselSlides = document.querySelectorAll('#collectionCarousel .carousel-slide');
        if (carouselSlides.length === 0) return;

        carouselInitialized = true;
        carouselIndex = 0;

        computeCarouselLayout();
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

        // Przelicz layout przy zmianie rozmiaru okna (debounce)
        window.addEventListener('resize', function () {
            clearTimeout(carouselResizeTimer);
            carouselResizeTimer = setTimeout(function () {
                computeCarouselLayout();
            }, 150);
        });
    }

    /**
     * Pomocnicza - ustawia klasę pozycji na slajdzie
     */
    function applyPos(slide, cls) {
        ['active', 'prev', 'next', 'far-prev', 'far-next'].forEach(function (c) {
            slide.classList.remove(c);
        });
        if (cls) slide.classList.add(cls);
    }

    /**
     * Aktualizuje pozycje slajdów z logiką fade dla far slides.
     * 4 przypadki:
     *   1) Appearing  (hidden → visible): teleport bez animacji, potem fade in
     *   2) Disappearing (visible → hidden): fade out 0.4s, potem ukryj
     *   3) Moving (visible → visible): normalna tranzycja CSS
     *   4) Hidden → hidden: natychmiast, bez animacji
     */
    function updateCarouselPositions() {
        var total = carouselSlides.length;
        if (total === 0) return;

        var posClasses = ['active', 'prev', 'next', 'far-prev', 'far-next'];
        var posMap = { 0: 'active', '-1': 'prev', 1: 'next', '-2': 'far-prev', 2: 'far-next' };

        carouselSlides.forEach(function (slide, index) {
            // Anuluj wcześniejszy timer fade jeśli istnieje
            if (slide._fadeTimer) {
                clearTimeout(slide._fadeTimer);
                slide._fadeTimer = null;
            }

            var wasVisible = posClasses.some(function (cls) { return slide.classList.contains(cls); });

            var diff = index - carouselIndex;
            if (diff > total / 2) diff -= total;
            if (diff < -total / 2) diff += total;

            var willBeVisible = (diff >= -2 && diff <= 2);
            var targetCls = posMap[diff] || null;

            if (!wasVisible && willBeVisible) {
                // --- CASE 1: Appearing → teleport + fade in ---
                slide.classList.add('no-transition');
                applyPos(slide, targetCls);
                slide.style.opacity = '0';
                void slide.offsetHeight; // force reflow
                slide.classList.remove('no-transition');
                // Uruchom fade in
                slide.style.opacity = '';

            } else if (wasVisible && !willBeVisible) {
                // --- CASE 2: Disappearing → fade out, potem ukryj ---
                slide.style.opacity = '0';
                slide._fadeTimer = setTimeout(function () {
                    slide.classList.add('no-transition');
                    applyPos(slide, null);
                    void slide.offsetHeight;
                    slide.classList.remove('no-transition');
                    slide._fadeTimer = null;
                }, 400);

            } else if (wasVisible && willBeVisible) {
                // --- CASE 3: Moving → normalna tranzycja CSS ---
                applyPos(slide, targetCls);
                slide.style.opacity = '';

            } else {
                // --- CASE 4: Hidden → hidden → natychmiast ---
                slide.classList.add('no-transition');
                applyPos(slide, null);
                slide.style.opacity = '0';
                void slide.offsetHeight;
                slide.classList.remove('no-transition');
            }
        });
    }

    // Inicjalizacja karuzeli jeśli domyślny widok to carousel
    var urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('view') === 'carousel') {
        initCarousel();
    }

    // ================================================================
    // USTAWIENIA KOLEKCJI (localStorage)
    // ================================================================

    var SETTINGS_KEY = 'collection_settings';

    /** Domyślne ustawienia */
    var defaultSettings = {
        stats: { items_count: true, total_value: true },
        list_columns: { image: true, source: true, price: true, date: true },
        grid_columns: 0 // 0 = auto (responsive CSS)
    };

    /** Odczytaj ustawienia z localStorage */
    function loadSettings() {
        try {
            var raw = localStorage.getItem(SETTINGS_KEY);
            if (raw) {
                var parsed = JSON.parse(raw);
                // Scal z domyślnymi na wypadek brakujących kluczy
                return {
                    stats: Object.assign({}, defaultSettings.stats, parsed.stats),
                    list_columns: Object.assign({}, defaultSettings.list_columns, parsed.list_columns),
                    grid_columns: parsed.grid_columns !== undefined ? parsed.grid_columns : 0
                };
            }
        } catch (e) { /* ignoruj błędy parsowania */ }
        return JSON.parse(JSON.stringify(defaultSettings));
    }

    /** Zapisz ustawienia do localStorage */
    function saveSettings(settings) {
        localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    }

    /** Zastosuj ustawienia na stronie */
    function applySettings(settings) {
        // --- Statystyki ---
        var statItems = document.querySelector('[data-stat="items_count"]');
        var statValue = document.querySelector('[data-stat="total_value"]');
        if (statItems) statItems.style.display = settings.stats.items_count ? '' : 'none';
        if (statValue) statValue.style.display = settings.stats.total_value ? '' : 'none';

        // Ukryj cały kontener metryk jeśli obie wyłączone
        var metricsContainer = document.querySelector('.collection-metrics');
        if (metricsContainer) {
            var anyStatVisible = settings.stats.items_count || settings.stats.total_value;
            metricsContainer.style.display = anyStatVisible ? '' : 'none';
        }

        // --- Kolumny listy ---
        var colMap = {
            image: '.col-image',
            source: '.col-source',
            price: '.col-price',
            date: '.col-date'
        };
        Object.keys(colMap).forEach(function (key) {
            var selector = colMap[key];
            var visible = settings.list_columns[key];
            document.querySelectorAll(selector).forEach(function (el) {
                el.style.display = visible ? '' : 'none';
            });
        });

        // Przelicz grid-template-columns listy
        rebuildListGrid(settings.list_columns);

        // --- Kolumny siatki ---
        var grid = document.getElementById('collectionGrid');
        if (grid) {
            if (settings.grid_columns > 0) {
                grid.style.gridTemplateColumns = 'repeat(' + settings.grid_columns + ', 1fr)';
            } else {
                grid.style.gridTemplateColumns = '';
            }
        }
    }

    /** Przelicza grid-template-columns dla list-header i collection-row */
    function rebuildListGrid(cols) {
        // Bazowa konfiguracja: image(48px) name(1fr) source(100px) price(100px) date(100px) actions(80px)
        var parts = [];
        if (cols.image) parts.push('48px');
        parts.push('minmax(120px, 1fr)'); // nazwa - zawsze
        if (cols.source) parts.push('100px');
        if (cols.price) parts.push('100px');
        if (cols.date) parts.push('100px');
        parts.push('80px'); // akcje - zawsze

        var tpl = parts.join(' ');

        document.querySelectorAll('.list-header, .collection-row').forEach(function (el) {
            el.style.gridTemplateColumns = tpl;
        });
    }

    /** Zsynchronizuj ustawienia → kontrolki modala */
    function settingsToModal(settings) {
        var el;
        el = document.getElementById('settingStatItems');
        if (el) el.checked = settings.stats.items_count;
        el = document.getElementById('settingStatValue');
        if (el) el.checked = settings.stats.total_value;

        el = document.getElementById('settingColImage');
        if (el) el.checked = settings.list_columns.image;
        el = document.getElementById('settingColSource');
        if (el) el.checked = settings.list_columns.source;
        el = document.getElementById('settingColPrice');
        if (el) el.checked = settings.list_columns.price;
        el = document.getElementById('settingColDate');
        if (el) el.checked = settings.list_columns.date;

        el = document.getElementById('settingGridCols');
        if (el) el.value = String(settings.grid_columns);
    }

    /** Odczytaj stan kontrolek modala → obiekt ustawień */
    function modalToSettings() {
        return {
            stats: {
                items_count: !!document.getElementById('settingStatItems').checked,
                total_value: !!document.getElementById('settingStatValue').checked
            },
            list_columns: {
                image: !!document.getElementById('settingColImage').checked,
                source: !!document.getElementById('settingColSource').checked,
                price: !!document.getElementById('settingColPrice').checked,
                date: !!document.getElementById('settingColDate').checked
            },
            grid_columns: parseInt(document.getElementById('settingGridCols').value, 10) || 0
        };
    }

    /** Otwórz modal ustawień */
    window.openSettingsModal = function () {
        var modal = document.getElementById('collectionSettingsModal');
        if (!modal) return;
        settingsToModal(loadSettings());
        modal.classList.add('active');
    };

    /** Zamknij modal ustawień */
    window.closeSettingsModal = function () {
        var modal = document.getElementById('collectionSettingsModal');
        if (!modal) return;
        modal.classList.remove('active');
    };

    // Nasłuchuj zmian w kontrolkach modala → natychmiastowy zapis i zastosowanie
    (function () {
        var ids = [
            'settingStatItems', 'settingStatValue',
            'settingColImage', 'settingColSource', 'settingColPrice', 'settingColDate',
            'settingGridCols'
        ];
        ids.forEach(function (id) {
            var el = document.getElementById(id);
            if (!el) return;
            el.addEventListener('change', function () {
                var settings = modalToSettings();
                saveSettings(settings);
                applySettings(settings);
            });
        });
    })();

    // Zastosuj ustawienia przy załadowaniu strony
    applySettings(loadSettings());

    // ================================================================
    // ADD MODAL
    // ================================================================

    window.openAddModal = function () {
        var modal = document.getElementById('addCollectionModal');
        if (modal) {
            document.getElementById('addCollectionForm').reset();
            // Reset photos area — show empty state
            var photosArea = document.getElementById('addUploadPhotos');
            if (photosArea) {
                // Remove thumbs, keep empty state
                photosArea.querySelectorAll('.upload-thumb').forEach(function (t) { t.remove(); });
            }
            var emptyState = document.getElementById('addEmptyState');
            if (emptyState) emptyState.style.display = '';
            var counter = document.getElementById('addUploadCounter');
            if (counter) counter.textContent = '';
            // Show actions column
            var actions = document.getElementById('addUploadActions');
            if (actions) actions.style.display = '';
            // Reset QR inline
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
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'success');
                    closeAddModal();
                    window.location.reload();
                } else {
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'error');
                }
            })
            .catch(function () {
                if (typeof window.showToast === 'function') window.showToast('Wystąpił błąd', 'error');
            })
            .finally(function () {
                btn.disabled = false;
                btn.textContent = 'Dodaj do kolekcji';
            });
    };

    // ---- Image preview for add modal (renders into upload-row-photos) ----
    window.handleImagePreview = function (input) {
        var photosArea = document.getElementById('addUploadPhotos');
        var emptyState = document.getElementById('addEmptyState');
        var counter = document.getElementById('addUploadCounter');
        var actionsCol = document.getElementById('addUploadActions');
        if (!photosArea) return;

        // Remove old thumbs
        photosArea.querySelectorAll('.upload-thumb').forEach(function (t) { t.remove(); });

        var files = Array.from(input.files).slice(0, 3);

        if (input.files.length > 3) {
            if (typeof window.showToast === 'function') window.showToast('Maksymalnie 3 zdjęcia', 'warning');
            var dt = new DataTransfer();
            for (var i = 0; i < 3; i++) {
                dt.items.add(input.files[i]);
            }
            input.files = dt.files;
            files = Array.from(input.files);
        }

        // Hide/show empty state
        if (emptyState) emptyState.style.display = files.length > 0 ? 'none' : '';

        files.forEach(function (file, idx) {
            var reader = new FileReader();
            reader.onload = function (e) {
                var div = document.createElement('div');
                div.className = 'upload-thumb';
                div.innerHTML = '<img src="' + e.target.result + '" alt="Preview">' +
                    '<button type="button" class="upload-thumb-remove" onclick="removePreviewImage(' + idx + ')">&times;</button>';
                photosArea.appendChild(div);
            };
            reader.readAsDataURL(file);
        });

        // Update counter
        if (counter) {
            counter.textContent = files.length > 0 ? files.length + '/3' : '';
        }

        // Hide actions column if at limit
        if (actionsCol) {
            actionsCol.style.display = files.length >= 3 ? 'none' : '';
        }
    };

    window.removePreviewImage = function (index) {
        var input = document.getElementById('addImageInput');
        var dt = new DataTransfer();
        var files = Array.from(input.files);
        files.splice(index, 1);
        files.forEach(function (f) { dt.items.add(f); });
        input.files = dt.files;
        handleImagePreview(input);
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
                    if (typeof window.showToast === 'function') window.showToast(data.message || 'Błąd', 'error');
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
                if (typeof window.showToast === 'function') window.showToast('Błąd ładowania danych', 'error');
            });
    };

    function renderEditImages(images, itemId, canAdd) {
        var photosArea = document.getElementById('editUploadPhotos');
        var emptyState = document.getElementById('editEmptyState');
        var actionsCol = document.getElementById('editUploadActions');

        // Remove old image items (keep empty state element)
        if (photosArea) {
            photosArea.querySelectorAll('.existing-image-item').forEach(function (el) { el.remove(); });
        }

        var hasImages = images && images.length > 0;

        if (hasImages) {
            images.forEach(function (img) {
                var isProductImage = img.source === 'product';
                var div = document.createElement('div');
                div.className = 'existing-image-item' + (img.is_primary ? ' primary' : '') + (isProductImage ? ' product-source' : '');
                var actionsHtml = '';
                if (!isProductImage) {
                    actionsHtml = '<div class="image-actions">' +
                        (!img.is_primary ? '<button type="button" class="btn-set-primary" onclick="setEditPrimary(' + itemId + ',' + img.id + ')" title="Ustaw jako główne">&#9733;</button>' : '') +
                        '<button type="button" class="btn-remove-image" onclick="deleteEditImage(' + itemId + ',' + img.id + ')" title="Usuń">&times;</button>' +
                        '</div>';
                }
                div.innerHTML = '<img src="' + img.url + '" alt="Image">' +
                    (img.is_primary && !isProductImage ? '<span class="primary-indicator">Główne</span>' : '') +
                    (isProductImage ? '<span class="product-image-label">Z produktu</span>' : '') +
                    actionsHtml;
                photosArea.appendChild(div);
            });
        }

        // Empty state
        if (emptyState) emptyState.style.display = hasImages ? 'none' : '';

        // Actions column — show when can add more
        if (actionsCol) actionsCol.style.display = canAdd ? '' : 'none';
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
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'success');
                    closeEditModal();
                    window.location.reload();
                } else {
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'error');
                }
            })
            .catch(function () {
                if (typeof window.showToast === 'function') window.showToast('Wystąpił błąd', 'error');
            })
            .finally(function () {
                btn.disabled = false;
                btn.textContent = 'Zapisz zmiany';
            });
    };

    // ---- Edit modal: Upload additional image ----
    function uploadEditImage(files) {
        if (!files || !files.length || !currentEditItem) return;

        var itemId = currentEditItem.id;
        var formData = new FormData();
        formData.append('image', files[0]);

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
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'success');
                    openEditModal(itemId);
                } else {
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'error');
                }
            })
            .catch(function () {
                if (typeof window.showToast === 'function') window.showToast('Błąd uploadu', 'error');
            });

        // Reset input
        var editInput = document.getElementById('editImageInput');
        if (editInput) editInput.value = '';
    }

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
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'success');
                    openEditModal(itemId);
                } else {
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'error');
                }
            })
            .catch(function () {
                if (typeof window.showToast === 'function') window.showToast('Błąd', 'error');
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
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'success');
                    openEditModal(itemId);
                } else {
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'error');
                }
            })
            .catch(function () {
                if (typeof window.showToast === 'function') window.showToast('Błąd', 'error');
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
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'success');
                    closeDeleteModal();
                    var elements = document.querySelectorAll('[data-item-id="' + itemId + '"]');
                    elements.forEach(function (el) { el.remove(); });
                    var remaining = document.querySelectorAll('.collection-card, .collection-row');
                    if (remaining.length === 0) {
                        window.location.reload();
                    }
                } else {
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'error');
                }
            })
            .catch(function () {
                if (typeof window.showToast === 'function') window.showToast('Wystąpił błąd', 'error');
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
                var existsSection = document.getElementById('publicConfigExists');

                if (!data.exists) {
                    // Brak konfiguracji - pokaż przycisk tworzenia
                    createSection.style.display = '';
                    existsSection.style.display = 'none';
                } else {
                    // Konfiguracja istnieje - pokaż ustawienia
                    createSection.style.display = 'none';
                    existsSection.style.display = '';

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
                if (typeof window.showToast === 'function') window.showToast('Błąd ładowania konfiguracji', 'error');
            });
    }

    function renderConfigItems(items) {
        var list = document.getElementById('configItemsList');
        var selectAll = document.getElementById('configSelectAll');
        list.innerHTML = '';

        if (!items || items.length === 0) {
            list.innerHTML = '<p class="share-items-empty">Brak przedmiotów w kolekcji</p>';
            return;
        }

        var allPublic = true;
        items.forEach(function (item) {
            if (!item.is_public) allPublic = false;

            var row = document.createElement('label');
            row.className = 'share-item-row';
            row.innerHTML =
                '<input type="checkbox" ' + (item.is_public ? 'checked' : '') +
                ' onchange="toggleItemPublic(' + item.id + ', this.checked)">' +
                (item.image_url
                    ? '<img src="' + item.image_url + '" class="share-item-thumb" alt="">'
                    : '<div class="share-item-thumb"></div>') +
                '<span class="share-item-name">' + escapeHtml(item.name) + '</span>';
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
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'success');
                    loadPublicConfig();
                } else {
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'error');
                }
            })
            .catch(function () {
                if (typeof window.showToast === 'function') window.showToast('Wystąpił błąd', 'error');
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
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'success');
                } else {
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'error');
                }
            })
            .catch(function () {
                if (typeof window.showToast === 'function') window.showToast('Wystąpił błąd', 'error');
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
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'error');
                }
                // Aktualizuj "Zaznacz wszystkie"
                updateSelectAllState();
            })
            .catch(function () {
                if (typeof window.showToast === 'function') window.showToast('Wystąpił błąd', 'error');
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
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'success');
                } else {
                    if (typeof window.showToast === 'function') window.showToast(data.message, 'error');
                }
            })
            .catch(function () {
                if (typeof window.showToast === 'function') window.showToast('Wystąpił błąd', 'error');
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

        var btn = document.getElementById('btnCopyUrl');
        var copyIcon = btn ? btn.querySelector('.copy-icon') : null;
        var checkIcon = btn ? btn.querySelector('.check-icon') : null;

        function showCheck() {
            if (copyIcon) copyIcon.style.display = 'none';
            if (checkIcon) checkIcon.style.display = '';
            if (btn) btn.classList.add('copied');
            setTimeout(function () {
                if (copyIcon) copyIcon.style.display = '';
                if (checkIcon) checkIcon.style.display = 'none';
                if (btn) btn.classList.remove('copied');
            }, 1500);
        }

        navigator.clipboard.writeText(input.value).then(function () {
            showCheck();
            if (typeof window.showToast === 'function') window.showToast('Link skopiowany', 'success');
        }).catch(function () {
            input.select();
            document.execCommand('copy');
            showCheck();
            if (typeof window.showToast === 'function') window.showToast('Link skopiowany', 'success');
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
                    if (typeof window.showToast === 'function') window.showToast(result.message, 'error');
                    return;
                }

                // Set QR image
                var qrImage = document.getElementById(context + 'QrImage');
                if (qrImage) qrImage.src = result.qr_data_uri;

                // Show QR inline section
                var qrInline = document.getElementById(context + 'QrInline');
                if (qrInline) qrInline.classList.add('active');

                // Zapisz session token (dla add modal - do formularza)
                if (context === 'add') {
                    var tokenInput = document.getElementById('addQrSessionToken');
                    if (tokenInput) tokenInput.value = result.session_token;
                }

                // Startuj polling co 3 sekundy
                startQrPolling(context, result.session_token);
            })
            .catch(function () {
                if (typeof window.showToast === 'function') window.showToast('Błąd tworzenia sesji QR', 'error');
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
                            // Hide QR code, show uploaded preview
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
                            if (typeof window.showToast === 'function') window.showToast('Zdjęcie dodane z telefonu', 'success');
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

        // Hide the QR inline section
        var qrInline = document.getElementById(context + 'QrInline');
        if (qrInline) qrInline.classList.remove('active');

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
    // QR INLINE SHOW / HIDE
    // ================================================================

    window.showQrInline = function (context) {
        startQrSession(context);
    };

    window.hideQrInline = function (context) {
        stopQrPolling(context);
        var qrInline = document.getElementById(context + 'QrInline');
        if (qrInline) qrInline.classList.remove('active');

        // Reset QR display for next use
        var qrDisplay = document.getElementById(context + 'QrDisplay');
        if (qrDisplay) qrDisplay.style.display = '';

        var statusEl = document.getElementById(context + 'QrStatus');
        if (statusEl) {
            statusEl.textContent = 'Oczekiwanie na upload...';
            statusEl.className = 'qr-status';
        }

        if (context === 'add') {
            var uploaded = document.getElementById('addQrUploaded');
            if (uploaded) uploaded.style.display = 'none';
        }
    };

    // ================================================================
    // DRAG & DROP + UPLOAD ZONE CLICK
    // ================================================================

    function setupUploadRow(photosId, btnId, inputId, opts) {
        var photosArea = document.getElementById(photosId);
        var btn = document.getElementById(btnId);
        var input = document.getElementById(inputId);

        // "Z komputera" button click — open file picker
        if (btn && input) {
            btn.addEventListener('click', function () {
                input.click();
            });
        }

        // File input change
        if (input && opts.onInputChange) {
            input.addEventListener('change', function () {
                opts.onInputChange(input);
            });
        }

        // Drag & drop on photos area
        if (photosArea) {
            photosArea.addEventListener('dragenter', function (e) {
                e.preventDefault();
                e.stopPropagation();
                photosArea.classList.add('drag-over');
            });

            photosArea.addEventListener('dragover', function (e) {
                e.preventDefault();
                e.stopPropagation();
                photosArea.classList.add('drag-over');
            });

            photosArea.addEventListener('dragleave', function (e) {
                e.preventDefault();
                e.stopPropagation();
                photosArea.classList.remove('drag-over');
            });

            photosArea.addEventListener('drop', function (e) {
                e.preventDefault();
                e.stopPropagation();
                photosArea.classList.remove('drag-over');

                var droppedFiles = e.dataTransfer.files;
                if (!droppedFiles.length) return;

                var imageFiles = [];
                for (var i = 0; i < droppedFiles.length; i++) {
                    if (droppedFiles[i].type.match(/^image\/(jpeg|png|webp|gif)$/)) {
                        imageFiles.push(droppedFiles[i]);
                    }
                }

                if (imageFiles.length === 0) {
                    if (typeof window.showToast === 'function') window.showToast('Dozwolone formaty: JPG, PNG, WebP, GIF', 'warning');
                    return;
                }

                if (opts.onDrop) opts.onDrop(imageFiles);
            });
        }
    }

    // Setup Add modal
    setupUploadRow('addUploadPhotos', 'addBtnComputer', 'addImageInput', {
        onInputChange: function (input) {
            var files = Array.from(input.files);
            if (files.length > 3) {
                if (typeof window.showToast === 'function') window.showToast('Maksymalnie 3 zdjęcia', 'warning');
                var dt = new DataTransfer();
                for (var i = 0; i < 3; i++) dt.items.add(files[i]);
                input.files = dt.files;
            }
            handleImagePreview(input);
        },
        onDrop: function (droppedFiles) {
            var input = document.getElementById('addImageInput');
            if (!input) return;
            var existing = Array.from(input.files);
            var combined = existing.concat(droppedFiles).slice(0, 3);
            if (existing.length + droppedFiles.length > 3) {
                if (typeof window.showToast === 'function') window.showToast('Maksymalnie 3 zdjęcia', 'warning');
            }
            var dt = new DataTransfer();
            combined.forEach(function (f) { dt.items.add(f); });
            input.files = dt.files;
            handleImagePreview(input);
        }
    });

    // Setup Edit modal
    setupUploadRow('editUploadPhotos', 'editBtnComputer', 'editImageInput', {
        onInputChange: function (input) {
            uploadEditImage(input.files);
        },
        onDrop: function (droppedFiles) {
            uploadEditImage(droppedFiles);
        }
    });

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
