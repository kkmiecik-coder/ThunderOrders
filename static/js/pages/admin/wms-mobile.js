/**
 * WMS Mobile — Picking interface for phone
 * ==========================================
 *
 * Standalone mobile page connected via WebSocket.
 * Reads window.WMS_SESSION_TOKEN, WMS_SESSION_DATA, WMS_SESSION_ID.
 *
 * Counter panel: [-] [0/2] [+] [✓]
 * WebSocket events: join_session, update_item_status, mark_order_packed
 */

(function () {
    'use strict';

    // ========================================
    // STATE
    // ========================================

    var sessionToken = null;
    var sessionId = null;
    var sessionData = null;
    var ordersMap = {};           // {orderId: orderObject}
    var ordersOrder = [];         // ordered list of order IDs
    var currentOrderIdx = 0;      // index into ordersOrder
    var socket = null;
    var isConnected = false;
    var selectedMaterialId = null;
    var packingSuggestionsCache = {};
    var uploadedPhotoUrl = null;  // URL of uploaded packing photo

    // ========================================
    // TOAST (inline — no external dependency)
    // ========================================

    function showToast(message, type) {
        var container = document.getElementById('wmsMToastContainer');
        if (!container) return;

        var toast = document.createElement('div');
        toast.className = 'wms-m-toast ' + (type || 'info');
        toast.textContent = message;
        container.appendChild(toast);

        setTimeout(function () {
            toast.classList.add('hiding');
            setTimeout(function () {
                if (toast.parentNode) toast.parentNode.removeChild(toast);
            }, 300);
        }, 3000);
    }

    // ========================================
    // VIBRATE HELPER
    // ========================================

    function vibrate(ms) {
        if (navigator.vibrate) {
            navigator.vibrate(ms || 50);
        }
    }

    // ========================================
    // INIT
    // ========================================

    function initMobileWms() {
        sessionToken = window.WMS_SESSION_TOKEN;
        sessionData = window.WMS_SESSION_DATA;
        sessionId = window.WMS_SESSION_ID;

        if (!sessionToken || !sessionData || !sessionId) {
            showToast('Brak danych sesji', 'error');
            return;
        }

        // Build ordersMap and ordersOrder
        buildOrdersState(sessionData.orders || []);

        // Update session progress
        updateSessionProgressUI();

        // Connect WebSocket
        connectWebSocket();

        // Render first non-packed order
        var startIdx = findFirstNonPackedIndex();
        if (startIdx >= 0) {
            currentOrderIdx = startIdx;
        }
        renderCurrentOrder();

        // Bind navigation
        bindNavigation();
    }

    function buildOrdersState(orders) {
        ordersMap = {};
        ordersOrder = [];
        orders.forEach(function (o) {
            ordersMap[o.id] = o;
            ordersOrder.push(o.id);
        });
    }

    function findFirstNonPackedIndex() {
        for (var i = 0; i < ordersOrder.length; i++) {
            var order = ordersMap[ordersOrder[i]];
            if (order && !order.packing_completed_at) {
                return i;
            }
        }
        return 0;
    }

    // ========================================
    // WEBSOCKET CONNECTION
    // ========================================

    function connectWebSocket() {
        socket = io({
            reconnection: true,
            reconnectionAttempts: Infinity,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000,
        });

        socket.on('connect', function () {
            isConnected = true;
            updateConnectionUI('connected', 'Połączono');

            // Join the session room
            socket.emit('join_session', {
                session_id: sessionId,
                role: 'mobile',
                token: sessionToken,
            });
        });

        socket.on('disconnect', function () {
            isConnected = false;
            updateConnectionUI('disconnected', 'Rozłączono — ponawiam...');
        });

        socket.on('reconnect_attempt', function () {
            updateConnectionUI('disconnected', 'Ponowne łączenie...');
        });

        // Session state — full refresh (e.g. after joining)
        socket.on('session_state', function (data) {
            sessionData = data;
            buildOrdersState(data.orders || []);
            updateSessionProgressUI();
            renderCurrentOrder();
        });

        // Item status updated (from any source — desktop or mobile)
        socket.on('item_status_updated', function (data) {
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
                    localItem.picked_quantity = itemData.picked_quantity;
                    localItem.wms_status = itemData.wms_status;
                    localItem.wms_status_name = itemData.wms_status_name;
                    localItem.wms_status_color = itemData.wms_status_color;
                    localItem.is_picked = itemData.is_picked;
                    localItem.picked_at = itemData.picked_at;
                }
            }

            // Update session progress
            if (sessionProgress) {
                sessionData.session.packed_orders_count = sessionProgress.packed_orders_count;
                sessionData.session.picked_orders_count = sessionProgress.picked_orders_count;
                sessionData.session.progress_percentage = sessionProgress.progress_percentage;
                updateSessionProgressUI();
            }

            // Update DOM if this is the current order
            var currentOrderId = ordersOrder[currentOrderIdx];
            if (orderData.id === currentOrderId) {
                updateItemCardDOM(itemData);
                updateOrderProgressUI(order);
                updatePackButton(order);
            }
        });

        // Order packed (from any source)
        socket.on('order_packed', function (data) {
            var orderData = data.order;
            var sessionProgress = data.session;

            var order = ordersMap[orderData.id];
            if (order) {
                order.packing_completed_at = orderData.packed_at;
                order.status = orderData.status;
                order.status_display_name = orderData.status_display_name;
            }

            if (sessionProgress) {
                sessionData.session.packed_orders_count = sessionProgress.packed_orders_count;
                sessionData.session.progress_percentage = sessionProgress.progress_percentage;
                updateSessionProgressUI();
            }

            if (data.low_stock_warning) {
                showToast(data.low_stock_warning, 'warning');
            }

            vibrate(200);
            showToast('Zamówienie ' + (orderData.order_number || '') + ' spakowane!', 'success');

            // Auto-advance to next non-packed order
            var nextIdx = findFirstNonPackedIndex();
            if (nextIdx >= 0 && nextIdx !== currentOrderIdx) {
                currentOrderIdx = nextIdx;
                renderCurrentOrder();
            } else {
                // All packed or stay on current
                renderCurrentOrder();
            }
        });

        // Error
        socket.on('error', function (data) {
            showToast(data.message || 'Wystąpił błąd', 'error');
        });

        socket.on('session_ended', function (data) {
            showToast(data.message || 'Sesja WMS została zakończona', 'info');
            // Disable all interactive elements
            var buttons = document.querySelectorAll('button');
            buttons.forEach(function (btn) { btn.disabled = true; });
            // Show overlay message
            var overlay = document.createElement('div');
            overlay.className = 'wms-m-session-ended-overlay';
            overlay.innerHTML = '<div class="wms-m-session-ended-box">' +
                '<div class="wms-m-session-ended-icon">✓</div>' +
                '<div class="wms-m-session-ended-title">' +
                (data.status === 'cancelled' ? 'Sesja anulowana' : 'Sesja zakończona') +
                '</div>' +
                '<div class="wms-m-session-ended-msg">' + (data.message || '') + '</div>' +
                '</div>';
            document.body.appendChild(overlay);
        });
    }

    // ========================================
    // CONNECTION UI
    // ========================================

    function updateConnectionUI(state, text) {
        var bar = document.getElementById('wmsConnectionBar');
        if (!bar) return;

        bar.className = 'wms-m-connection ' + state;
        var textEl = bar.querySelector('.wms-m-connection-text');
        if (textEl) textEl.textContent = text;
    }

    // ========================================
    // RENDER CURRENT ORDER
    // ========================================

    function renderCurrentOrder() {
        var orderId = ordersOrder[currentOrderIdx];
        var order = ordersMap[orderId];

        if (!order) {
            clearOrderUI();
            return;
        }

        // Order card info
        var numEl = document.getElementById('wmsMOrderNumber');
        var custEl = document.getElementById('wmsMOrderCustomer');
        if (numEl) numEl.textContent = order.order_number;
        if (custEl) custEl.textContent = order.customer_name || '-';

        // Order progress
        updateOrderProgressUI(order);

        // Render items
        renderItems(order);

        // Pack button
        updatePackButton(order);

        // Navigation
        updateNavigation();
    }

    function clearOrderUI() {
        var numEl = document.getElementById('wmsMOrderNumber');
        var custEl = document.getElementById('wmsMOrderCustomer');
        if (numEl) numEl.textContent = '-';
        if (custEl) custEl.textContent = '-';

        var list = document.getElementById('wmsMItemsList');
        if (list) {
            list.querySelectorAll('.wms-m-item-card').forEach(function (el) { el.remove(); });
            var empty = document.getElementById('wmsMItemsEmpty');
            if (empty) empty.style.display = '';
        }

        var packSection = document.getElementById('wmsMPackSection');
        if (packSection) packSection.style.display = 'none';
    }

    // ========================================
    // RENDER ITEMS
    // ========================================

    function renderItems(order) {
        var list = document.getElementById('wmsMItemsList');
        var emptyEl = document.getElementById('wmsMItemsEmpty');
        if (!list) return;

        // Remove old item cards
        list.querySelectorAll('.wms-m-item-card').forEach(function (el) { el.remove(); });

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
        var card = document.createElement('div');
        card.className = 'wms-m-item-card';
        card.setAttribute('data-item-id', item.id);

        var pickedQty = item.picked_quantity || 0;
        if (pickedQty >= item.quantity) {
            card.classList.add('picked');
        } else if (pickedQty > 0) {
            card.classList.add('partial');
        }
        if (isPacked) {
            card.classList.add('packed');
        }

        // Top row: image + info + badge
        var top = document.createElement('div');
        top.className = 'wms-m-item-top';

        var imgWrap = document.createElement('div');
        imgWrap.className = 'wms-m-item-image';
        var img = document.createElement('img');
        img.src = item.product_image_url || '/static/images/placeholder.png';
        img.alt = item.product_name || '';
        img.loading = 'lazy';
        imgWrap.appendChild(img);

        var info = document.createElement('div');
        info.className = 'wms-m-item-info';
        var name = document.createElement('div');
        name.className = 'wms-m-item-name';
        name.textContent = item.product_name || '-';
        var sku = document.createElement('div');
        sku.className = 'wms-m-item-sku';
        sku.textContent = item.product_sku || '';
        info.appendChild(name);
        info.appendChild(sku);

        var badge = document.createElement('span');
        badge.className = 'wms-m-item-status-badge';
        badge.textContent = item.wms_status_name || item.wms_status || '-';
        badge.style.backgroundColor = item.wms_status_color || '#9ca3af';

        top.appendChild(imgWrap);
        top.appendChild(info);
        top.appendChild(badge);

        // Bottom row: counter
        var counter = document.createElement('div');
        counter.className = 'wms-m-item-counter';
        if (pickedQty >= item.quantity) {
            counter.classList.add('complete');
        } else if (pickedQty > 0) {
            counter.classList.add('partial');
        }

        var decBtn = createCounterButton('decrement',
            '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"></line></svg>'
        );
        decBtn.disabled = pickedQty <= 0 || isPacked;

        var display = document.createElement('span');
        display.className = 'wms-m-counter-display';
        display.textContent = pickedQty + '/' + item.quantity;

        var incBtn = createCounterButton('increment',
            '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>'
        );
        incBtn.disabled = pickedQty >= item.quantity || isPacked;

        var allBtn = createCounterButton('pick_all',
            '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>'
        );
        allBtn.classList.add('wms-m-pick-all');
        allBtn.disabled = pickedQty >= item.quantity || isPacked;

        if (!isPacked) {
            decBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                if (!decBtn.disabled) onItemAction(item.id, 'decrement');
            });
            incBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                if (!incBtn.disabled) onItemAction(item.id, 'increment');
            });
            allBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                if (!allBtn.disabled) onItemAction(item.id, 'pick_all');
            });
        }

        counter.appendChild(decBtn);
        counter.appendChild(display);
        counter.appendChild(incBtn);
        counter.appendChild(allBtn);

        card.appendChild(top);
        card.appendChild(counter);
        return card;
    }

    function createCounterButton(action, svgHTML) {
        var btn = document.createElement('button');
        btn.className = 'wms-m-counter-btn';
        btn.setAttribute('type', 'button');
        btn.setAttribute('data-action', action);
        btn.innerHTML = svgHTML;
        return btn;
    }

    // ========================================
    // ITEM ACTION (WebSocket emit)
    // ========================================

    function onItemAction(orderItemId, action) {
        if (!socket || !isConnected) {
            showToast('Brak połączenia', 'error');
            return;
        }

        // Optimistic UI update
        var orderId = ordersOrder[currentOrderIdx];
        var order = ordersMap[orderId];
        if (order) {
            var item = (order.items || []).find(function (i) { return i.id === orderItemId; });
            if (item) {
                var oldQty = item.picked_quantity || 0;
                var newQty = oldQty;

                if (action === 'increment') {
                    newQty = Math.min(oldQty + 1, item.quantity);
                } else if (action === 'decrement') {
                    newQty = Math.max(oldQty - 1, 0);
                } else if (action === 'pick_all') {
                    newQty = item.quantity;
                }

                item.picked_quantity = newQty;
                item.is_picked = newQty >= item.quantity;
                item.wms_status = newQty >= item.quantity ? 'zebrane' : 'do_zebrania';

                // Update local order progress
                var totalQty = (order.items || []).reduce(function (s, i) { return s + i.quantity; }, 0);
                var pickedQty = (order.items || []).reduce(function (s, i) { return s + (i.picked_quantity || 0); }, 0);
                order.picked_percentage = totalQty > 0 ? Math.round((pickedQty / totalQty) * 100) : 0;
                order.is_picked = pickedQty >= totalQty && totalQty > 0;
                order.picked_quantity = pickedQty;
                order.total_quantity = totalQty;

                // Update DOM immediately
                updateItemCardDOM(item);
                updateOrderProgressUI(order);
                updatePackButton(order);

                vibrate(50);
            }
        }

        // Emit to server
        socket.emit('update_item_status', {
            order_item_id: orderItemId,
            action: action,
        });
    }

    // ========================================
    // UPDATE ITEM CARD DOM
    // ========================================

    function updateItemCardDOM(itemData) {
        var card = document.querySelector('.wms-m-item-card[data-item-id="' + itemData.id + '"]');
        if (!card) return;

        var pickedQty = itemData.picked_quantity || 0;
        var totalQty = itemData.quantity;

        // Card state classes
        card.classList.remove('picked', 'partial');
        if (pickedQty >= totalQty) {
            card.classList.add('picked');
        } else if (pickedQty > 0) {
            card.classList.add('partial');
        }

        // Badge
        var badge = card.querySelector('.wms-m-item-status-badge');
        if (badge) {
            badge.textContent = itemData.wms_status_name || itemData.wms_status || '-';
            if (itemData.wms_status_color) {
                badge.style.backgroundColor = itemData.wms_status_color;
            }
        }

        // Counter display
        var display = card.querySelector('.wms-m-counter-display');
        if (display) display.textContent = pickedQty + '/' + totalQty;

        // Counter state
        var counter = card.querySelector('.wms-m-item-counter');
        if (counter) {
            counter.classList.remove('partial', 'complete');
            if (pickedQty >= totalQty) {
                counter.classList.add('complete');
            } else if (pickedQty > 0) {
                counter.classList.add('partial');
            }
        }

        // Button states
        var decBtn = card.querySelector('[data-action="decrement"]');
        var incBtn = card.querySelector('[data-action="increment"]');
        var allBtn = card.querySelector('[data-action="pick_all"]');
        if (decBtn) decBtn.disabled = pickedQty <= 0;
        if (incBtn) incBtn.disabled = pickedQty >= totalQty;
        if (allBtn) allBtn.disabled = pickedQty >= totalQty;
    }

    // ========================================
    // PROGRESS UI
    // ========================================

    function updateSessionProgressUI() {
        var session = sessionData.session;
        var packed = session.packed_orders_count || 0;
        var total = session.orders_count || 0;
        var pct = session.progress_percentage || 0;

        var progressEl = document.getElementById('wmsMSessionProgress');
        var fillEl = document.getElementById('wmsMSessionProgressFill');

        if (progressEl) progressEl.textContent = packed + '/' + total;
        if (fillEl) {
            fillEl.style.width = pct + '%';
            fillEl.classList.toggle('complete', pct >= 100);
        }
    }

    function updateOrderProgressUI(order) {
        if (!order) return;

        var items = order.items || [];
        var totalQty = items.reduce(function (s, i) { return s + i.quantity; }, 0);
        var pickedQty = items.reduce(function (s, i) { return s + (i.picked_quantity || 0); }, 0);
        var pct = totalQty > 0 ? Math.round((pickedQty / totalQty) * 100) : 0;

        var textEl = document.getElementById('wmsMOrderProgressText');
        var fillEl = document.getElementById('wmsMOrderProgressFill');

        if (textEl) textEl.textContent = pickedQty + ' / ' + totalQty + ' szt.';
        if (fillEl) {
            fillEl.style.width = pct + '%';
            fillEl.classList.toggle('complete', pct >= 100);
        }
    }

    // ========================================
    // PACK ORDER
    // ========================================

    function updatePackButton(order) {
        var section = document.getElementById('wmsMPackSection');
        var btn = document.getElementById('wmsMPackBtn');
        if (!section || !btn) return;

        if (!order || order.packing_completed_at) {
            section.style.display = 'none';
            return;
        }

        if (order.is_picked) {
            section.style.display = '';
            btn.disabled = false;
            fetchPackingSuggestionsMobile(order.id);
        } else {
            section.style.display = 'none';
            btn.disabled = true;
        }
    }

    // ========================================
    // PACKAGING SUGGESTIONS (MOBILE)
    // ========================================

    function fetchPackingSuggestionsMobile(orderId) {
        if (packingSuggestionsCache[orderId]) {
            renderPackingSuggestionsMobile(orderId, packingSuggestionsCache[orderId]);
            return;
        }

        fetch('/api/orders/wms/suggest-packaging/' + orderId + '/' + sessionToken)
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.success) return;
            packingSuggestionsCache[orderId] = data;
            renderPackingSuggestionsMobile(orderId, data);
        })
        .catch(function () {
            // Suggestions not available for mobile (auth issue) — hide suggestion area
        });
    }

    function renderPackingSuggestionsMobile(orderId, data) {
        var container = document.getElementById('wmsMPackingSuggestions');
        var warningsEl = document.getElementById('wmsMPackingWarnings');
        var selectEl = document.getElementById('wmsMPackingMaterialSelect');
        var weightInput = document.getElementById('wmsMPackingWeight');

        selectedMaterialId = null;

        // Warnings
        if (warningsEl) {
            warningsEl.innerHTML = '';
            (data.warnings || []).forEach(function (w) {
                var span = document.createElement('span');
                span.className = 'wms-m-packing-warning';
                span.textContent = w;
                warningsEl.appendChild(span);
            });
        }

        if (container) {
            // Remove old cards
            container.querySelectorAll('.wms-m-suggestion-card').forEach(function (c) { c.remove(); });

            var suggestions = data.suggestions || [];
            suggestions.forEach(function (s) {
                var card = document.createElement('div');
                card.className = 'wms-m-suggestion-card';
                card.setAttribute('data-material-id', s.id);

                var scorePercent = Math.round(s.fit_score * 100);

                card.innerHTML =
                    '<div class="wms-m-suggestion-top">' +
                        '<span class="wms-m-suggestion-name">' + escapeHtmlM(s.name) + '</span>' +
                        '<span class="wms-m-suggestion-score">' + scorePercent + '%</span>' +
                    '</div>' +
                    '<div class="wms-m-suggestion-bottom">' +
                        '<span>' + escapeHtmlM(s.type_display) + '</span>' +
                        (s.dimensions_display ? '<span>' + escapeHtmlM(s.dimensions_display) + '</span>' : '') +
                    '</div>';

                card.addEventListener('click', function () {
                    selectedMaterialId = s.id;
                    container.querySelectorAll('.wms-m-suggestion-card').forEach(function (c) {
                        c.classList.remove('suggestion-selected');
                    });
                    card.classList.add('suggestion-selected');
                    if (selectEl) selectEl.value = s.id;
                    vibrate(30);
                });

                container.appendChild(card);
            });
        }

        // Populate dropdown
        if (selectEl) {
            while (selectEl.options.length > 1) selectEl.remove(1);
            (data.all_materials || []).forEach(function (m) {
                var opt = document.createElement('option');
                opt.value = m.id;
                opt.textContent = m.name + (m.dimensions_display ? ' (' + m.dimensions_display + ')' : '');
                selectEl.appendChild(opt);
            });
            selectEl.value = '';
            selectEl.addEventListener('change', function () {
                selectedMaterialId = parseInt(selectEl.value) || null;
                if (container) {
                    container.querySelectorAll('.wms-m-suggestion-card').forEach(function (c) {
                        c.classList.remove('suggestion-selected');
                    });
                }
            });
        }

        // Pre-fill weight
        if (weightInput && data.total_weight) {
            weightInput.value = data.total_weight.toFixed(2);
        }
    }

    function escapeHtmlM(text) {
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ========================================
    // PHOTO CAPTURE & UPLOAD
    // ========================================

    function bindPhotoHandlers() {
        var photoBtn = document.getElementById('wmsMPhotoBtn');
        var photoInput = document.getElementById('wmsMPhotoInput');
        var removeBtn = document.getElementById('wmsMPhotoRemove');

        if (photoBtn && photoInput) {
            photoBtn.addEventListener('click', function () {
                photoInput.click();
            });

            photoInput.addEventListener('change', function () {
                var file = photoInput.files && photoInput.files[0];
                if (!file) return;
                handlePhotoSelected(file);
            });
        }

        if (removeBtn) {
            removeBtn.addEventListener('click', function () {
                resetPhotoState();
            });
        }
    }

    function handlePhotoSelected(file) {
        compressImage(file, 1200, 0.7).then(function (blob) {
            showPhotoPreview(blob);
            uploadPackingPhoto(blob);
        }).catch(function (err) {
            showToast('Błąd przetwarzania zdjęcia', 'error');
        });
    }

    function compressImage(file, maxSize, quality) {
        return new Promise(function (resolve, reject) {
            var reader = new FileReader();
            reader.onload = function (e) {
                var img = new Image();
                img.onload = function () {
                    var canvas = document.createElement('canvas');
                    var w = img.width;
                    var h = img.height;

                    if (w > h) {
                        if (w > maxSize) { h = Math.round(h * maxSize / w); w = maxSize; }
                    } else {
                        if (h > maxSize) { w = Math.round(w * maxSize / h); h = maxSize; }
                    }

                    canvas.width = w;
                    canvas.height = h;
                    var ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, w, h);

                    canvas.toBlob(function (blob) {
                        if (blob) resolve(blob);
                        else reject(new Error('Canvas toBlob failed'));
                    }, 'image/jpeg', quality);
                };
                img.onerror = reject;
                img.src = e.target.result;
            };
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    function showPhotoPreview(blob) {
        var preview = document.getElementById('wmsMPhotoPreview');
        var previewImg = document.getElementById('wmsMPhotoPreviewImg');
        var photoBtn = document.getElementById('wmsMPhotoBtn');

        if (preview && previewImg) {
            var url = URL.createObjectURL(blob);
            previewImg.src = url;
            preview.style.display = '';
        }
        if (photoBtn) photoBtn.style.display = 'none';
    }

    function uploadPackingPhoto(blob) {
        var orderId = ordersOrder[currentOrderIdx];
        var uploading = document.getElementById('wmsMPhotoUploading');
        if (uploading) uploading.style.display = '';

        var formData = new FormData();
        formData.append('session_token', sessionToken);
        formData.append('order_id', orderId);
        formData.append('photo', blob, 'packing_photo.jpg');

        fetch('/wms/mobile/upload-packing-photo', {
            method: 'POST',
            body: formData,
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (uploading) uploading.style.display = 'none';
            if (data.success) {
                uploadedPhotoUrl = data.photo_url;
                showToast('Zdjęcie przesłane', 'success');
                vibrate(50);
            } else {
                showToast(data.message || 'Błąd przesyłania', 'error');
                resetPhotoState();
            }
        })
        .catch(function () {
            if (uploading) uploading.style.display = 'none';
            showToast('Błąd połączenia', 'error');
            resetPhotoState();
        });
    }

    function resetPhotoState() {
        uploadedPhotoUrl = null;
        var preview = document.getElementById('wmsMPhotoPreview');
        var previewImg = document.getElementById('wmsMPhotoPreviewImg');
        var photoBtn = document.getElementById('wmsMPhotoBtn');
        var photoInput = document.getElementById('wmsMPhotoInput');

        if (preview) preview.style.display = 'none';
        if (previewImg) previewImg.src = '';
        if (photoBtn) photoBtn.style.display = '';
        if (photoInput) photoInput.value = '';
    }

    // ========================================
    // PACK ORDER
    // ========================================

    function onPackOrder() {
        var orderId = ordersOrder[currentOrderIdx];
        var order = ordersMap[orderId];
        if (!order) return;

        if (!confirm('Oznaczyć zamówienie ' + order.order_number + ' jako spakowane?')) {
            return;
        }

        if (!socket || !isConnected) {
            showToast('Brak połączenia', 'error');
            return;
        }

        var selectEl = document.getElementById('wmsMPackingMaterialSelect');
        var materialId = selectedMaterialId || (selectEl ? parseInt(selectEl.value) || null : null);

        var weightInput = document.getElementById('wmsMPackingWeight');
        var weight = weightInput ? parseFloat(weightInput.value) || null : null;

        var sendEmailCheckbox = document.getElementById('wmsMSendEmailCheckbox');
        var sendEmail = sendEmailCheckbox ? sendEmailCheckbox.checked : false;

        var payload = { order_id: orderId };
        if (materialId) payload.packaging_material_id = materialId;
        if (weight) payload.weight = weight;
        if (sendEmail && uploadedPhotoUrl) payload.send_email = true;

        socket.emit('mark_order_packed', payload);

        // Reset
        selectedMaterialId = null;
        delete packingSuggestionsCache[orderId];
        resetPhotoState();
    }

    // ========================================
    // NAVIGATION
    // ========================================

    function bindNavigation() {
        var prevBtn = document.getElementById('wmsMPrevBtn');
        var nextBtn = document.getElementById('wmsMNextBtn');
        var packBtn = document.getElementById('wmsMPackBtn');

        if (prevBtn) {
            prevBtn.addEventListener('click', function () {
                navigateOrder(-1);
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener('click', function () {
                navigateOrder(1);
            });
        }
        if (packBtn) {
            packBtn.addEventListener('click', onPackOrder);
        }

        bindPhotoHandlers();
    }

    function navigateOrder(direction) {
        var newIdx = currentOrderIdx + direction;
        if (newIdx < 0 || newIdx >= ordersOrder.length) return;
        currentOrderIdx = newIdx;
        resetPhotoState();
        renderCurrentOrder();

        if (socket && socket.connected) {
            socket.emit('navigate_order', { order_id: ordersOrder[currentOrderIdx] });
        }
    }

    function updateNavigation() {
        var prevBtn = document.getElementById('wmsMPrevBtn');
        var nextBtn = document.getElementById('wmsMNextBtn');
        var indicator = document.getElementById('wmsMNavIndicator');

        if (prevBtn) prevBtn.disabled = currentOrderIdx <= 0;
        if (nextBtn) nextBtn.disabled = currentOrderIdx >= ordersOrder.length - 1;
        if (indicator) indicator.textContent = (currentOrderIdx + 1) + ' / ' + ordersOrder.length;
    }

    // ========================================
    // BOOT
    // ========================================

    document.addEventListener('DOMContentLoaded', initMobileWms);

})();
