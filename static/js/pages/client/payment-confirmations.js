/**
 * Panel potwierdzeń płatności - obsługa UI
 * Wizard 2-krokowy: wybór etapów per zamówienie → przelew + upload
 */

/**
 * Otwórz modal płatności dla konkretnego zamówienia (z onclick w tabeli)
 */
window.openPaymentForOrder = function(btnEl) {
    var orderId = parseInt(btnEl.dataset.orderId);
    if (!orderId) return;

    document.querySelectorAll('.order-checkbox').forEach(function(cb) {
        cb.checked = false;
    });

    var checkbox = document.querySelector('.order-checkbox[data-order-id="' + orderId + '"]');
    if (checkbox) {
        checkbox.checked = true;
        checkbox.dispatchEvent(new Event('change', { bubbles: true }));
    }

    setTimeout(function() {
        var executeBtn = document.getElementById('bulk-execute-payment-btn');
        if (executeBtn) executeBtn.click();
    }, 50);
};

/**
 * Kliknięcie w kartę toggleuje checkbox (ignoruje przyciski i interaktywne elementy)
 */
window.toggleCardCheckbox = function(e) {
    if (e.target.closest('button, input, a, .pc-card-pay-btn')) return;
    var card = e.currentTarget;
    var cb = card.querySelector('.order-checkbox');
    if (!cb || cb.disabled) return;
    cb.checked = !cb.checked;
    cb.dispatchEvent(new Event('change', { bubbles: true }));
};

/**
 * Toggle widoczności ukrytych pozycji zamówienia
 */
window.toggleOrderItems = function(orderId, totalItems) {
    const hiddenItems = document.getElementById(`hiddenItems-${orderId}`);
    const toggleBtn = hiddenItems?.parentElement.querySelector('.items-toggle-btn .toggle-text');

    if (!hiddenItems || !toggleBtn) return;

    const isHidden = hiddenItems.style.display === 'none';

    if (isHidden) {
        hiddenItems.style.display = 'flex';
        toggleBtn.textContent = 'Ukryj pozostałe';
    } else {
        hiddenItems.style.display = 'none';
        toggleBtn.textContent = `W sumie ${totalItems} przedmiotów - pokaż pozostałe`;
    }
};

