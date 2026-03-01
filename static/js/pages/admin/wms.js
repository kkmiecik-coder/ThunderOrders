/**
 * WMS Desktop — Picking / Packing session interface
 * =================================================
 *
 * Reads window.WMS_SESSION_DATA and window.WMS_SESSION_ID set by the template.
 * Communicates with the backend via JSON APIs + WebSocket (SocketIO).
 *
 * Flow:
 *  1. Active session → Mode selection screen (Desktop / Phone)
 *  2a. Desktop mode → Direct picking with counter panel [-] [0/2] [+] [✓]
 *  2b. Phone mode → QR pairing → Preview mode (read-only, real-time updates)
 *  3. Non-active session → Read-only picking view (no mode selection)
 */

(function () {
    'use strict';

    // ========================================
    // STATE
    // ========================================

    var sessionData = null;
    var sessionId = null;
    var ordersMap = {};
    var currentOrderId = null;
    var isSessionActive = false;
    var phoneConnected = false;
    var socket = null;
    var currentWorkMode = null; // null | 'desktop' | 'phone'
    var selectedMaterialId = null;
    var packingSuggestionsCache = {}; // {orderId: {suggestions, all_materials, total_weight}}

    // ========================================
    // HELPERS
    // ========================================

    function el(id) {
        return document.getElementById(id);
    }

    function getCSRFToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) return meta.getAttribute('content');
        var input = document.querySelector('input[name="csrf_token"]');
        if (input) return input.value;
        return '';
    }

    function showToast(message, type) {
        if (typeof window.showToast === 'function') {
            window.showToast(message, type);
        } else if (window.Toast && typeof window.Toast.show === 'function') {
            window.Toast.show(message, type);
        }
    }

    function postJSON(url, body) {
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken(),
            },
            body: JSON.stringify(body),
        }).then(function (r) { return r.json(); });
    }

    // ========================================
    // INIT
    // ========================================

    function initWmsPage() {
        sessionId = window.WMS_SESSION_ID;
        sessionData = window.WMS_SESSION_DATA;

        if (!sessionData || !sessionId) {
            console.error('WMS: brak danych sesji');
            return;
        }

        isSessionActive = sessionData.session.status === 'active';

        // Build ordersMap
        ordersMap = {};
        (sessionData.orders || []).forEach(function (o) {
            ordersMap[o.id] = o;
        });

        renderOrderQueue();
        bindHeaderActions();

        // Auto-select first non-packed order
        var orders = sessionData.orders || [];
        var first = orders.find(function (o) { return !o.packing_completed_at; }) || orders[0];
        if (first) {
            selectOrder(first.id);
        }

        if (isSessionActive) {
            // Check if phone is already connected
            if (sessionData.session.phone_connected) {
                phoneConnected = true;
                currentWorkMode = 'phone';
                connectWebSocket();
                toggleMode('preview');
                updatePhoneIndicator(true);
            } else {
                // Show mode selection, hide picking content
                showModeSelection();
            }
        }
    }

    // ========================================
    // MODE SELECTION SCREEN
    // ========================================

    function showModeSelection() {
        var modeEl = el('wmsModeSelection');
        if (modeEl) modeEl.style.display = '';
        hidePickingContent();
    }

    function hidePickingContent() {
        var header = el('wmsCurrentOrderHeader');
        var items = el('wmsItemsList');
        var pack = el('wmsPackAction');
        if (header) header.style.display = 'none';
        if (items) items.style.display = 'none';
        if (pack) pack.style.display = 'none';
    }

    function showPickingContent() {
        var header = el('wmsCurrentOrderHeader');
        var items = el('wmsItemsList');
        if (header) header.style.display = '';
        if (items) items.style.display = '';
        // Re-render current order
        if (currentOrderId) {
            selectOrder(currentOrderId);
        }
    }

    function onSelectDesktopMode() {
        currentWorkMode = 'desktop';
        var modeEl = el('wmsModeSelection');
        if (modeEl) modeEl.style.display = 'none';
        showPickingContent();
        connectWebSocket();
    }

    function onSelectPhoneMode() {
        currentWorkMode = 'phone';
        var modeEl = el('wmsModeSelection');
        if (modeEl) modeEl.style.display = 'none';
        var qrScreen = el('wmsQrScreen');
        if (qrScreen) qrScreen.style.display = '';
        loadQrCode();
        connectWebSocket();
    }

    function onQrBack() {
        var qrScreen = el('wmsQrScreen');
        if (qrScreen) qrScreen.style.display = 'none';
        currentWorkMode = null;
        showModeSelection();
    }

    // ========================================
    // QR CODE
    // ========================================

    function loadQrCode() {
        var qrContainer = el('wmsQrImage');
        var qrUrlEl = el('wmsQrUrl');

        fetch('/admin/orders/wms/' + sessionId + '/qr', {
            headers: { 'X-CSRFToken': getCSRFToken() },
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.success) {
                if (qrContainer) qrContainer.innerHTML = '<div class="wms-qr-error">Błąd generowania QR</div>';
                return;
            }
            if (qrContainer) {
                qrContainer.innerHTML = '<img src="' + data.qr_image + '" alt="QR Code" />';
            }
            if (qrUrlEl && data.mobile_url) {
                qrUrlEl.textContent = data.mobile_url;
            }
        })
        .catch(function () {
            if (qrContainer) qrContainer.innerHTML = '<div class="wms-qr-error">Błąd połączenia</div>';
        });
    }

    // ========================================
    // WEBSOCKET CLIENT
    // ========================================

    function connectWebSocket() {
        if (socket) return;
        if (typeof io === 'undefined') {
            console.warn('WMS: socket.io not loaded');
            return;
        }

        socket = io({
            reconnection: true,
            reconnectionAttempts: Infinity,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000,
        });

        socket.on('connect', function () {
            socket.emit('join_session', {
                session_id: sessionId,
                role: 'desktop',
            });
        });

        socket.on('phone_connected', handlePhoneConnected);
        socket.on('phone_disconnected', handlePhoneDisconnected);
        socket.on('item_status_updated', handleItemStatusUpdated);
        socket.on('order_picked', handleOrderPicked);
        socket.on('order_packed', handleOrderPacked);
        socket.on('session_state', handleSessionState);
        socket.on('session_progress', handleSessionProgressWS);

        socket.on('packing_photo_uploaded', handlePackingPhotoUploaded);

        socket.on('order_navigated', function(data) {
            if (data.order_id && ordersMap[data.order_id]) {
                selectOrder(data.order_id);
            }
        });

        socket.on('session_ended', function(data) {
            showToast(data.message || 'Sesja WMS została zakończona', 'info');
            setTimeout(function() {
                window.location.href = '/admin/orders';
            }, 1500);
        });

        socket.on('error', function (data) {
            console.error('WMS WebSocket error:', data.message);
        });

        socket.on('disconnect', function () {
            console.warn('WMS: WebSocket disconnected');
            showConnectionAlert();
        });

        socket.on('reconnect', function () {
            console.info('WMS: WebSocket reconnected');
            hideConnectionAlert();
        });
    }

    // ========================================
    // WEBSOCKET EVENT HANDLERS
    // ========================================

    function handlePhoneConnected(data) {
        phoneConnected = true;

        // Hide QR screen if visible
        var qrScreen = el('wmsQrScreen');
        if (qrScreen) qrScreen.style.display = 'none';

        // Hide mode selection if still visible
        var modeEl = el('wmsModeSelection');
        if (modeEl) modeEl.style.display = 'none';

        // Show picking content
        showPickingContent();

        // Auto-switch to preview mode if phone mode was selected
        if (currentWorkMode === 'phone') {
            toggleMode('preview');
        }

        updatePhoneIndicator(true);
        showToast('Telefon połączony!', 'success');
    }

    function handlePhoneDisconnected(data) {
        phoneConnected = false;
        updatePhoneIndicator(false);
        showToast('Telefon rozłączony', 'warning');
    }

    function handleItemStatusUpdated(data) {
        var itemData = data.item;
        var orderData = data.order;
        var sessionProgress = data.session;

        // Update local state
        var order = ordersMap[orderData.id];
        if (order) {
            order.is_picked = orderData.is_picked;
            order.picked_percentage = orderData.picked_percentage;
            order.picked_quantity = orderData.picked_quantity;
            order.total_quantity = orderData.total_quantity;

            var localItem = (order.items || []).find(function (i) { return i.id === itemData.id; });
            if (localItem) {
                localItem.wms_status = itemData.wms_status;
                localItem.wms_status_name = itemData.wms_status_name;
                localItem.wms_status_color = itemData.wms_status_color;
                localItem.is_picked = itemData.is_picked;
                localItem.picked_at = itemData.picked_at;
                localItem.picked_quantity = itemData.picked_quantity;
            }
        }

        // Update DOM — item card
        updateItemCardDOM(itemData.id, itemData);

        // Flash animation for WebSocket updates
        flashItemCard(itemData.id);

        // Update order progress
        if (order) {
            updateOrderProgressBar(order);
            updatePackAction(order);
        }

        // Update queue card
        updateQueueCard(orderData.id);

        // Update session progress
        if (sessionProgress) {
            updateSessionProgress(sessionProgress);
        }

        // Update preview mode if active
        refreshPreviewIfVisible();
    }

    function handleOrderPicked(data) {
        var orderData = data.order;
        updateQueueCard(orderData.id);
        refreshPreviewIfVisible();
    }

    function handleOrderPacked(data) {
        var orderData = data.order;
        var sessionProgress = data.session;

        var order = ordersMap[orderData.id];
        if (order) {
            order.packing_completed_at = orderData.packed_at;
            order.status = orderData.status;
            order.status_display_name = orderData.status_display_name;
            if (orderData.packaging_material_name) {
                order.packaging_material_name = orderData.packaging_material_name;
            }
            if (orderData.total_package_weight) {
                order.total_package_weight = orderData.total_package_weight;
            }
        }

        updateQueueCard(orderData.id);

        if (sessionProgress) {
            updateSessionProgress(sessionProgress);
        }

        if (data.low_stock_warning) {
            showToast(data.low_stock_warning, 'warning');
        }

        showToast('Zamówienie ' + (orderData.order_number || '') + ' spakowane!', 'success');

        // Re-render current order if it was packed
        if (currentOrderId === orderData.id) {
            selectOrder(currentOrderId);
        }

        autoAdvanceToNextOrder(orderData.id);
        refreshPreviewIfVisible();
    }

    function handleSessionState(data) {
        // Full state refresh (after join/reconnect)
        sessionData = data;
        ordersMap = {};
        (data.orders || []).forEach(function (o) {
            ordersMap[o.id] = o;
        });

        renderOrderQueue();

        // Re-select current order or first non-packed
        var orders = data.orders || [];
        var target = null;
        if (currentOrderId && ordersMap[currentOrderId]) {
            target = ordersMap[currentOrderId];
        } else {
            target = orders.find(function (o) { return !o.packing_completed_at; }) || orders[0];
        }
        if (target) {
            selectOrder(target.id);
        }

        updateSessionProgress({
            packed_orders_count: data.session.packed_orders_count,
            progress_percentage: data.session.progress_percentage,
        });

        refreshPreviewIfVisible();
    }

    function handleSessionProgressWS(data) {
        updateSessionProgress(data);
    }

    // ========================================
    // PHONE INDICATOR
    // ========================================

    function updatePhoneIndicator(connected) {
        var indicator = el('wmsPhoneIndicator');
        var dot = el('wmsPhoneDot');
        var text = el('wmsPhoneText');

        if (indicator) {
            indicator.style.display = '';
            indicator.classList.toggle('disconnected', !connected);
        }
        if (dot) {
            dot.className = 'wms-phone-dot ' + (connected ? 'connected' : 'disconnected');
        }
        if (text) {
            text.textContent = connected ? 'Telefon połączony' : 'Telefon rozłączony';
        }
    }

    // ========================================
    // FLASH ANIMATION (WebSocket updates)
    // ========================================

    function flashItemCard(itemId) {
        var card = document.querySelector('.wms-item-card[data-item-id="' + itemId + '"]');
        if (!card) return;
        card.classList.remove('ws-flash');
        void card.offsetWidth; // force reflow to restart animation
        card.classList.add('ws-flash');
    }

    // ========================================
    // ORDER QUEUE (left panel)
    // ========================================

    function renderOrderQueue() {
        var list = el('wmsQueueList');
        var countEl = el('wmsQueueCount');
        if (!list) return;

        list.innerHTML = '';
        var orders = sessionData.orders || [];
        if (countEl) countEl.textContent = orders.length;

        // Group orders by shipping_request if available
        var hasSR = orders.some(function (o) { return o.shipping_request; });

        if (hasSR) {
            var grouped = {};
            var noSR = [];
            orders.forEach(function (o) {
                if (o.shipping_request) {
                    var srId = o.shipping_request.id;
                    if (!grouped[srId]) grouped[srId] = { sr: o.shipping_request, orders: [] };
                    grouped[srId].orders.push(o);
                } else {
                    noSR.push(o);
                }
            });

            Object.keys(grouped).forEach(function (srId) {
                var group = grouped[srId];
                var groupEl = createSRGroupHeader(group.sr);
                list.appendChild(groupEl);
                group.orders.forEach(function (o) {
                    list.appendChild(createOrderCard(o));
                });
            });

            noSR.forEach(function (o) {
                list.appendChild(createOrderCard(o));
            });
        } else {
            orders.forEach(function (o) {
                list.appendChild(createOrderCard(o));
            });
        }
    }

    function createSRGroupHeader(sr) {
        var tpl = el('tplWmsSrGroup');
        var clone = tpl.content.cloneNode(true);
        var groupEl = clone.querySelector('.wms-sr-group');
        groupEl.setAttribute('data-sr-id', sr.id);
        groupEl.querySelector('.wms-sr-group-number').textContent = sr.request_number;
        return groupEl;
    }

    function createOrderCard(order) {
        var tpl = el('tplWmsOrderCard');
        var clone = tpl.content.cloneNode(true);
        var card = clone.querySelector('.wms-order-card');

        card.setAttribute('data-order-id', order.id);
        if (order.shipping_request) {
            card.setAttribute('data-sr-id', order.shipping_request.id);
        }

        card.querySelector('.wms-order-card-number').textContent = order.order_number;
        card.querySelector('.wms-order-card-customer').textContent = order.customer_name || '-';
        card.querySelector('.wms-order-card-items-count').textContent = order.items_count + ' poz.';

        updateOrderCardProgress(card, order);

        card.addEventListener('click', function () {
            selectOrder(order.id);
        });

        return card;
    }

    function updateOrderCardProgress(card, order) {
        var pct = order.picked_percentage || 0;
        var fill = card.querySelector('.wms-progress-fill');
        var pctEl = card.querySelector('.wms-order-card-percentage');
        var indicator = card.querySelector('.wms-order-card-indicator');

        if (fill) fill.style.width = pct + '%';
        if (pctEl) pctEl.textContent = Math.round(pct) + '%';

        if (indicator) {
            indicator.className = 'wms-order-card-indicator';
            if (order.packing_completed_at) {
                indicator.classList.add('packed');
            } else if (order.is_picked) {
                indicator.classList.add('picked');
            } else if (pct > 0) {
                indicator.classList.add('picking');
            }
        }

        card.classList.toggle('packed', !!order.packing_completed_at);

        if (fill && pct >= 100) {
            fill.classList.add('complete');
        } else if (fill) {
            fill.classList.remove('complete');
        }
    }

    // ========================================
    // SELECT ORDER (right panel)
    // ========================================

    function selectOrder(orderId) {
        var order = ordersMap[orderId];
        if (!order) return;

        currentOrderId = orderId;

        // Highlight card in queue
        document.querySelectorAll('.wms-order-card').forEach(function (c) {
            c.classList.toggle('active', parseInt(c.getAttribute('data-order-id')) === orderId);
        });

        // Update header
        var numEl = el('wmsCurrentOrderNumber');
        var custEl = el('wmsCurrentOrderCustomer');
        var srEl = el('wmsCurrentOrderSR');

        if (numEl) numEl.textContent = order.order_number;
        if (custEl) custEl.textContent = order.customer_name || '-';
        if (srEl) {
            if (order.shipping_request) {
                srEl.textContent = 'SR: ' + order.shipping_request.request_number;
            } else {
                srEl.textContent = '';
            }
        }

        renderItems(order);
        updateOrderProgressBar(order);
        updatePackAction(order);
    }

    function renderItems(order) {
        var list = el('wmsItemsList');
        var emptyEl = el('wmsItemsEmpty');
        if (!list) return;

        // Remove old item cards (keep empty placeholder)
        list.querySelectorAll('.wms-item-card').forEach(function (el) { el.remove(); });

        var items = order.items || [];
        if (items.length === 0) {
            if (emptyEl) emptyEl.style.display = '';
            return;
        }
        if (emptyEl) emptyEl.style.display = 'none';

        var isPacked = !!order.packing_completed_at;

        items.forEach(function (item) {
            var card = createItemCard(item, isPacked);
            list.appendChild(card);
        });
    }

    function createItemCard(item, isPacked) {
        var tpl = el('tplWmsItemCard');
        var clone = tpl.content.cloneNode(true);
        var card = clone.querySelector('.wms-item-card');

        card.setAttribute('data-item-id', item.id);

        // Image
        var img = card.querySelector('.wms-item-image img');
        if (img) {
            img.src = item.product_image_url || '/static/images/placeholder.png';
            img.alt = item.product_name || '';
        }

        // Info
        card.querySelector('.wms-item-name').textContent = item.product_name || '-';
        card.querySelector('.wms-item-sku').textContent = item.product_sku || '';

        // Status badge
        var badge = card.querySelector('.wms-item-status-badge');
        if (badge) {
            badge.textContent = item.wms_status_name || item.wms_status || '-';
            badge.style.backgroundColor = item.wms_status_color || '#9ca3af';
        }

        // Card state classes
        var pickedQty = item.picked_quantity || 0;
        if (pickedQty >= item.quantity) {
            card.classList.add('picked');
        } else if (pickedQty > 0) {
            card.classList.add('partial');
        }

        if (isPacked) {
            card.classList.add('packed');
        }

        buildPickCounter(card, item, isPacked);

        return card;
    }

    // ========================================
    // PICK COUNTER PANEL  [-] [0/2] [+] [✓]
    // ========================================

    function buildPickCounter(card, item, isPacked) {
        var counter = card.querySelector('.wms-pick-counter');
        if (!counter) return;

        var display = counter.querySelector('.wms-pick-display');
        var decBtn = counter.querySelector('.wms-pick-decrement');
        var incBtn = counter.querySelector('.wms-pick-increment');
        var allBtn = counter.querySelector('.wms-pick-all');

        var pickedQty = item.picked_quantity || 0;
        var totalQty = item.quantity;

        if (display) display.textContent = pickedQty + '/' + totalQty;

        // Counter state class
        counter.className = 'wms-pick-counter';
        if (pickedQty >= totalQty) {
            counter.classList.add('complete');
        } else if (pickedQty > 0) {
            counter.classList.add('partial');
        }

        // Disable buttons based on state
        var disableAll = isPacked || !isSessionActive;
        if (decBtn) decBtn.disabled = pickedQty <= 0 || disableAll;
        if (incBtn) incBtn.disabled = pickedQty >= totalQty || disableAll;
        if (allBtn) allBtn.disabled = pickedQty >= totalQty || disableAll;

        if (disableAll) return;

        // Event listeners
        if (decBtn) {
            decBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                if (!decBtn.disabled) updateItemStatus(item.id, 'decrement');
            });
        }

        if (incBtn) {
            incBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                if (!incBtn.disabled) updateItemStatus(item.id, 'increment');
            });
        }

        if (allBtn) {
            allBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                if (!allBtn.disabled) updateItemStatus(item.id, 'pick_all');
            });
        }
    }

    // ========================================
    // UPDATE ITEM STATUS (AJAX — desktop picking)
    // ========================================

    function updateItemStatus(orderItemId, action) {
        postJSON('/admin/orders/wms/update-item-status', {
            order_item_id: orderItemId,
            action: action,
        }).then(function (result) {
            if (!result.success) {
                showToast(result.message || 'Błąd zmiany statusu', 'error');
                return;
            }

            var itemResult = result.item;
            var orderResult = result.order;
            var sessionResult = result.session;

            // Update local state
            var order = ordersMap[orderResult.id];
            if (order) {
                order.is_picked = orderResult.is_picked;
                order.picked_percentage = orderResult.picked_percentage;
                order.picked_quantity = orderResult.picked_quantity;
                order.total_quantity = orderResult.total_quantity;

                var localItem = order.items.find(function (i) { return i.id === itemResult.id; });
                if (localItem) {
                    localItem.wms_status = itemResult.wms_status;
                    localItem.wms_status_name = itemResult.wms_status_name;
                    localItem.wms_status_color = itemResult.wms_status_color;
                    localItem.is_picked = itemResult.is_picked;
                    localItem.picked_at = itemResult.picked_at;
                    localItem.picked_quantity = itemResult.picked_quantity;
                }
            }

            // Update DOM
            updateItemCardDOM(orderItemId, itemResult);

            if (order) {
                updateOrderProgressBar(order);
                updatePackAction(order);
            }

            updateQueueCard(orderResult.id);

            if (sessionResult) {
                updateSessionProgress(sessionResult);
            }

        }).catch(function (err) {
            console.error('WMS updateItemStatus error:', err);
            showToast('Błąd połączenia', 'error');
        });
    }

    function updateItemCardDOM(itemId, itemResult) {
        var card = document.querySelector('.wms-item-card[data-item-id="' + itemId + '"]');
        if (!card) return;

        // Badge
        var badge = card.querySelector('.wms-item-status-badge');
        if (badge) {
            badge.textContent = itemResult.wms_status_name;
            badge.style.backgroundColor = itemResult.wms_status_color || '#9ca3af';
        }

        // Counter display
        var display = card.querySelector('.wms-pick-display');
        if (display) {
            display.textContent = itemResult.picked_quantity + '/' + itemResult.quantity;
        }

        // Counter state class
        var counter = card.querySelector('.wms-pick-counter');
        if (counter) {
            counter.className = 'wms-pick-counter';
            if (itemResult.picked_quantity >= itemResult.quantity) {
                counter.classList.add('complete');
            } else if (itemResult.picked_quantity > 0) {
                counter.classList.add('partial');
            }
        }

        // Button disabled states
        var decBtn = card.querySelector('.wms-pick-decrement');
        var incBtn = card.querySelector('.wms-pick-increment');
        var allBtn = card.querySelector('.wms-pick-all');
        if (decBtn) decBtn.disabled = itemResult.picked_quantity <= 0;
        if (incBtn) incBtn.disabled = itemResult.picked_quantity >= itemResult.quantity;
        if (allBtn) allBtn.disabled = itemResult.picked_quantity >= itemResult.quantity;

        // Card state classes
        card.classList.remove('picked', 'partial');
        if (itemResult.is_picked) {
            card.classList.add('picked');
        } else if (itemResult.picked_quantity > 0) {
            card.classList.add('partial');
        }
    }

    // ========================================
    // PROGRESS BARS
    // ========================================

    function updateOrderProgressBar(order) {
        var items = order.items || [];
        var totalQty = items.reduce(function (sum, i) { return sum + i.quantity; }, 0);
        var pickedQty = items.reduce(function (sum, i) { return sum + (i.picked_quantity || 0); }, 0);
        var pct = totalQty > 0 ? Math.round((pickedQty / totalQty) * 100) : 0;

        var textEl = el('wmsOrderProgressText');
        var fillEl = el('wmsOrderProgressFill');

        if (textEl) textEl.textContent = pickedQty + ' / ' + totalQty + ' szt. zebranych';
        if (fillEl) {
            fillEl.style.width = pct + '%';
            fillEl.classList.toggle('complete', pct >= 100);
        }

        order.picked_percentage = pct;
        order.is_picked = pickedQty >= totalQty && totalQty > 0;
    }

    function updateQueueCard(orderId) {
        var order = ordersMap[orderId];
        if (!order) return;

        var card = document.querySelector('.wms-order-card[data-order-id="' + orderId + '"]');
        if (!card) return;

        updateOrderCardProgress(card, order);
    }

    function updateSessionProgress(sessionResult) {
        var packedEl = el('wmsPackedCount');
        var totalEl = el('wmsTotalCount');
        var fillEl = el('wmsProgressFill');

        if (packedEl) packedEl.textContent = sessionResult.packed_orders_count;
        if (totalEl) totalEl.textContent = sessionData.session.orders_count;
        if (fillEl) {
            fillEl.style.width = sessionResult.progress_percentage + '%';
            fillEl.classList.toggle('complete', sessionResult.progress_percentage >= 100);
        }

        sessionData.session.packed_orders_count = sessionResult.packed_orders_count;
        if (sessionResult.picked_orders_count !== undefined) {
            sessionData.session.picked_orders_count = sessionResult.picked_orders_count;
        }
        sessionData.session.progress_percentage = sessionResult.progress_percentage;
    }

    // ========================================
    // PACKING PHOTO (from mobile upload)
    // ========================================

    function handlePackingPhotoUploaded(data) {
        var orderId = data.order_id;
        var photoUrl = data.photo_url;

        // Store photo URL on local order object
        var order = ordersMap[orderId];
        if (order) {
            order.packing_photo_url = photoUrl;
        }

        // Update UI if this is the currently viewed order
        if (currentOrderId === orderId) {
            showPackingPhoto(photoUrl);
        }

        showToast('Zdjęcie paczki przesłane z telefonu', 'info');
        refreshPreviewIfVisible();
    }

    function showPackingPhoto(photoUrl) {
        var container = el('wmsPackingPhoto');
        var thumb = el('wmsPackingPhotoThumb');
        var img = el('wmsPackingPhotoImg');
        var emailLabel = el('wmsEmailLabel');

        if (container && thumb && img && photoUrl) {
            img.src = photoUrl;
            thumb.href = photoUrl;
            container.style.display = '';
            if (emailLabel) emailLabel.style.display = '';
        }
    }

    function hidePackingPhoto() {
        var container = el('wmsPackingPhoto');
        var emailLabel = el('wmsEmailLabel');
        if (container) container.style.display = 'none';
        if (emailLabel) emailLabel.style.display = 'none';
    }

    // ========================================
    // PACK ORDER
    // ========================================

    function updatePackAction(order) {
        var packAction = el('wmsPackAction');
        var packBtn = el('btnPackOrder');
        if (!packAction || !packBtn) return;

        if (!isSessionActive || order.packing_completed_at) {
            packAction.style.display = 'none';
            hidePackingPhoto();
            return;
        }

        if (order.is_picked) {
            packAction.style.display = '';
            packBtn.disabled = false;
            fetchPackingSuggestions(order.id);

            // Show packing photo if available
            if (order.packing_photo_url) {
                showPackingPhoto(order.packing_photo_url);
            } else {
                hidePackingPhoto();
            }
        } else {
            packAction.style.display = 'none';
            packBtn.disabled = true;
            hidePackingPhoto();
        }
    }

    // ========================================
    // PACKAGING SUGGESTIONS
    // ========================================

    function fetchPackingSuggestions(orderId) {
        // Use cache if available
        if (packingSuggestionsCache[orderId]) {
            renderPackingSuggestions(orderId, packingSuggestionsCache[orderId]);
            return;
        }

        var loadingEl = el('wmsPackingSuggestionsLoading');
        if (loadingEl) loadingEl.style.display = '';

        fetch('/api/orders/wms/suggest-packaging/' + orderId, {
            headers: { 'X-CSRFToken': getCSRFToken() },
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (loadingEl) loadingEl.style.display = 'none';
            if (!data.success) return;

            packingSuggestionsCache[orderId] = data;
            renderPackingSuggestions(orderId, data);
        })
        .catch(function () {
            if (loadingEl) loadingEl.style.display = 'none';
        });
    }

    function renderPackingSuggestions(orderId, data) {
        var container = el('wmsPackingSuggestions');
        var warningsEl = el('wmsPackingWarnings');
        var selectEl = el('wmsPackingMaterialSelect');
        var weightInput = el('wmsPackingWeight');

        if (!container) return;

        // Reset selection
        selectedMaterialId = null;

        // Warnings
        if (warningsEl) {
            warningsEl.innerHTML = '';
            (data.warnings || []).forEach(function (w) {
                var span = document.createElement('span');
                span.className = 'wms-packing-warning-badge';
                span.textContent = w;
                warningsEl.appendChild(span);
            });
        }

        // Remove old suggestion cards (keep loading element)
        container.querySelectorAll('.packing-suggestion-card').forEach(function (c) { c.remove(); });

        // Render suggestion cards
        var suggestions = data.suggestions || [];
        if (suggestions.length === 0) {
            var empty = document.createElement('div');
            empty.className = 'packing-suggestion-card packing-suggestion-empty';
            empty.textContent = 'Brak sugestii — wybierz materiał ręcznie';
            container.appendChild(empty);
        } else {
            suggestions.forEach(function (s) {
                var card = document.createElement('div');
                card.className = 'packing-suggestion-card';
                card.setAttribute('data-material-id', s.id);

                var scorePercent = Math.round(s.fit_score * 100);

                card.innerHTML =
                    '<div class="suggestion-card-header">' +
                        '<span class="suggestion-name">' + escapeHtml(s.name) + '</span>' +
                        '<span class="suggestion-score" title="Dopasowanie">' + scorePercent + '%</span>' +
                    '</div>' +
                    '<div class="suggestion-card-details">' +
                        '<span class="suggestion-type">' + escapeHtml(s.type_display) + '</span>' +
                        (s.dimensions_display ? '<span class="suggestion-dims">' + escapeHtml(s.dimensions_display) + '</span>' : '') +
                        (s.own_weight ? '<span class="suggestion-weight">' + s.own_weight + ' kg</span>' : '') +
                        (s.cost ? '<span class="suggestion-cost">' + s.cost.toFixed(2) + ' zł</span>' : '') +
                    '</div>' +
                    (s.is_low_stock ? '<span class="suggestion-low-stock">Niski stan!</span>' : '');

                card.addEventListener('click', function () {
                    selectPackingMaterial(s.id, container, selectEl);
                });

                container.appendChild(card);
            });
        }

        // Populate dropdown
        if (selectEl) {
            // Remove old options except first
            while (selectEl.options.length > 1) selectEl.remove(1);

            (data.all_materials || []).forEach(function (m) {
                var opt = document.createElement('option');
                opt.value = m.id;
                opt.textContent = m.name + (m.dimensions_display ? ' (' + m.dimensions_display + ')' : '') +
                    (m.is_low_stock ? ' ⚠️' : '');
                selectEl.appendChild(opt);
            });

            selectEl.value = '';
            selectEl.addEventListener('change', function () {
                var val = parseInt(selectEl.value) || null;
                selectedMaterialId = val;
                // Deselect suggestion cards
                container.querySelectorAll('.packing-suggestion-card').forEach(function (c) {
                    c.classList.remove('suggestion-selected');
                });
            });
        }

        // Pre-fill weight
        if (weightInput && data.total_weight) {
            weightInput.value = data.total_weight.toFixed(2);
        }
    }

    function selectPackingMaterial(materialId, container, selectEl) {
        selectedMaterialId = materialId;

        // Highlight card
        container.querySelectorAll('.packing-suggestion-card').forEach(function (c) {
            c.classList.toggle('suggestion-selected',
                parseInt(c.getAttribute('data-material-id')) === materialId);
        });

        // Sync dropdown
        if (selectEl) selectEl.value = materialId;
    }

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function packOrder(orderId) {
        var order = ordersMap[orderId];
        if (!order) return;

        // Get selected material from dropdown or suggestion card
        var selectEl = el('wmsPackingMaterialSelect');
        var materialId = selectedMaterialId || (selectEl ? parseInt(selectEl.value) || null : null);

        var weightInput = el('wmsPackingWeight');
        var weight = weightInput ? parseFloat(weightInput.value) || null : null;

        var sendEmailCheckbox = el('wmsSendEmailCheckbox');
        var sendEmail = sendEmailCheckbox ? sendEmailCheckbox.checked : false;

        if (!confirm('Czy na pewno oznaczyć zamówienie ' + order.order_number + ' jako spakowane?')) {
            return;
        }

        var body = { order_id: orderId };
        if (materialId) body.packaging_material_id = materialId;
        if (weight) body.total_package_weight = weight;
        if (sendEmail && order.packing_photo_url) body.send_email = true;

        var packBtn = el('btnPackOrder');
        setButtonLoading(packBtn, true);

        postJSON('/admin/orders/wms/' + sessionId + '/pack-order', body).then(function (result) {
            setButtonLoading(packBtn, false);
            if (!result.success) {
                showToast(result.message || 'Błąd pakowania', 'error');
                return;
            }

            order.packing_completed_at = result.order.packed_at;
            order.status = result.order.status;
            order.status_display_name = result.order.status_display_name;

            // Reset packing state
            selectedMaterialId = null;
            delete packingSuggestionsCache[orderId];

            updateQueueCard(orderId);

            if (result.session) {
                updateSessionProgress(result.session);
            }

            if (result.low_stock_warning) {
                showToast(result.low_stock_warning, 'warning');
            }

            showToast(result.message || 'Zamówienie spakowane!', 'success');

            selectOrder(orderId);
            autoAdvanceToNextOrder(orderId);

        }).catch(function (err) {
            setButtonLoading(packBtn, false);
            console.error('WMS packOrder error:', err);
            showToast('Błąd połączenia', 'error');
        });
    }

    function autoAdvanceToNextOrder(packedOrderId) {
        var orders = sessionData.orders || [];
        var next = orders.find(function (o) {
            return o.id !== packedOrderId && !o.packing_completed_at;
        });

        if (next) {
            selectOrder(next.id);
        }
    }

    // ========================================
    // SESSION ACTIONS (complete / cancel)
    // ========================================

    function completeSession() {
        if (!confirm('Czy na pewno zakończyć sesję WMS?')) return;

        postJSON('/admin/orders/wms/' + sessionId + '/complete', {}).then(function (result) {
            if (result.success) {
                showToast(result.message || 'Sesja zakończona', 'success');
                if (result.redirect_url) {
                    window.location.href = result.redirect_url;
                }
            } else {
                showToast(result.message || 'Błąd zakończenia sesji', 'error');
            }
        }).catch(function (err) {
            console.error('WMS completeSession error:', err);
            showToast('Błąd połączenia', 'error');
        });
    }

    function cancelSession() {
        if (!confirm('Czy na pewno anulować sesję WMS? Zamówienia zostaną odblokowane.')) return;

        postJSON('/admin/orders/wms/' + sessionId + '/cancel', {}).then(function (result) {
            if (result.success) {
                showToast(result.message || 'Sesja anulowana', 'success');
                if (result.redirect_url) {
                    window.location.href = result.redirect_url;
                }
            } else {
                showToast(result.message || 'Błąd anulowania sesji', 'error');
            }
        }).catch(function (err) {
            console.error('WMS cancelSession error:', err);
            showToast('Błąd połączenia', 'error');
        });
    }

    // ========================================
    // MODE TOGGLE (picking / preview)
    // ========================================

    var previewTimerInterval = null;

    function toggleMode(mode) {
        var pickingMode = el('wmsPickingMode');
        var previewContainer = el('wmsPreviewContainer');
        var btnPicking = el('btnModePicking');
        var btnPreview = el('btnModePreview');

        if (mode === 'preview') {
            if (pickingMode) pickingMode.style.display = 'none';
            if (previewContainer) previewContainer.style.display = '';
            if (btnPicking) btnPicking.classList.remove('active');
            if (btnPreview) btnPreview.classList.add('active');
            renderPreviewMode();
            startPreviewTimer();
        } else {
            if (pickingMode) pickingMode.style.display = '';
            if (previewContainer) previewContainer.style.display = 'none';
            if (btnPicking) btnPicking.classList.add('active');
            if (btnPreview) btnPreview.classList.remove('active');
            stopPreviewTimer();
        }
    }

    // ========================================
    // PREVIEW MODE
    // ========================================

    function renderPreviewMode() {
        renderPreviewStats();
        renderPreviewGrid();
    }

    function renderPreviewStats() {
        var orders = sessionData.orders || [];
        var totalItems = 0;
        var pickedItems = 0;
        var packedOrders = 0;

        orders.forEach(function (o) {
            totalItems += (o.total_quantity || 0);
            pickedItems += (o.picked_quantity || 0);
            if (o.packing_completed_at) packedOrders++;
        });

        var totalItemsEl = el('previewTotalItems');
        var pickedItemsEl = el('previewPickedItems');
        var packedOrdersEl = el('previewPackedOrders');

        if (totalItemsEl) totalItemsEl.textContent = totalItems;
        if (pickedItemsEl) pickedItemsEl.textContent = pickedItems;
        if (packedOrdersEl) packedOrdersEl.textContent = packedOrders + ' / ' + orders.length;
    }

    function renderPreviewGrid() {
        var grid = el('wmsPreviewGrid');
        if (!grid) return;

        grid.innerHTML = '';
        var orders = sessionData.orders || [];

        orders.forEach(function (order) {
            var card = document.createElement('div');
            card.className = 'wms-preview-card';
            card.setAttribute('data-order-id', order.id);

            var isPacked = !!order.packing_completed_at;
            var isPicked = order.is_picked;
            var pct = order.picked_percentage || 0;

            if (isPacked) card.classList.add('packed');
            else if (isPicked) card.classList.add('picked');
            else if (pct > 0) card.classList.add('picking');

            var statusText = isPacked ? 'Spakowane' : (isPicked ? 'Zebrane' : (pct > 0 ? 'Zbieranie' : 'Oczekuje'));
            var statusClass = isPacked ? 'packed' : (isPicked ? 'picked' : (pct > 0 ? 'picking' : 'pending'));

            var photoHtml = '';
            if (order.packing_photo_url) {
                photoHtml = '<div class="wms-preview-card-photo">' +
                    '<img src="' + order.packing_photo_url + '" alt="Zdjęcie paczki" loading="lazy">' +
                '</div>';
            }

            card.innerHTML =
                '<div class="wms-preview-card-header">' +
                    '<span class="wms-preview-card-number">' + order.order_number + '</span>' +
                    '<span class="wms-preview-card-status ' + statusClass + '">' + statusText + '</span>' +
                '</div>' +
                '<div class="wms-preview-card-customer">' + (order.customer_name || '-') + '</div>' +
                '<div class="wms-preview-card-progress">' +
                    '<div class="wms-progress-bar wms-progress-bar-sm">' +
                        '<div class="wms-progress-fill' + (pct >= 100 ? ' complete' : '') + '" style="width: ' + pct + '%;"></div>' +
                    '</div>' +
                    '<span class="wms-preview-card-pct">' + Math.round(pct) + '%</span>' +
                '</div>' +
                '<div class="wms-preview-card-meta">' +
                    '<span>' + (order.picked_quantity || 0) + ' / ' + (order.total_quantity || 0) + ' szt.</span>' +
                    (order.shipping_request ? '<span class="wms-preview-card-sr">SR: ' + order.shipping_request.request_number + '</span>' : '') +
                '</div>' +
                photoHtml;

            grid.appendChild(card);
        });
    }

    function startPreviewTimer() {
        if (previewTimerInterval) return;
        updatePreviewElapsed();
        previewTimerInterval = setInterval(updatePreviewElapsed, 1000);
    }

    function stopPreviewTimer() {
        if (previewTimerInterval) {
            clearInterval(previewTimerInterval);
            previewTimerInterval = null;
        }
    }

    function updatePreviewElapsed() {
        var timerEl = el('previewElapsedTime');
        if (!timerEl || !sessionData || !sessionData.session || !sessionData.session.created_at) return;

        var start = new Date(sessionData.session.created_at);
        var now = new Date();
        var diff = Math.max(0, Math.floor((now - start) / 1000));

        var hrs = Math.floor(diff / 3600);
        var mins = Math.floor((diff % 3600) / 60);
        var secs = diff % 60;

        if (hrs > 0) {
            timerEl.textContent = hrs + ':' + pad2(mins) + ':' + pad2(secs);
        } else {
            timerEl.textContent = pad2(mins) + ':' + pad2(secs);
        }
    }

    function pad2(n) {
        return n < 10 ? '0' + n : '' + n;
    }

    function refreshPreviewIfVisible() {
        var previewContainer = el('wmsPreviewContainer');
        if (previewContainer && previewContainer.style.display !== 'none') {
            renderPreviewMode();
        }
    }

    // ========================================
    // HEADER EVENT BINDINGS
    // ========================================

    function bindHeaderActions() {
        // Mode toggle (picking/preview in header)
        var btnPicking = el('btnModePicking');
        var btnPreview = el('btnModePreview');
        if (btnPicking) btnPicking.addEventListener('click', function () { toggleMode('picking'); });
        if (btnPreview) btnPreview.addEventListener('click', function () { toggleMode('preview'); });

        // Session actions
        var btnComplete = el('btnCompleteSession');
        var btnCancel = el('btnCancelSession');
        if (btnComplete) btnComplete.addEventListener('click', completeSession);
        if (btnCancel) btnCancel.addEventListener('click', cancelSession);

        // Pack order button
        var btnPack = el('btnPackOrder');
        if (btnPack) {
            btnPack.addEventListener('click', function () {
                if (currentOrderId) packOrder(currentOrderId);
            });
        }

        // Mode selection buttons
        var btnDesktop = el('btnModeDesktop');
        var btnPhone = el('btnModePhone');
        var btnQrBackEl = el('btnQrBack');
        if (btnDesktop) btnDesktop.addEventListener('click', onSelectDesktopMode);
        if (btnPhone) btnPhone.addEventListener('click', onSelectPhoneMode);
        if (btnQrBackEl) btnQrBackEl.addEventListener('click', onQrBack);

        // Disable action buttons for non-active sessions
        if (!isSessionActive) {
            if (btnComplete) btnComplete.disabled = true;
            if (btnCancel) btnCancel.disabled = true;
        }
    }

    // ========================================
    // KEYBOARD SHORTCUTS
    // ========================================

    function bindKeyboardShortcuts() {
        document.addEventListener('keydown', function (e) {
            // Skip if focus is in an input/textarea/select
            var tag = (e.target.tagName || '').toLowerCase();
            if (tag === 'input' || tag === 'textarea' || tag === 'select') return;

            var orders = sessionData ? (sessionData.orders || []) : [];
            if (orders.length === 0) return;

            if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
                e.preventDefault();
                var idx = orders.findIndex(function (o) { return o.id === currentOrderId; });
                if (idx === -1) idx = 0;

                if (e.key === 'ArrowLeft') {
                    idx = Math.max(0, idx - 1);
                } else {
                    idx = Math.min(orders.length - 1, idx + 1);
                }
                selectOrder(orders[idx].id);
            }

            // Enter — trigger packing if order is fully picked
            if (e.key === 'Enter' && currentOrderId && isSessionActive) {
                var order = ordersMap[currentOrderId];
                if (order && order.is_picked && !order.packing_completed_at) {
                    e.preventDefault();
                    packOrder(currentOrderId);
                }
            }
        });
    }

    // ========================================
    // LOADING STATES
    // ========================================

    function setButtonLoading(btn, loading) {
        if (!btn) return;
        if (loading) {
            btn.disabled = true;
            btn.setAttribute('data-original-text', btn.innerHTML);
            btn.innerHTML = '<span class="wms-btn-spinner"></span> Ładowanie...';
        } else {
            btn.disabled = false;
            var orig = btn.getAttribute('data-original-text');
            if (orig) btn.innerHTML = orig;
        }
    }

    // ========================================
    // WEBSOCKET CONNECTION ALERT
    // ========================================

    function setupConnectionAlert() {
        var alertEl = document.createElement('div');
        alertEl.className = 'wms-connection-alert';
        alertEl.id = 'wmsConnectionAlert';
        alertEl.style.display = 'none';
        alertEl.innerHTML =
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
                '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>' +
                '<line x1="12" y1="9" x2="12" y2="13"></line>' +
                '<line x1="12" y1="17" x2="12.01" y2="17"></line>' +
            '</svg>' +
            '<span>Utracono połączenie z serwerem. Próba ponownego połączenia...</span>';

        var header = document.querySelector('.wms-header');
        if (header) {
            header.parentNode.insertBefore(alertEl, header.nextSibling);
        }
    }

    function showConnectionAlert() {
        var alertEl = el('wmsConnectionAlert');
        if (alertEl) alertEl.style.display = '';
    }

    function hideConnectionAlert() {
        var alertEl = el('wmsConnectionAlert');
        if (alertEl) alertEl.style.display = 'none';
    }

    // ========================================
    // BOOT
    // ========================================

    document.addEventListener('DOMContentLoaded', function () {
        initWmsPage();
        bindKeyboardShortcuts();
        setupConnectionAlert();
    });

})();