(function () {
    'use strict';

    // === STAN ===
    var selectedOrders = new Map(); // orderId -> { orderNumber, amount, productStatus }
    var selectedStages = new Map(); // orderId -> Set(['product', ...])
    var currentStep = 1;
    var paymentMethodsLoaded = false;
    var paymentMethodsData = [];

    // Definicja etapów — ikony SVG
    var STAGE_ICONS = {
        product: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>',
        korean_shipping: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.8 19.2L16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"/></svg>',
        customs_vat: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>',
        domestic_shipping: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="1" y="3" width="15" height="13"/><polygon points="16 8 20 8 23 11 23 16 16 16 16 8"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>'
    };

    /**
     * Zwraca listę etapów dla danego zamówienia (zależy od payment_stages).
     * payment_stages == 4 (Proxy): product → korean_shipping → customs_vat → domestic_shipping
     * payment_stages == 3 (Polska): product → customs_vat → domestic_shipping
     * payment_stages == 2 (On-hand): product → domestic_shipping
     */
    function getStagesForOrder(paymentStages) {
        if (paymentStages === 4) {
            return [
                { id: 'product', name: 'Produkty' },
                { id: 'korean_shipping', name: 'Wysyłka KR' },
                { id: 'customs_vat', name: 'Cło i VAT' },
                { id: 'domestic_shipping', name: 'Wysyłka PL' }
            ];
        }
        if (paymentStages === 2) {
            return [
                { id: 'product', name: 'Produkty' },
                { id: 'domestic_shipping', name: 'Wysyłka PL' }
            ];
        }
        // Domyślnie 3 etapy
        return [
            { id: 'product', name: 'Produkty' },
            { id: 'customs_vat', name: 'Cło i VAT' },
            { id: 'domestic_shipping', name: 'Wysyłka PL' }
        ];
    }

    // === DOM REFERENCES ===
    var bulkToolbar = document.getElementById('pcBulkToolbar');
    var bulkSelectedCount = document.getElementById('pcSelectedCount');
    var bulkSelectedTotal = document.getElementById('pcSelectedTotal');
    var bulkExecuteBtn = document.getElementById('bulk-execute-payment-btn');
    var paymentModal = document.getElementById('payment-modal');
    var modalCloseBtn = document.getElementById('modal-close-btn');
    var totalAmountValue = document.getElementById('total-amount-value');
    var wizardTotalAmount = document.getElementById('wizard-total-amount');
    var uploadForm = document.getElementById('upload-form');
    var proofFileInput = document.getElementById('proof-file');
    var filePreview = document.getElementById('file-preview');
    var submitBtn = document.getElementById('submit-btn');

    // QR Upload state
    var paymentSocket = null;
    var currentQrSessionToken = null;
    var qrUploadedFilename = null;

    var paymentMethodsContainer = document.getElementById('payment-methods-container');
    var wizardNextBtn = document.getElementById('wizard-next-btn');
    var wizardBackBtn = document.getElementById('wizard-back-btn');
    var cancelBtn = document.getElementById('cancel-btn');
    var ordersStagesContainer = document.getElementById('pc-orders-stages');

    // SVG ikona kopiowania
    var COPY_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';

    // === INICJALIZACJA ===

    function init() {
        var orderCheckboxes = document.querySelectorAll('.order-checkbox');
        if (orderCheckboxes.length === 0) return;

        orderCheckboxes.forEach(function (cb) {
            cb.addEventListener('change', handleOrderCheckboxChange);
        });

        if (bulkExecuteBtn) {
            bulkExecuteBtn.addEventListener('click', openPaymentModal);
        }

        var selectAllToggle = document.getElementById('select-all-toggle');
        if (selectAllToggle) {
            selectAllToggle.addEventListener('click', function(e) {
                e.preventDefault();
                var enabledCbs = document.querySelectorAll('.order-checkbox:not([disabled])');
                var allChecked = Array.from(enabledCbs).every(function(cb) { return cb.checked; });
                enabledCbs.forEach(function(cb) { cb.checked = !allChecked; });
                this.textContent = allChecked ? 'Zaznacz wszystkie' : 'Odznacz wszystkie';
                syncSelectedOrders();
            });
        }

        document.querySelectorAll('.pc-upload-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var orderId = parseInt(this.dataset.orderId);
                openPaymentModalForOrder(orderId);
            });
        });

        if (modalCloseBtn) {
            modalCloseBtn.addEventListener('click', closePaymentModal);
        }

        if (paymentModal) {
            paymentModal.addEventListener('click', function (e) {
                if (e.target === paymentModal) closePaymentModal();
            });
        }

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && paymentModal && paymentModal.classList.contains('active')) {
                closePaymentModal();
            }
        });

        if (cancelBtn) {
            cancelBtn.addEventListener('click', closePaymentModal);
        }

        // Wizard: nawigacja
        if (wizardNextBtn) {
            wizardNextBtn.addEventListener('click', function () {
                goToStep(2);
            });
        }

        if (wizardBackBtn) {
            wizardBackBtn.addEventListener('click', function () {
                goToStep(1);
            });
        }

        if (proofFileInput) {
            proofFileInput.addEventListener('change', handleFileSelect);
        }

        if (uploadForm) {
            uploadForm.addEventListener('submit', handleUploadSubmit);
        }

        // QR Upload buttons
        var qrBtn = document.getElementById('pc-qr-btn');
        if (qrBtn) {
            qrBtn.addEventListener('click', startPaymentQrSession);
        }
        var qrCancelBtn = document.getElementById('pc-qr-cancel-btn');
        if (qrCancelBtn) {
            qrCancelBtn.addEventListener('click', cancelPaymentQr);
        }

        initDragDrop();
        handlePreselect();
    }

    // === WIZARD STEPS ===

    function goToStep(step) {
        currentStep = step;

        // Aktualizuj wskaźniki kroków
        document.querySelectorAll('.wizard-step').forEach(function (el) {
            var stepNum = parseInt(el.dataset.step);
            el.classList.remove('active', 'completed');
            if (stepNum < step) {
                el.classList.add('completed');
            } else if (stepNum === step) {
                el.classList.add('active');
            }
        });

        // Pokaż/ukryj zawartość kroków
        document.querySelectorAll('.wizard-content').forEach(function (el) {
            el.style.display = 'none';
        });

        var stepContent = document.getElementById('pc-wizard-step-' + step);
        if (stepContent) stepContent.style.display = 'block';

        // Przyciski
        if (step === 1) {
            if (wizardBackBtn) wizardBackBtn.style.display = 'none';
            if (wizardNextBtn) wizardNextBtn.style.display = 'inline-flex';
            if (submitBtn) submitBtn.style.display = 'none';
            if (cancelBtn) cancelBtn.style.display = 'inline-flex';
            updateNextButtonState();
        } else if (step === 2) {
            if (wizardBackBtn) wizardBackBtn.style.display = 'inline-flex';
            if (wizardNextBtn) wizardNextBtn.style.display = 'none';
            if (submitBtn) submitBtn.style.display = 'inline-flex';
            if (cancelBtn) cancelBtn.style.display = 'none';

            // Aktualizuj kwotę w kroku 2
            updateStep2Total();

            // Załaduj metody płatności
            if (paymentMethodsLoaded) {
                renderPaymentMethods(paymentMethodsData);
            } else {
                loadPaymentMethods();
            }
        }
    }

    function updateNextButtonState() {
        if (!wizardNextBtn) return;
        var hasSelection = false;
        selectedStages.forEach(function (stages) {
            if (stages.size > 0) hasSelection = true;
        });
        wizardNextBtn.disabled = !hasSelection;
    }

    // === KROK 1: ZAMÓWIENIA Z ETAPAMI ===

    function renderOrdersWithStages() {
        if (!ordersStagesContainer) return;

        var html = '';

        selectedOrders.forEach(function (data, orderId) {
            var stages = getStagesForOrder(data.paymentStages);

            html += '<div class="pc-order-stage-row">';
            html += '<div class="pc-order-stage-header">';
            html += '<span class="pc-order-stage-number">' + escapeHtml(data.orderNumber) + '</span>';
            html += '</div>';

            html += '<div class="pc-stage-tiles">';
            stages.forEach(function (stage) {
                var status = getStageStatus(orderId, stage.id, data);
                var canUpload = canUploadStage(stage.id, data);
                var tileClass = 'pc-stage-tile';
                var badge = '';
                var clickable = false;
                var isSelected = selectedStages.has(orderId) && selectedStages.get(orderId).has(stage.id);

                if (status === 'approved') {
                    tileClass += ' paid';
                    badge = '<span class="pc-stage-badge pc-stage-badge-paid">Opłacone</span>';
                } else if (status === 'pending') {
                    tileClass += ' pending';
                    badge = '<span class="pc-stage-badge pc-stage-badge-pending">Weryfikacja</span>';
                } else if (status === 'rejected') {
                    tileClass += ' rejected';
                    clickable = true;
                    badge = '<span class="pc-stage-badge pc-stage-badge-rejected">Odrzucone</span>';
                } else if (canUpload) {
                    clickable = true;
                } else {
                    tileClass += ' disabled';
                    badge = '<span class="pc-stage-badge pc-stage-badge-soon">Zablokowane</span>';
                }

                if (isSelected) {
                    tileClass += ' selected';
                }

                var amountText = getStageAmount(stage.id, data).toFixed(2) + ' zł';
                var icon = STAGE_ICONS[stage.id] || '';

                html += '<div class="' + tileClass + '"' +
                    (clickable ? ' data-order-id="' + orderId + '" data-stage="' + stage.id + '"' : '') +
                    '>';
                html += '<div class="pc-stage-tile-icon">' + icon + '</div>';
                html += '<span class="pc-stage-tile-name">' + escapeHtml(stage.name) + '</span>';
                html += '<span class="pc-stage-tile-amount">' + amountText + '</span>';
                if (badge) html += badge;
                html += '</div>';
            });
            html += '</div>';

            html += '</div>';
        });

        ordersStagesContainer.innerHTML = html;

        // Binduj kliknięcia na kafelki
        ordersStagesContainer.querySelectorAll('.pc-stage-tile[data-stage]').forEach(function (tile) {
            tile.addEventListener('click', function () {
                var orderId = parseInt(this.dataset.orderId);
                var stageId = this.dataset.stage;

                if (!selectedStages.has(orderId)) {
                    selectedStages.set(orderId, new Set());
                }

                var stages = selectedStages.get(orderId);
                if (stages.has(stageId)) {
                    stages.delete(stageId);
                    this.classList.remove('selected');
                } else {
                    stages.add(stageId);
                    this.classList.add('selected');
                }

                updateWizardTotal();
                updateNextButtonState();
            });
        });

        updateWizardTotal();
        updateNextButtonState();
    }

    function getStageStatus(orderId, stageId, orderData) {
        if (stageId === 'product') {
            return orderData.productStatus || 'none';
        }
        // E2 (korean_shipping) → stage2Status (tylko 4-płatnościowe)
        if (stageId === 'korean_shipping') {
            return orderData.stage2Status || 'none';
        }
        // E3 (customs_vat) → stage3Status (zawsze)
        if (stageId === 'customs_vat') {
            return orderData.stage3Status || 'none';
        }
        // E4 (domestic_shipping) → stage4Status (zawsze)
        if (stageId === 'domestic_shipping') {
            return orderData.stage4Status || 'none';
        }
        return 'none';
    }

    function canUploadStage(stageId, orderData) {
        if (stageId === 'product') {
            var st = orderData.productStatus;
            return st !== 'approved' && st !== 'pending';
        }
        // E2 (korean_shipping) → canUploadStage2 (tylko 4-płatnościowe)
        if (stageId === 'korean_shipping') {
            return orderData.canUploadStage2;
        }
        // E3 (customs_vat) → canUploadStage3 (zawsze)
        if (stageId === 'customs_vat') {
            return orderData.canUploadStage3;
        }
        // E4 (domestic_shipping) → canUploadStage4 (zawsze)
        if (stageId === 'domestic_shipping') {
            return orderData.canUploadStage4;
        }
        return false;
    }

    function updateWizardTotal() {
        var total = 0;
        selectedStages.forEach(function (stages, orderId) {
            if (stages.size === 0) return;
            var orderData = selectedOrders.get(orderId);
            if (!orderData) return;

            stages.forEach(function (stageId) {
                total += getStageAmount(stageId, orderData);
            });
        });

        if (wizardTotalAmount) {
            wizardTotalAmount.textContent = total.toFixed(2) + ' zł';
        }
    }

    function updateStep2Total() {
        var total = 0;
        selectedStages.forEach(function (stages, orderId) {
            if (stages.size === 0) return;
            var orderData = selectedOrders.get(orderId);
            if (!orderData) return;
            stages.forEach(function (stageId) {
                total += getStageAmount(stageId, orderData);
            });
        });

        if (totalAmountValue) {
            totalAmountValue.textContent = total.toFixed(2) + ' zł';
        }
    }

    // === DRAG & DROP UPLOAD ===

    function initDragDrop() {
        var dropzone = document.getElementById('upload-dropzone');
        if (!dropzone || !proofFileInput) return;

        dropzone.addEventListener('click', function (e) {
            if (e.target !== proofFileInput) {
                proofFileInput.click();
            }
        });

        var browseLink = dropzone.querySelector('.pc-upload-browse');
        if (browseLink) {
            browseLink.addEventListener('click', function (e) {
                e.stopPropagation();
                proofFileInput.click();
            });
        }

        ['dragenter', 'dragover'].forEach(function (eventName) {
            dropzone.addEventListener(eventName, function (e) {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.add('pc-upload-dragover');
            });
        });

        ['dragleave', 'drop'].forEach(function (eventName) {
            dropzone.addEventListener(eventName, function (e) {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.remove('pc-upload-dragover');
            });
        });

        dropzone.addEventListener('drop', function (e) {
            var files = e.dataTransfer.files;
            if (files.length > 0) {
                proofFileInput.files = files;
                proofFileInput.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
    }

    // === PRESELECT Z URL ===

    function handlePreselect() {
        var urlParams = new URLSearchParams(window.location.search);
        var preselectOrderId = urlParams.get('preselect');

        if (!preselectOrderId) return;

        var checkbox = document.querySelector('.order-checkbox[data-order-id="' + preselectOrderId + '"]');
        if (!checkbox || checkbox.disabled) return;

        checkbox.checked = true;
        syncSelectedOrders();

        setTimeout(function () {
            openPaymentModal();
        }, 500);

        window.history.replaceState({}, document.title, window.location.pathname);
    }

    // === SELECT / DESELECT ===

    function handleOrderCheckboxChange() {
        syncSelectedOrders();
    }

    function syncSelectedOrders() {
        selectedOrders.clear();

        // Toggle selected class on cards
        document.querySelectorAll('.pc-order-card').forEach(function (card) {
            var cb = card.querySelector('.order-checkbox');
            if (cb && cb.checked) {
                card.classList.add('selected');
            } else {
                card.classList.remove('selected');
            }
        });

        document.querySelectorAll('.order-checkbox:checked').forEach(function (cb) {
            var orderId = parseInt(cb.dataset.orderId);
            var row = cb.closest('.pc-order-card') || cb.closest('tr');
            selectedOrders.set(orderId, {
                orderNumber: cb.dataset.orderNumber,
                amount: parseFloat(cb.dataset.amount),
                productStatus: cb.dataset.productStatus || 'none',
                paymentStages: parseInt(cb.dataset.paymentStages) || 3,
                stage2Status: row ? (row.dataset.stage2Status || 'none') : 'none',
                stage3Status: row ? (row.dataset.stage3Status || 'none') : 'none',
                stage4Status: row ? (row.dataset.stage4Status || '') : '',
                canUploadStage2: row ? (row.dataset.canUploadStage2 === 'true') : false,
                canUploadStage3: row ? (row.dataset.canUploadStage3 === 'true') : false,
                canUploadStage4: row ? (row.dataset.canUploadStage4 === 'true') : false,
                proxyShippingAmount: row ? parseFloat(row.dataset.proxyShippingAmount || 0) : 0,
                customsVatAmount: row ? parseFloat(row.dataset.customsVatAmount || 0) : 0,
                shippingCostAmount: row ? parseFloat(row.dataset.shippingCostAmount || 0) : 0
            });
        });

        updateUI();
    }

    function getStageAmount(stageId, orderData) {
        switch (stageId) {
            case 'product': return orderData.amount;
            case 'korean_shipping': return orderData.proxyShippingAmount;
            case 'customs_vat': return orderData.customsVatAmount;
            case 'domestic_shipping': return orderData.shippingCostAmount;
            default: return 0;
        }
    }

    function updateUI() {
        var count = selectedOrders.size;

        if (bulkToolbar) {
            if (count > 0) {
                bulkToolbar.classList.remove('hidden');
                bulkSelectedCount.textContent = count + ' zaznaczonych';

                var total = 0;
                selectedOrders.forEach(function(data) {
                    // E1: Produkt - do zapłaty jeśli nie approved i nie pending
                    var ps = data.productStatus;
                    if (ps !== 'approved' && ps !== 'pending') {
                        total += data.amount;
                    }
                    // E2: Wysyłka KR (tylko 4-etapowe)
                    if (data.canUploadStage2) {
                        total += data.proxyShippingAmount;
                    }
                    // E3: Cło/VAT
                    if (data.canUploadStage3) {
                        total += data.customsVatAmount;
                    }
                    // E4: Wysyłka PL
                    if (data.canUploadStage4) {
                        total += data.shippingCostAmount;
                    }
                });
                if (bulkSelectedTotal) {
                    bulkSelectedTotal.textContent = total.toFixed(2) + ' zł';
                }
            } else {
                bulkToolbar.classList.add('hidden');
            }
        }

        var selectAllToggle = document.getElementById('select-all-toggle');
        if (selectAllToggle) {
            var enabledCbs = document.querySelectorAll('.order-checkbox:not([disabled])');
            var allChecked = enabledCbs.length > 0 && Array.from(enabledCbs).every(function(cb) { return cb.checked; });
            selectAllToggle.textContent = allChecked ? 'Odznacz wszystkie' : 'Zaznacz wszystkie';
        }
    }

    // === MODAL ===

    function openPaymentModal() {
        if (selectedOrders.size === 0) return;

        // Reset wizard
        selectedStages.clear();
        currentStep = 1;

        // Auto-select pierwszy dostępny etap (none/rejected + can upload)
        selectedOrders.forEach(function (data, orderId) {
            var autoStages = new Set();
            var stages = getStagesForOrder(data.paymentStages);
            stages.forEach(function (stage) {
                var status = getStageStatus(orderId, stage.id, data);
                var canDo = canUploadStage(stage.id, data);
                if ((status === 'none' || status === 'rejected') && canDo) {
                    autoStages.add(stage.id);
                }
            });
            if (autoStages.size > 0) {
                selectedStages.set(orderId, autoStages);
            }
        });

        // Renderuj krok 1
        renderOrdersWithStages();
        goToStep(1);

        // Pokaż modal
        paymentModal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    function openPaymentModalForOrder(orderId) {
        document.querySelectorAll('.order-checkbox').forEach(function (cb) {
            cb.checked = false;
        });

        var checkbox = document.querySelector('.order-checkbox[data-order-id="' + orderId + '"]');
        if (checkbox) {
            checkbox.checked = true;
            syncSelectedOrders();
            openPaymentModal();
        }
    }

    function closePaymentModal() {
        paymentModal.classList.add('closing');

        setTimeout(function () {
            paymentModal.classList.remove('active', 'closing');
            document.body.style.overflow = '';

            if (uploadForm) uploadForm.reset();
            if (filePreview) filePreview.innerHTML = '';
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Prześlij potwierdzenie';
            }

            var dropzone = document.getElementById('upload-dropzone');
            if (dropzone) dropzone.classList.remove('pc-upload-dragover');

            // Reset QR state
            resetQrState();
        }, 350);
    }

    // === METODY PŁATNOŚCI ===

    function loadPaymentMethods() {
        if (!paymentMethodsContainer) return;

        paymentMethodsContainer.innerHTML = '<div class="pc-loading">Ładowanie metod płatności...</div>';

        fetch('/client/payment-confirmations/payment-methods')
            .then(function (response) { return response.json(); })
            .then(function (data) {
                if (data.success && data.methods) {
                    paymentMethodsData = data.methods;
                    paymentMethodsLoaded = true;
                    renderPaymentMethods(data.methods);
                } else {
                    paymentMethodsContainer.innerHTML = '<p class="pc-error-text">Błąd podczas ładowania metod płatności.</p>';
                }
            })
            .catch(function (error) {
                console.error('Error loading payment methods:', error);
                paymentMethodsContainer.innerHTML = '<p class="pc-error-text">Błąd połączenia. Spróbuj ponownie.</p>';
            });
    }


    function getSelectedOrderNumbers() {
        var numbers = [];
        selectedOrders.forEach(function (data) {
            numbers.push(data.orderNumber);
        });
        return numbers.join(', ');
    }

    function renderCopyButton(text) {
        return '<button class="pc-btn-copy" data-copy-text="' + escapeAttr(text) + '" title="Kopiuj">' +
            COPY_ICON +
            '</button>';
    }

    function getMethodLogoUrl(method) {
        var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        if (isDark && method.logo_dark_url) return method.logo_dark_url;
        if (!isDark && method.logo_light_url) return method.logo_light_url;
        return method.logo_light_url || method.logo_dark_url || null;
    }

    function renderMethodDetails(method, detailPanel) {
        var orderNumbers = getSelectedOrderNumbers();
        var html = '';

        html += '<div class="pc-method-detail-header">';
        html += '<span class="pc-method-detail-name">' + escapeHtml(method.name) + '</span>';
        html += '</div>';

        html += '<div class="pc-method-detail-fields">';

        if (method.recipient) {
            html += '<div class="pc-method-field">';
            html += '<span class="pc-method-field-label">Odbiorca</span>';
            html += '<div class="pc-method-field-value">';
            html += '<span>' + escapeHtml(method.recipient) + '</span>';
            html += renderCopyButton(method.recipient);
            html += '</div></div>';
        }

        if (method.account_number) {
            var accountLabel = method.account_number_label || 'Numer konta';
            html += '<div class="pc-method-field">';
            html += '<span class="pc-method-field-label">' + escapeHtml(accountLabel) + '</span>';
            html += '<div class="pc-method-field-value">';
            html += '<code>' + escapeHtml(method.account_number) + '</code>';
            html += renderCopyButton(method.account_number);
            html += '</div></div>';
        }

        if (method.code) {
            var codeLabel = method.code_label || 'Kod SWIFT';
            html += '<div class="pc-method-field">';
            html += '<span class="pc-method-field-label">' + escapeHtml(codeLabel) + '</span>';
            html += '<div class="pc-method-field-value">';
            html += '<code>' + escapeHtml(method.code) + '</code>';
            html += renderCopyButton(method.code);
            html += '</div></div>';
        }

        if (method.transfer_title) {
            var title = method.transfer_title.replace(/\[NUMER ZAMÓWIENIA\]/gi, orderNumbers);
            html += '<div class="pc-method-field">';
            html += '<span class="pc-method-field-label">Tytuł przelewu</span>';
            html += '<div class="pc-method-field-value">';
            html += '<span>' + escapeHtml(title) + '</span>';
            html += renderCopyButton(title);
            html += '</div></div>';
        }

        html += '</div>';

        detailPanel.innerHTML = html;
        detailPanel.style.display = 'block';

        detailPanel.querySelectorAll('.pc-btn-copy').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                copyToClipboard(this.dataset.copyText, this);
            });
        });
    }

    function renderPaymentMethods(methods) {
        if (!paymentMethodsContainer) return;

        if (methods.length === 0) {
            paymentMethodsContainer.innerHTML = '<p class="pc-no-methods">Brak dostępnych metod płatności. Skontaktuj się z administratorem.</p>';
            return;
        }

        var html = '';

        html += '<div class="pc-methods-grid">';
        methods.forEach(function (method, index) {
            var logoUrl = getMethodLogoUrl(method);

            html += '<div class="pc-method-tile' + (index === 0 ? ' active' : '') + '" data-method-index="' + index + '" data-method-id="' + method.id + '">';
            if (logoUrl) {
                html += '<img class="pc-method-tile-logo" src="' + escapeAttr(logoUrl) + '" alt="' + escapeAttr(method.name) + '">';
            } else {
                html += '<span class="pc-method-tile-text">' + escapeHtml(method.name) + '</span>';
            }
            html += '</div>';
        });
        html += '</div>';

        html += '<div class="pc-method-detail" id="pc-method-detail"></div>';

        paymentMethodsContainer.innerHTML = html;

        var detailPanel = document.getElementById('pc-method-detail');

        if (methods.length > 0) {
            renderMethodDetails(methods[0], detailPanel);
        }

        paymentMethodsContainer.querySelectorAll('.pc-method-tile').forEach(function (tile) {
            tile.addEventListener('click', function () {
                var idx = parseInt(this.dataset.methodIndex);
                var method = methods[idx];
                if (!method) return;

                paymentMethodsContainer.querySelectorAll('.pc-method-tile').forEach(function (t) {
                    t.classList.remove('active');
                });
                this.classList.add('active');

                renderMethodDetails(method, detailPanel);
            });
        });
    }

    // === UPLOAD ===

    function handleFileSelect(event) {
        var file = event.target.files[0];

        if (!filePreview) return;

        if (!file) {
            filePreview.innerHTML = '';
            return;
        }

        var maxSize = 5 * 1024 * 1024;
        if (file.size > maxSize) {
            showToast('Plik jest za duży. Maksymalny rozmiar: 5MB.', 'error');
            event.target.value = '';
            filePreview.innerHTML = '';
            return;
        }

        var allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'application/pdf'];
        if (allowedTypes.indexOf(file.type) === -1) {
            showToast('Nieprawidłowy format pliku. Dozwolone: JPG, PNG, PDF.', 'error');
            event.target.value = '';
            filePreview.innerHTML = '';
            return;
        }

        var sizeKb = (file.size / 1024).toFixed(1);
        var fileInfoHtml = '<div class="pc-file-info">' +
            '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>' +
            '<span>' + escapeHtml(file.name) + '</span>' +
            '<span class="pc-file-size">(' + sizeKb + ' KB)</span>' +
            '</div>';

        if (file.type.startsWith('image/')) {
            var reader = new FileReader();
            reader.onload = function (e) {
                filePreview.innerHTML =
                    '<div class="pc-image-preview"><img src="' + e.target.result + '" alt="Preview"></div>' +
                    fileInfoHtml;
            };
            reader.readAsDataURL(file);
        } else {
            filePreview.innerHTML = fileInfoHtml;
        }
    }

    function handleUploadSubmit(event) {
        event.preventDefault();

        // Check if file uploaded via QR or local file
        var hasLocalFile = proofFileInput && proofFileInput.files[0];
        var hasQrFile = qrUploadedFilename && currentQrSessionToken;

        if (!hasLocalFile && !hasQrFile) {
            showToast('Wybierz plik potwierdzenia lub wgraj z telefonu.', 'error');
            return;
        }

        // Zbierz order_stages
        var orderStagesArr = [];
        selectedStages.forEach(function (stages, orderId) {
            if (stages.size > 0) {
                orderStagesArr.push({
                    order_id: orderId,
                    stages: Array.from(stages)
                });
            }
        });

        if (orderStagesArr.length === 0) {
            showToast('Nie wybrano żadnych etapów do opłacenia.', 'error');
            return;
        }

        var formData = new FormData();
        if (hasQrFile) {
            formData.append('qr_session_token', currentQrSessionToken);
        } else {
            formData.append('proof_file', proofFileInput.files[0]);
        }
        formData.append('order_stages', JSON.stringify(orderStagesArr));

        // Wyślij wybraną metodę płatności
        var activeTile = document.querySelector('.pc-method-tile.active');
        if (activeTile && activeTile.dataset.methodId) {
            formData.append('payment_method_id', activeTile.dataset.methodId);
        }

        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Przesyłanie...';
        }

        var csrfToken = document.querySelector('meta[name="csrf-token"]');
        var headers = { 'X-Requested-With': 'XMLHttpRequest' };
        if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;

        fetch('/client/payment-confirmations/upload', {
            method: 'POST',
            body: formData,
            headers: headers
        })
            .then(function (response) { return response.json(); })
            .then(function (data) {
                if (data.success) {
                    showToast(data.message, 'success');
                    // Zamknij modal
                    closePaymentModal();
                    // Zaktualizuj karty — zmień etapy na "Weryfikacja"
                    if (data.updated_stages) {
                        data.updated_stages.forEach(function (us) {
                            updateCardStageStatus(us.order_id, us.stage, us.status);
                        });
                    }
                    // Wyczyść selekcję
                    selectedOrders.clear();
                    selectedStages.clear();
                    document.querySelectorAll('.order-checkbox').forEach(function (cb) {
                        cb.checked = false;
                    });
                    document.querySelectorAll('.pc-order-card').forEach(function (card) {
                        card.classList.remove('selected');
                    });
                    updateUI();
                } else {
                    showToast(data.message || 'Błąd podczas przesyłania.', 'error');
                    resetSubmitBtn();
                }
            })
            .catch(function (error) {
                console.error('Upload error:', error);
                showToast('Błąd połączenia. Spróbuj ponownie.', 'error');
                resetSubmitBtn();
            });
    }

    function resetSubmitBtn() {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Prześlij potwierdzenie';
        }
    }

    // === CARD STAGE UPDATE ===

    function updateCardStageStatus(orderId, stageId, status) {
        var card = document.querySelector('.pc-order-card[data-order-id="' + orderId + '"]');
        if (!card) return;

        var paymentRows = card.querySelectorAll('.pc-payment-row');
        var paymentStages = parseInt(card.dataset.paymentStages) || 3;

        // Map stage ID to row index based on payment_stages
        // 4 stages: product(0), korean_shipping(1), customs_vat(2), domestic_shipping(3)
        // 3 stages: product(0), customs_vat(1), domestic_shipping(2)
        // 2 stages: product(0), domestic_shipping(1)
        var stages = getStagesForOrder(paymentStages);
        var rowIndex = -1;
        for (var si = 0; si < stages.length; si++) {
            if (stages[si].id === stageId) { rowIndex = si; break; }
        }

        if (rowIndex < 0 || rowIndex >= paymentRows.length) return;

        var row = paymentRows[rowIndex];
        var badge = row.querySelector('.pc-stage-badge');
        var amountEl = row.querySelector('.pc-payment-amount');

        if (badge) {
            badge.className = 'pc-stage-badge';
            if (status === 'approved') {
                badge.classList.add('pc-stage-badge-paid');
                badge.textContent = 'Opłacone';
                if (amountEl) amountEl.classList.add('pc-payment-amount-paid');
            } else if (status === 'pending') {
                badge.classList.add('pc-stage-badge-pending');
                badge.textContent = 'Weryfikacja';
                if (amountEl) amountEl.classList.remove('pc-payment-amount-paid');
            } else if (status === 'rejected') {
                badge.classList.add('pc-stage-badge-rejected');
                badge.textContent = 'Odrzucone';
                if (amountEl) amountEl.classList.remove('pc-payment-amount-paid');
            }
        }

        // Zaktualizuj data-attributes na karcie
        if (stageId === 'product') {
            var cb = card.querySelector('.order-checkbox');
            if (cb) cb.dataset.productStatus = status;
        } else if (stageId === 'korean_shipping') {
            card.dataset.stage2Status = status;
        } else if (stageId === 'customs_vat') {
            card.dataset.stage3Status = status;
        } else if (stageId === 'domestic_shipping') {
            card.dataset.stage4Status = status;
        }

        // Pending = nie można ponownie uploadować
        if (status === 'pending') {
            if (stageId === 'korean_shipping') card.dataset.canUploadStage2 = 'false';
            if (stageId === 'customs_vat') card.dataset.canUploadStage3 = 'false';
            if (stageId === 'domestic_shipping') card.dataset.canUploadStage4 = 'false';
        }
    }

    // === UTILITIES ===

    function copyToClipboard(text, btnEl) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(function () {
                showToast('Skopiowano do schowka!');
                showCopyFeedback(btnEl);
            }).catch(function () {
                fallbackCopy(text);
                showCopyFeedback(btnEl);
            });
        } else {
            fallbackCopy(text);
            showCopyFeedback(btnEl);
        }
    }

    function showCopyFeedback(btnEl) {
        if (!btnEl) return;
        btnEl.classList.add('pc-copied');
        setTimeout(function () {
            btnEl.classList.remove('pc-copied');
        }, 1500);
    }

    function fallbackCopy(text) {
        var textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.left = '-9999px';
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand('copy');
            showToast('Skopiowano do schowka!');
        } catch (err) {
            showToast('Nie udało się skopiować.', 'error');
        }
        document.body.removeChild(textArea);
    }

    function showToast(message, type) {
        type = type || 'success';

        if (typeof window.showToast === 'function') {
            window.showToast(message, type);
            return;
        }

        var toast = document.createElement('div');
        toast.className = 'pc-toast pc-toast-' + type;
        toast.textContent = message;
        document.body.appendChild(toast);

        requestAnimationFrame(function () {
            toast.classList.add('pc-toast-visible');
        });

        setTimeout(function () {
            toast.classList.add('pc-toast-out');
            setTimeout(function () {
                if (toast.parentNode) toast.remove();
            }, 300);
        }, 2500);
    }

    function escapeHtml(text) {
        if (!text) return '';
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function escapeAttr(text) {
        if (!text) return '';
        return text.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // === QR UPLOAD (Socket.IO) ===

    function startPaymentQrSession() {
        var csrfToken = document.querySelector('meta[name="csrf-token"]');
        var headers = { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' };
        if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;

        var qrBtn = document.getElementById('pc-qr-btn');
        if (qrBtn) {
            qrBtn.disabled = true;
            qrBtn.textContent = 'Generowanie...';
        }

        fetch('/client/payment-confirmations/qr-session', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({})
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.success) {
                showToast(data.message || 'Błąd', 'error');
                if (qrBtn) {
                    qrBtn.disabled = false;
                    qrBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="8" height="8" rx="1"/><rect x="14" y="2" width="8" height="8" rx="1"/><rect x="2" y="14" width="8" height="8" rx="1"/><rect x="14" y="14" width="4" height="4"/></svg> Wgraj z telefonu (QR)';
                }
                return;
            }

            currentQrSessionToken = data.session_token;
            qrUploadedFilename = null;

            // Show QR
            var qrImg = document.getElementById('pc-qr-image');
            var qrDisplay = document.getElementById('pc-qr-display');
            var qrUploaded = document.getElementById('pc-qr-uploaded');

            if (qrImg) qrImg.src = data.qr_data_uri;
            if (qrDisplay) qrDisplay.style.display = '';
            if (qrBtn) qrBtn.style.display = 'none';
            if (qrUploaded) qrUploaded.style.display = 'none';

            // Hide regular upload area
            var uploadForm = document.getElementById('upload-form');
            var uploadOr = document.querySelector('.pc-upload-or');
            if (uploadForm) uploadForm.style.display = 'none';
            if (uploadOr) uploadOr.style.display = 'none';

            // Connect Socket.IO
            connectPaymentSocket(data.session_token);
        })
        .catch(function(err) {
            console.error('QR session error:', err);
            showToast('Błąd połączenia', 'error');
            if (qrBtn) {
                qrBtn.disabled = false;
                qrBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="8" height="8" rx="1"/><rect x="14" y="2" width="8" height="8" rx="1"/><rect x="2" y="14" width="8" height="8" rx="1"/><rect x="14" y="14" width="4" height="4"/></svg> Wgraj z telefonu (QR)';
            }
        });
    }

    var qrPollInterval = null;

    function connectPaymentSocket(sessionToken) {
        if (paymentSocket) {
            paymentSocket.disconnect();
        }

        // Start HTTP polling as fallback (Socket.IO may not work cross-worker)
        startQrPolling(sessionToken);

        try {
            console.log('[PaymentQR] Connecting Socket.IO...');
            paymentSocket = io({ transports: ['websocket', 'polling'] });

            paymentSocket.on('connect', function() {
                console.log('[PaymentQR] Connected! sid=' + paymentSocket.id);
                paymentSocket.emit('join_payment_upload', { session_token: sessionToken });
                console.log('[PaymentQR] Joined room for token: ' + sessionToken);
            });

            paymentSocket.on('connect_error', function(err) {
                console.error('[PaymentQR] Connection error:', err.message);
            });

            paymentSocket.on('disconnect', function(reason) {
                console.log('[PaymentQR] Disconnected:', reason);
            });

            paymentSocket.on('payment_photo_uploaded', function(data) {
                console.log('[PaymentQR] Received payment_photo_uploaded event:', data);
                if (data.session_token === sessionToken) {
                    stopQrPolling();
                    onQrPhotoUploaded(data.filename);
                }
            });
        } catch (e) {
            console.error('Socket.IO unavailable:', e);
        }
    }

    function startQrPolling(sessionToken) {
        stopQrPolling();
        console.log('[PaymentQR] Starting HTTP polling fallback');
        qrPollInterval = setInterval(function() {
            fetch('/client/payment-confirmations/qr-session/' + sessionToken + '/status')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success && data.status === 'uploaded' && data.filename) {
                        console.log('[PaymentQR] Poll detected upload:', data.filename);
                        stopQrPolling();
                        onQrPhotoUploaded(data.filename);
                    } else if (data.success && data.status === 'expired') {
                        stopQrPolling();
                        showToast('Sesja QR wygasła', 'error');
                        cancelPaymentQr();
                    }
                })
                .catch(function() {});
        }, 3000);
    }

    function stopQrPolling() {
        if (qrPollInterval) {
            clearInterval(qrPollInterval);
            qrPollInterval = null;
        }
    }

    function onQrPhotoUploaded(filename) {
        qrUploadedFilename = filename;

        // Hide QR, show success
        var qrDisplay = document.getElementById('pc-qr-display');
        var qrUploaded = document.getElementById('pc-qr-uploaded');
        var filenameEl = document.getElementById('pc-qr-uploaded-filename');
        var previewContainer = document.getElementById('pc-qr-preview-image');
        var previewImg = document.getElementById('pc-qr-preview-img');

        if (qrDisplay) qrDisplay.style.display = 'none';
        if (qrUploaded) qrUploaded.style.display = '';
        if (filenameEl) filenameEl.textContent = filename.replace(/^[0-9a-f]{32}_/, '');

        // Show image preview (for JPG/PNG, not PDF)
        var isImage = /\.(jpg|jpeg|png)$/i.test(filename);
        if (isImage && previewContainer && previewImg && currentQrSessionToken) {
            previewImg.src = '/client/payment-confirmations/qr-preview/' + currentQrSessionToken;
            previewContainer.style.display = '';
        }

        // Enable submit button
        if (submitBtn) {
            submitBtn.style.display = '';
            submitBtn.disabled = false;
        }
        // Hide the "Dalej" button if visible
        var nextBtn = document.getElementById('wizard-next-btn');
        if (nextBtn) nextBtn.style.display = 'none';

        // Disconnect socket
        if (paymentSocket) {
            paymentSocket.disconnect();
            paymentSocket = null;
        }

        showToast('Potwierdzenie wgrane z telefonu!', 'success');
    }

    function cancelPaymentQr() {
        currentQrSessionToken = null;
        qrUploadedFilename = null;
        stopQrPolling();

        // Hide QR, show button + upload form again
        var qrDisplay = document.getElementById('pc-qr-display');
        var qrBtn = document.getElementById('pc-qr-btn');
        var uploadForm = document.getElementById('upload-form');
        var uploadOr = document.querySelector('.pc-upload-or');
        var qrUploaded = document.getElementById('pc-qr-uploaded');

        if (qrDisplay) qrDisplay.style.display = 'none';
        if (qrUploaded) qrUploaded.style.display = 'none';
        if (qrBtn) {
            qrBtn.style.display = '';
            qrBtn.disabled = false;
            qrBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="8" height="8" rx="1"/><rect x="14" y="2" width="8" height="8" rx="1"/><rect x="2" y="14" width="8" height="8" rx="1"/><rect x="14" y="14" width="4" height="4"/></svg> Wgraj z telefonu (QR)';
        }
        if (uploadForm) uploadForm.style.display = '';
        if (uploadOr) uploadOr.style.display = '';

        if (paymentSocket) {
            paymentSocket.disconnect();
            paymentSocket = null;
        }
    }

    function resetQrState() {
        currentQrSessionToken = null;
        qrUploadedFilename = null;
        stopQrPolling();

        var qrDisplay = document.getElementById('pc-qr-display');
        var qrBtn = document.getElementById('pc-qr-btn');
        var uploadForm = document.getElementById('upload-form');
        var uploadOr = document.querySelector('.pc-upload-or');
        var qrUploaded = document.getElementById('pc-qr-uploaded');

        if (qrDisplay) qrDisplay.style.display = 'none';
        if (qrUploaded) qrUploaded.style.display = 'none';
        if (qrBtn) {
            qrBtn.style.display = '';
            qrBtn.disabled = false;
            qrBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="8" height="8" rx="1"/><rect x="14" y="2" width="8" height="8" rx="1"/><rect x="2" y="14" width="8" height="8" rx="1"/><rect x="14" y="14" width="4" height="4"/></svg> Wgraj z telefonu (QR)';
        }
        if (uploadForm) uploadForm.style.display = '';
        if (uploadOr) uploadOr.style.display = '';

        if (paymentSocket) {
            paymentSocket.disconnect();
            paymentSocket = null;
        }
    }

    // === START ===

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            init();
        });
    } else {
        init();
    }

})();
