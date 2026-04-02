/**
 * Offer LIVE Dashboard
 * Tab switching, Chart.js, orders search/pagination, Socket.IO real-time updates
 */

document.addEventListener('DOMContentLoaded', function () {
    initializeLiveTabs();
    initializeOrdersTimelineChart();
    initializeOrdersTab();
    initializeProductsTab();
    initializeSocketIO();
    initializeMetaCountdowns();
    initializeMatrixToggle();
});

/* ==========================================
   1. TAB SWITCHING
   ========================================== */

function initializeLiveTabs() {
    var tabButtons = document.querySelectorAll('.live-tab-button');
    var tabPanels = document.querySelectorAll('.live-tab-panel');

    if (tabButtons.length === 0) return;

    tabButtons.forEach(function (button) {
        button.addEventListener('click', function () {
            var targetTab = this.getAttribute('data-tab');

            tabButtons.forEach(function (btn) { btn.classList.remove('live-tab-active'); });
            tabPanels.forEach(function (panel) { panel.classList.remove('live-tab-active'); });

            this.classList.add('live-tab-active');
            var targetPanel = document.getElementById(targetTab);
            if (targetPanel) {
                targetPanel.classList.add('live-tab-active');
            }

            if (targetTab === 'tab-orders' && !ordersRendered) {
                renderOrderCards();
                ordersRendered = true;
            }

            try {
                localStorage.setItem('offerLiveActiveTab', targetTab);
            } catch (e) { /* ignore */ }
        });
    });

    try {
        var savedTab = localStorage.getItem('offerLiveActiveTab');
        if (savedTab) {
            var btn = document.querySelector('.live-tab-button[data-tab="' + savedTab + '"]');
            if (btn) btn.click();
        }
    } catch (e) { /* ignore */ }
}

/* ==========================================
   2. ORDERS TIMELINE CHART
   ========================================== */

var ordersChart = null;
var currentGranularity = 'hour';

var GRANULARITY_LABELS = {
    day: 'Zamówienia / dzień',
    hour: 'Zamówienia / godz.',
    minute: 'Zamówienia / min.'
};

function initializeOrdersTimelineChart() {
    var canvas = document.getElementById('ordersTimelineChart');
    if (!canvas || typeof Chart === 'undefined') return;

    buildChart(canvas);
    initializeGranularityToggle();

    // Theme change observer
    var observer = new MutationObserver(function (mutations) {
        for (var m = 0; m < mutations.length; m++) {
            if (mutations[m].attributeName === 'data-theme') updateChartTheme();
        }
    });
    observer.observe(document.documentElement, { attributes: true });
}

function buildChart(canvas) {
    var timestamps = window.ORDER_TIMESTAMPS || [];

    var buckets = bucketTimestamps(timestamps, currentGranularity);
    var sortedKeys = Object.keys(buckets).sort();
    var labels = [];
    var data = [];
    var cumulativeData = [];
    var cumulative = 0;

    for (var j = 0; j < sortedKeys.length; j++) {
        labels.push(sortedKeys[j]);
        data.push(buckets[sortedKeys[j]]);
        cumulative += buckets[sortedKeys[j]];
        cumulativeData.push(cumulative);
    }

    var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    var colors = getChartColors(isDark);
    var timeUnit = currentGranularity === 'day' ? 'day' : currentGranularity === 'minute' ? 'minute' : 'hour';

    if (ordersChart) {
        ordersChart.destroy();
        ordersChart = null;
    }

    var ctx = canvas.getContext('2d');

    ordersChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: GRANULARITY_LABELS[currentGranularity],
                    data: data,
                    borderColor: colors.primary,
                    backgroundColor: colors.primaryBg,
                    borderWidth: 2.5,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                    pointHoverRadius: 6,
                    pointBackgroundColor: colors.primary,
                    pointBorderColor: colors.pointBorder,
                    pointBorderWidth: 2,
                    yAxisID: 'y',
                },
                {
                    label: 'Suma narastająco',
                    data: cumulativeData,
                    borderColor: colors.secondary,
                    backgroundColor: 'transparent',
                    borderWidth: 2,
                    borderDash: [6, 3],
                    fill: false,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    pointBackgroundColor: colors.secondary,
                    yAxisID: 'y1',
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    display: true, position: 'top', align: 'end',
                    labels: { color: colors.text, font: { size: 12 }, usePointStyle: true, pointStyle: 'circle', padding: 16 }
                },
                tooltip: {
                    backgroundColor: colors.tooltipBg, titleColor: colors.tooltipTitle,
                    bodyColor: colors.tooltipBody, borderColor: colors.tooltipBorder,
                    borderWidth: 1, padding: 12, cornerRadius: 8,
                    callbacks: {
                        title: function (items) {
                            if (!items.length) return '';
                            var ts = items[0].parsed.x;
                            var d = new Date(ts);
                            if (isNaN(d.getTime())) return items[0].label || '';
                            return formatChartDate(d);
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: timeUnit,
                        displayFormats: { minute: 'HH:mm', hour: 'dd.MM HH:mm', day: 'dd.MM.yyyy' },
                        tooltipFormat: 'dd.MM.yyyy HH:mm'
                    },
                    grid: { color: colors.grid },
                    ticks: { color: colors.tickText, font: { size: 11 }, maxRotation: 45, autoSkip: true, maxTicksLimit: 14 },
                    border: { color: colors.grid }
                },
                y: {
                    type: 'linear', display: true, position: 'left', beginAtZero: true,
                    title: { display: true, text: GRANULARITY_LABELS[currentGranularity], color: colors.tickText, font: { size: 11 } },
                    grid: { color: colors.grid }, ticks: { color: colors.tickText, font: { size: 11 }, stepSize: 1, precision: 0 },
                    border: { color: colors.grid }
                },
                y1: {
                    type: 'linear', display: true, position: 'right', beginAtZero: true,
                    title: { display: true, text: 'Suma', color: colors.tickText, font: { size: 11 } },
                    grid: { drawOnChartArea: false }, ticks: { color: colors.tickText, font: { size: 11 }, precision: 0 },
                    border: { color: colors.grid }
                }
            }
        }
    });
}

function bucketTimestamps(timestamps, granularity) {
    var buckets = {};
    for (var i = 0; i < timestamps.length; i++) {
        var dt = new Date(timestamps[i]);
        var key;
        if (granularity === 'day') {
            key = new Date(dt.getFullYear(), dt.getMonth(), dt.getDate()).toISOString();
        } else if (granularity === 'minute') {
            key = new Date(dt.getFullYear(), dt.getMonth(), dt.getDate(), dt.getHours(), dt.getMinutes()).toISOString();
        } else {
            key = new Date(dt.getFullYear(), dt.getMonth(), dt.getDate(), dt.getHours()).toISOString();
        }
        buckets[key] = (buckets[key] || 0) + 1;
    }
    return buckets;
}

function rebuildChart() {
    var canvas = document.getElementById('ordersTimelineChart');
    if (!canvas || typeof Chart === 'undefined') return;
    buildChart(canvas);
}

function initializeGranularityToggle() {
    var buttons = document.querySelectorAll('.chart-granularity-btn');
    buttons.forEach(function (btn) {
        btn.addEventListener('click', function () {
            buttons.forEach(function (b) { b.classList.remove('chart-granularity-active'); });
            this.classList.add('chart-granularity-active');
            currentGranularity = this.getAttribute('data-granularity');
            rebuildChart();
        });
    });
}

function getChartColors(isDark) {
    if (isDark) {
        return {
            primary: '#f093fb', primaryBg: 'rgba(240, 147, 251, 0.15)',
            secondary: 'rgba(52, 211, 153, 0.8)', text: 'rgba(255, 255, 255, 0.7)',
            tickText: 'rgba(255, 255, 255, 0.5)', grid: 'rgba(255, 255, 255, 0.08)',
            pointBorder: 'rgba(15, 12, 41, 0.8)', tooltipBg: 'rgba(15, 12, 41, 0.95)',
            tooltipTitle: '#ffffff', tooltipBody: 'rgba(255, 255, 255, 0.8)',
            tooltipBorder: 'rgba(240, 147, 251, 0.3)',
        };
    }
    return {
        primary: '#FF8500', primaryBg: 'rgba(255, 133, 0, 0.1)',
        secondary: 'rgba(16, 185, 129, 0.7)', text: '#616161',
        tickText: '#9E9E9E', grid: 'rgba(0, 0, 0, 0.06)',
        pointBorder: '#ffffff', tooltipBg: '#ffffff',
        tooltipTitle: '#212121', tooltipBody: '#616161',
        tooltipBorder: '#E0E0E0',
    };
}

function updateChartTheme() {
    if (!ordersChart) return;
    var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    var c = getChartColors(isDark);
    ordersChart.data.datasets[0].borderColor = c.primary;
    ordersChart.data.datasets[0].backgroundColor = c.primaryBg;
    ordersChart.data.datasets[0].pointBackgroundColor = c.primary;
    ordersChart.data.datasets[0].pointBorderColor = c.pointBorder;
    ordersChart.data.datasets[1].borderColor = c.secondary;
    var scales = ordersChart.options.scales;
    scales.x.grid.color = c.grid; scales.x.ticks.color = c.tickText; scales.x.border.color = c.grid;
    scales.y.grid.color = c.grid; scales.y.ticks.color = c.tickText; scales.y.title.color = c.tickText; scales.y.border.color = c.grid;
    scales.y1.ticks.color = c.tickText; scales.y1.title.color = c.tickText; scales.y1.border.color = c.grid;
    ordersChart.options.plugins.legend.labels.color = c.text;
    ordersChart.options.plugins.tooltip.backgroundColor = c.tooltipBg;
    ordersChart.options.plugins.tooltip.titleColor = c.tooltipTitle;
    ordersChart.options.plugins.tooltip.bodyColor = c.tooltipBody;
    ordersChart.options.plugins.tooltip.borderColor = c.tooltipBorder;
    ordersChart.update('none');
}

function formatChartDate(dt) {
    var dd = String(dt.getDate()).padStart(2, '0');
    var mm = String(dt.getMonth() + 1).padStart(2, '0');
    var yyyy = dt.getFullYear();
    var hh = String(dt.getHours()).padStart(2, '0');
    var min = String(dt.getMinutes()).padStart(2, '0');
    return dd + '.' + mm + '.' + yyyy + ' ' + hh + ':' + min;
}

/* ==========================================
   3. ORDERS TAB
   ========================================== */

var ORDERS_PER_PAGE = 12;
var currentPage = 1;
var filteredOrders = [];
var ordersRendered = false;

function initializeOrdersTab() {
    filteredOrders = (window.LIVE_ORDERS || []).slice();

    var searchInput = document.getElementById('ordersSearch');
    if (searchInput) {
        searchInput.addEventListener('input', debounce(function () {
            currentPage = 1;
            applyOrdersFilters();
        }, 300));
    }
}

function applyOrdersFilters() {
    var allOrders = window.LIVE_ORDERS || [];
    var searchInput = document.getElementById('ordersSearch');
    var searchTerm = (searchInput ? searchInput.value : '').toLowerCase().trim();

    filteredOrders = allOrders.filter(function (order) {
        if (searchTerm) {
            return order.order_number.toLowerCase().indexOf(searchTerm) !== -1 ||
                order.customer_name.toLowerCase().indexOf(searchTerm) !== -1 ||
                order.customer_email.toLowerCase().indexOf(searchTerm) !== -1;
        }
        return true;
    });

    var countEl = document.getElementById('ordersDisplayCount');
    if (countEl) countEl.textContent = filteredOrders.length;

    renderOrderCards();
}

function renderOrderCards() {
    var grid = document.getElementById('ordersGrid');
    var emptyState = document.getElementById('ordersEmpty');
    var paginationContainer = document.getElementById('ordersPagination');
    if (!grid) return;

    if (filteredOrders.length === 0 && (window.LIVE_ORDERS || []).length > 0) {
        filteredOrders = (window.LIVE_ORDERS || []).slice();
        var countEl = document.getElementById('ordersDisplayCount');
        if (countEl) countEl.textContent = filteredOrders.length;
    }

    if (filteredOrders.length === 0) {
        grid.innerHTML = '';
        if (emptyState) emptyState.style.display = 'block';
        if (paginationContainer) paginationContainer.innerHTML = '';
        return;
    }

    if (emptyState) emptyState.style.display = 'none';

    var totalPages = Math.ceil(filteredOrders.length / ORDERS_PER_PAGE);
    if (currentPage > totalPages) currentPage = totalPages;
    var start = (currentPage - 1) * ORDERS_PER_PAGE;
    var pageOrders = filteredOrders.slice(start, start + ORDERS_PER_PAGE);

    var html = '';
    for (var i = 0; i < pageOrders.length; i++) {
        html += buildOrderCardHTML(pageOrders[i]);
    }
    grid.innerHTML = html;

    renderPagination(totalPages, paginationContainer);
}

function buildOrderCardHTML(order) {
    var detailUrl = window.ORDER_DETAIL_URL + '/' + order.order_id;
    var includeFinancials = window.INCLUDE_FINANCIALS;

    var itemsHTML = '';
    for (var i = 0; i < order.items.length; i++) {
        var item = order.items[i];
        var cls = 'order-item';
        var badge = '';

        if (item.is_full_set) {
            cls += ' item-full-set';
            badge = '<span class="item-badge item-badge-set">SET</span>';
        } else if (item.is_bonus) {
            cls += ' item-bonus';
            badge = '<span class="item-badge item-badge-bonus">GRATIS</span>';
        } else if (item.is_custom) {
            cls += ' item-custom';
            badge = '<span class="item-badge item-badge-custom">R\u0118CZNY</span>';
        }

        var name = item.product_name;
        if (name.length > 35) name = name.substring(0, 35) + '...';

        var sizeBadge = item.selected_size ? ' <span class="size-badge">' + escapeHtml(item.selected_size) + '</span>' : '';

        var priceHTML = '';
        if (includeFinancials && item.total) {
            priceHTML = '<span class="item-price">' + parseFloat(item.total).toFixed(2) + ' PLN</span>';
        }

        itemsHTML += '<div class="' + cls + '">' +
            badge +
            '<span class="item-name">' + escapeHtml(name) + sizeBadge + '</span>' +
            '<span class="item-qty">x' + item.quantity + '</span>' +
            priceHTML +
            '</div>';
    }

    var amountHTML = '';
    if (includeFinancials) {
        amountHTML = '<span class="order-card-amount">' + parseFloat(order.total_amount).toFixed(2) + ' PLN</span>';
    }

    return '<div class="order-card" data-order-id="' + order.order_id + '">' +
        '<div class="order-card-header">' +
        '<div class="order-card-main">' +
        '<div class="order-card-number">' +
        '<a href="' + detailUrl + '">' + escapeHtml(order.order_number) + '</a>' +
        '</div>' +
        '<div class="order-card-customer">' + escapeHtml(order.customer_name) + '</div>' +
        '<div class="order-card-meta">' +
        '<span>' + escapeHtml(order.created_at) + '</span>' +
        '<span>' + order.item_count + ' prod.</span>' +
        amountHTML +
        '</div>' +
        '</div>' +
        '</div>' +
        '<div class="order-card-body">' +
        '<div class="order-card-items">' + itemsHTML + '</div>' +
        '</div>' +
        '</div>';
}

function renderPagination(totalPages, container) {
    if (!container || totalPages <= 1) {
        if (container) container.innerHTML = '';
        return;
    }

    var html = '';
    html += '<button class="pagination-btn"' + (currentPage === 1 ? ' disabled' : '') + ' data-page="' + (currentPage - 1) + '">&laquo;</button>';

    var pages = getPaginationRange(currentPage, totalPages, 7);
    for (var i = 0; i < pages.length; i++) {
        var p = pages[i];
        if (p === '...') {
            html += '<span class="pagination-ellipsis">...</span>';
        } else {
            html += '<button class="pagination-btn' + (p === currentPage ? ' active' : '') + '" data-page="' + p + '">' + p + '</button>';
        }
    }

    html += '<button class="pagination-btn"' + (currentPage === totalPages ? ' disabled' : '') + ' data-page="' + (currentPage + 1) + '">&raquo;</button>';

    container.innerHTML = html;

    var buttons = container.querySelectorAll('.pagination-btn');
    for (var j = 0; j < buttons.length; j++) {
        buttons[j].addEventListener('click', function () {
            if (this.disabled) return;
            currentPage = parseInt(this.getAttribute('data-page'), 10);
            renderOrderCards();
            var tabEl = document.getElementById('tab-orders');
            if (tabEl) tabEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    }
}

/* ==========================================
   4. PRODUCTS TAB - SORTING
   ========================================== */

function initializeProductsTab() {
    var sortSelect = document.getElementById('productsSortSelect');
    if (!sortSelect) return;

    sortSelect.addEventListener('change', function () {
        sortProductsTable(this.value);
    });
}

function sortProductsTable(sortKey) {
    var table = document.getElementById('productsAggTable');
    if (!table) return;

    var tbody = table.querySelector('tbody');
    var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));

    rows.sort(function (a, b) {
        switch (sortKey) {
            case 'quantity-desc': return parseFloat(b.dataset.quantity) - parseFloat(a.dataset.quantity);
            case 'quantity-asc': return parseFloat(a.dataset.quantity) - parseFloat(b.dataset.quantity);
            case 'name-asc': return (a.dataset.productName || '').localeCompare(b.dataset.productName || '');
            case 'name-desc': return (b.dataset.productName || '').localeCompare(a.dataset.productName || '');
            case 'revenue-desc': return parseFloat(b.dataset.revenue) - parseFloat(a.dataset.revenue);
            case 'revenue-asc': return parseFloat(a.dataset.revenue) - parseFloat(b.dataset.revenue);
            default: return 0;
        }
    });

    for (var i = 0; i < rows.length; i++) {
        tbody.appendChild(rows[i]);
    }
}

/* ==========================================
   5. SETS MATRIX RENDERING
   ========================================== */

function renderSetsMatrix(setsData) {
    var container = document.getElementById('setsContainer');
    if (!container || !setsData) return;

    if (setsData.length === 0) {
        container.innerHTML = '';
        return;
    }

    var lockSvg = '<svg class="slot-lock" width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1a2 2 0 0 1 2 2v4H6V3a2 2 0 0 1 2-2zm3 6V3a3 3 0 0 0-6 0v4a2 2 0 0 0-2 2v5a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2z"/></svg>';
    var checkSvg = '<svg class="slot-check slot-check-new" width="18" height="18" viewBox="0 0 16 16" fill="currentColor"><path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/></svg>';
    var reservedSvg = '<svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor"><path d="M8 3.5a.5.5 0 0 0-1 0V9a.5.5 0 0 0 .252.434l3.5 2a.5.5 0 0 0 .496-.868L8 8.71V3.5z"/><path d="M8 16A8 8 0 1 0 8 0a8 8 0 0 0 0 16zm7-8A7 7 0 1 1 1 8a7 7 0 0 1 14 0z"/></svg>';

    var html = '';
    for (var s = 0; s < setsData.length; s++) {
        var set = setsData[s];
        var fullSetProd = null;

        html += '<div class="set-matrix-card">';
        html += '<div class="set-matrix-header">';
        if (set.set_image) {
            html += '<img src="/static/' + escapeHtml(set.set_image) + '" alt="' + escapeHtml(set.set_name) + '" class="set-image">';
        }
        html += '<div class="set-info">';
        html += '<h3 class="set-name">' + escapeHtml(set.set_name) + '</h3>';
        if (set.has_limit) {
            html += '<span class="set-count">' + set.ordered_sets + ' / ' + set.set_max_sets + ' kompletnych setów</span>';
        } else {
            html += '<span class="set-count">' + set.ordered_sets + ' kompletnych setów (bez limitu)</span>';
        }
        html += '</div>';
        if (s === 0) {
            html += '<button type="button" class="matrix-toggle-btn" id="matrixToggleNames" title="Pokaż imiona i nazwiska">';
            html += '<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M11 6a3 3 0 1 1-6 0 3 3 0 0 1 6 0z"/><path fill-rule="evenodd" d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8zm8-7a7 7 0 0 0-5.468 11.37C3.242 11.226 4.805 10 8 10s4.757 1.225 5.468 2.37A7 7 0 0 0 8 1z"/></svg>';
            html += '<span>Imiona</span></button>';
        }
        html += '</div>';

        if (set.products && set.products.length > 0) {
            html += '<div class="set-matrix-table-wrap"><table class="set-matrix-table"><thead><tr>';
            html += '<th class="matrix-product-col">Produkt</th>';
            for (var col = 0; col < set.set_max_sets; col++) {
                html += '<th class="matrix-slot-col text-center">Set ' + (col + 1) + '</th>';
            }
            if (set.has_limit) {
                html += '<th class="matrix-slot-col matrix-locked-col text-center">Set ' + (set.set_max_sets + 1) + '</th>';
            }
            html += '</tr></thead><tbody>';

            for (var p = 0; p < set.products.length; p++) {
                var prod = set.products[p];
                if (prod.is_full_set) {
                    fullSetProd = prod;
                    continue;
                }
                html += '<tr>';
                html += '<td class="matrix-product-col">';
                html += '<span>' + escapeHtml(prod.product_name) + (prod.selected_size ? ' <span class="size-badge">' + escapeHtml(prod.selected_size) + '</span>' : '') + '</span>';
                if (prod.reserved && prod.reserved > 0) {
                    var resCustomers = (prod.reserved_customers && prod.reserved_customers.length > 0) ? prod.reserved_customers.join(', ') : '';
                    var resTitle = resCustomers || ('W rezerwacji: ' + prod.reserved);
                    html += '<span class="slot-reserved-badge" data-tooltip="' + escapeHtml(resTitle) + '">' + reservedSvg + prod.reserved + '</span>';
                }
                html += '</td>';

                for (var sl = 0; sl < set.set_max_sets; sl++) {
                    html += '<td class="matrix-slot-col text-center">';
                    var slot = prod.slots && prod.slots[sl];
                    var isFilled = slot && (typeof slot === 'object' ? slot.filled : slot);
                    if (isFilled) {
                        var customerName = (slot && typeof slot === 'object' && slot.customer) ? slot.customer : '';
                        var svgHtml = '<svg class="slot-check slot-check-new slot-icon-view" width="18" height="18" viewBox="0 0 16 16" fill="currentColor"><path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/></svg>';
                        if (customerName) {
                            var nameParts = customerName.split(' ', 2);
                            var nameHtml = '<span class="slot-name-view"><span class="slot-first-name">' + escapeHtml(nameParts[0]) + '</span>';
                            if (nameParts.length > 1) {
                                nameHtml += '<span class="slot-last-name">' + escapeHtml(nameParts.slice(1).join(' ')) + '</span>';
                            }
                            nameHtml += '</span>';
                            html += '<span class="slot-check-wrap" data-tooltip="' + escapeHtml(customerName) + '">' + svgHtml + nameHtml + '</span>';
                        } else {
                            html += svgHtml;
                        }
                    }
                    html += '</td>';
                }
                if (set.has_limit) {
                    html += '<td class="matrix-slot-col matrix-locked-col text-center">' + lockSvg + '</td>';
                }
                html += '</tr>';
            }

            html += '</tbody></table></div>';

            // Full set as separate element below table
            if (fullSetProd) {
                html += '<div class="full-set-summary">';
                html += '<span class="item-badge item-badge-set">SET</span>';
                html += '<span class="full-set-label">' + escapeHtml(fullSetProd.product_name) + '</span>';
                html += '<span class="full-set-count">' + fullSetProd.total_ordered + '</span>';
                html += '<span class="full-set-unit">szt. sprzedanych</span>';
                if (fullSetProd.reserved && fullSetProd.reserved > 0) {
                    var fsResCustomers = (fullSetProd.reserved_customers && fullSetProd.reserved_customers.length > 0) ? fullSetProd.reserved_customers.join(', ') : '';
                    var fsResTitle = fsResCustomers || ('W rezerwacji: ' + fullSetProd.reserved);
                    html += '<span class="slot-reserved-badge" data-tooltip="' + escapeHtml(fsResTitle) + '">' + reservedSvg + fullSetProd.reserved + '</span>';
                }
                html += '</div>';
            }
            // Total sets sold summary
            var totalSetsSold = (set.total_sets_sold !== undefined) ? set.total_sets_sold : set.ordered_sets;
            var fullSetSold = (set.full_set_sold !== undefined) ? set.full_set_sold : 0;
            html += '<div class="set-total-summary">';
            html += '<span>Łącznie sprzedanych setów:</span>';
            html += '<span class="set-total-count">' + totalSetsSold + '</span>';
            html += '<span class="set-total-detail">(' + set.ordered_sets + ' kompletnych + ' + fullSetSold + ' pojedynczych)</span>';
            html += '</div>';
            if (set.bonus_items_count && set.bonus_items_count > 0) {
                html += '<div class="set-bonus-summary">';
                html += '<span class="item-badge item-badge-bonus">GRATIS</span>';
                html += '<span>Gratisów w zamówieniach:</span>';
                html += '<span class="set-total-count">' + set.bonus_items_count + '</span>';
                html += '<span class="set-total-detail">szt.</span>';
                html += '</div>';
            }
        }
        html += '</div>';
    }

    container.innerHTML = html;

    // Re-apply names mode and re-bind toggle after re-render
    if (_showNames) {
        container.classList.add('show-names');
    }
    var btn = document.getElementById('matrixToggleNames');
    if (btn) {
        if (_showNames) btn.classList.add('active');
        btn.addEventListener('click', function () {
            _showNames = !_showNames;
            _applyNamesMode(_showNames);
            this.classList.toggle('active', _showNames);
            try { localStorage.setItem('matrixShowNames', _showNames); } catch (e) { /* ignore */ }
        });
    }
}

/* ==========================================
   6. PRODUCTS TABLE RENDERING
   ========================================== */

function renderProductsTable(productsData) {
    var table = document.getElementById('productsAggTable');
    if (!table || !productsData) return;

    var tbody = table.querySelector('tbody');
    if (!tbody) return;

    var includeFinancials = window.INCLUDE_FINANCIALS;
    var html = '';

    for (var i = 0; i < productsData.length; i++) {
        var product = productsData[i];
        var revenue = product.revenue || 0;

        html += '<tr data-product-name="' + escapeHtml(product.product_name) + '"';
        html += ' data-quantity="' + product.total_quantity + '"';
        html += ' data-revenue="' + (includeFinancials ? revenue : 0) + '"';
        html += ' data-orders="' + product.order_count + '">';

        html += '<td><div class="product-name-cell">';
        if (product.is_full_set) {
            html += '<span class="item-badge item-badge-set">SET</span>';
        } else if (product.is_bonus) {
            html += '<span class="item-badge item-badge-bonus">GRATIS</span>';
        } else if (product.is_custom) {
            html += '<span class="item-badge item-badge-custom">RĘCZNY</span>';
        }
        html += '<span>' + escapeHtml(product.product_name) + '</span>';
        html += '</div></td>';

        html += '<td class="text-center">' + product.order_count + '</td>';
        html += '<td class="text-center"><strong>' + product.total_quantity + '</strong></td>';

        if (includeFinancials) {
            html += '<td class="text-right"><strong>' + parseFloat(revenue).toFixed(2) + ' PLN</strong></td>';
        }

        html += '</tr>';
    }

    tbody.innerHTML = html;

    // Re-apply current sort
    var sortSelect = document.getElementById('productsSortSelect');
    if (sortSelect && sortSelect.value) {
        sortProductsTable(sortSelect.value);
    }
}

/* ==========================================
   7. SOCKET.IO - REAL-TIME UPDATES
   ========================================== */

var socket = null;

function initializeSocketIO() {
    if (typeof io === 'undefined') {
        updateSocketStatus('error', 'Socket.IO niedostępny');
        return;
    }

    var pageId = window.OFFER_PAGE_ID;
    if (!pageId) return;

    socket = io({
        reconnection: true,
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
    });

    socket.on('connect', function () {
        updateSocketStatus('connected', 'Połączono');
        socket.emit('join_offer_admin', { page_id: pageId });
    });

    socket.on('disconnect', function () {
        updateSocketStatus('disconnected', 'Rozłączono');
    });

    socket.on('reconnecting', function () {
        updateSocketStatus('connecting', 'Łączenie...');
    });

    // Visitor count updates
    socket.on('visitor_count_update', function (data) {
        var countdownEl = document.getElementById('countdownVisitors');
        var orderEl = document.getElementById('orderPageVisitors');
        if (countdownEl) countdownEl.textContent = data.countdown || 0;
        if (orderEl) orderEl.textContent = data.order || 0;

        // Update active reservations count (included in periodic broadcast)
        if (data.active_reservations !== undefined) {
            animateStatUpdate('statReservationsValue', data.active_reservations);
        }
    });

    // New order notification
    socket.on('new_order', function (data) {
        // Add to orders array
        window.LIVE_ORDERS.unshift(data);
        filteredOrders = window.LIVE_ORDERS.slice();

        // Update tab count
        var tabCount = document.getElementById('ordersTabCount');
        if (tabCount) tabCount.textContent = window.LIVE_ORDERS.length;
        var totalCount = document.getElementById('ordersTotalCount');
        if (totalCount) totalCount.textContent = window.LIVE_ORDERS.length;
        var displayCount = document.getElementById('ordersDisplayCount');
        if (displayCount) displayCount.textContent = filteredOrders.length;

        // Re-render if orders tab is visible
        if (ordersRendered) {
            currentPage = 1;
            applyOrdersFilters();
        }

        // Update chart with new timestamp
        if (data.created_at) {
            window.ORDER_TIMESTAMPS.push(data.created_at);
            rebuildChart();
        }
    });

    // Stats update (includes sets + products + timestamps data)
    socket.on('stats_update', function (data) {
        animateStatUpdate('statOrdersValue', data.total_orders);
        animateStatUpdate('statCustomersValue', data.unique_customers);
        animateStatUpdate('statItemsValue', data.total_items);
        animateStatUpdate('statReservationsValue', data.active_reservations);

        if (data.total_revenue !== undefined) {
            var revEl = document.getElementById('statRevenueValue');
            if (revEl) {
                revEl.textContent = parseFloat(data.total_revenue).toFixed(2) + ' PLN';
                flashElement(revEl.closest('.stat-card'));
            }
        }
        if (data.avg_order_value !== undefined) {
            var avgEl = document.getElementById('statAvgValue');
            if (avgEl) {
                avgEl.textContent = parseFloat(data.avg_order_value).toFixed(2) + ' PLN';
            }
        }

        // Re-render sets matrix
        if (data.sets) {
            window.LIVE_SETS = data.sets;
            renderSetsMatrix(data.sets);
        }

        // Re-render products table
        if (data.products_aggregated) {
            window.LIVE_PRODUCTS = data.products_aggregated;
            renderProductsTable(data.products_aggregated);

            // Update products tab count badge
            var prodTabCount = document.querySelector('.live-tab-button[data-tab="tab-products"] .tab-count');
            if (prodTabCount) prodTabCount.textContent = data.products_aggregated.length;
        }

        // Update chart timestamps
        if (data.order_timestamps) {
            window.ORDER_TIMESTAMPS = data.order_timestamps;
            rebuildChart();
        }
    });

    // Reservations update (triggered by reserve/release actions)
    socket.on('reservations_update', function (data) {
        var byProduct = data.by_product || {};
        var customersByProduct = data.customers_by_product || {};

        // Update reservation badges in sets matrix
        if (window.LIVE_SETS) {
            for (var s = 0; s < window.LIVE_SETS.length; s++) {
                var set = window.LIVE_SETS[s];
                if (!set.products) continue;
                for (var p = 0; p < set.products.length; p++) {
                    var pid = set.products[p].product_id;
                    set.products[p].reserved = byProduct[pid] || 0;
                    set.products[p].reserved_customers = customersByProduct[String(pid)] || [];
                }
            }
            renderSetsMatrix(window.LIVE_SETS);
        }

        // Update active reservations stat card
        if (data.total !== undefined) {
            animateStatUpdate('statReservationsValue', data.total);
        }
    });
}

function updateSocketStatus(status, text) {
    var statusEl = document.getElementById('socketStatus');
    if (!statusEl) return;
    var dot = statusEl.querySelector('.socket-dot');
    var textEl = statusEl.querySelector('.socket-text');

    dot.className = 'socket-dot socket-dot-' + status;
    textEl.textContent = text;
}

function animateStatUpdate(elementId, newValue) {
    var el = document.getElementById(elementId);
    if (!el) return;
    var currentVal = el.textContent.trim();
    var newVal = String(newValue);
    if (currentVal !== newVal) {
        el.textContent = newVal;
        flashElement(el.closest('.stat-card'));
    }
}

function flashElement(el) {
    if (!el) return;
    el.classList.add('stat-flash');
    setTimeout(function () {
        el.classList.remove('stat-flash');
    }, 1000);
}

/* ==========================================
   UTILITY FUNCTIONS
   ========================================== */

function debounce(func, wait) {
    var timeout;
    return function () {
        var context = this;
        var args = arguments;
        clearTimeout(timeout);
        timeout = setTimeout(function () { func.apply(context, args); }, wait);
    };
}

function escapeHtml(text) {
    if (!text) return '';
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getPaginationRange(current, total, maxVisible) {
    if (total <= maxVisible) {
        var arr = [];
        for (var i = 1; i <= total; i++) arr.push(i);
        return arr;
    }
    var pages = [];
    var half = Math.floor(maxVisible / 2);
    var start = Math.max(2, current - half);
    var end = Math.min(total - 1, current + half);
    if (current <= half + 1) end = Math.min(total - 1, maxVisible - 1);
    if (current >= total - half) start = Math.max(2, total - maxVisible + 2);
    pages.push(1);
    if (start > 2) pages.push('...');
    for (var j = start; j <= end; j++) pages.push(j);
    if (end < total - 1) pages.push('...');
    pages.push(total);
    return pages;
}

/* ==========================================
   MATRIX NAMES TOGGLE
   ========================================== */

var _showNames = false;

function initializeMatrixToggle() {
    var btn = document.getElementById('matrixToggleNames');
    if (!btn) return;

    // Restore saved preference
    try {
        _showNames = localStorage.getItem('matrixShowNames') === 'true';
    } catch (e) { /* ignore */ }

    if (_showNames) {
        _applyNamesMode(true);
        btn.classList.add('active');
    }

    btn.addEventListener('click', function () {
        _showNames = !_showNames;
        _applyNamesMode(_showNames);
        btn.classList.toggle('active', _showNames);
        try {
            localStorage.setItem('matrixShowNames', _showNames);
        } catch (e) { /* ignore */ }
    });
}

function _applyNamesMode(show) {
    var container = document.getElementById('setsContainer');
    if (!container) return;
    if (show) {
        container.classList.add('show-names');
    } else {
        container.classList.remove('show-names');
    }
}

/* ==========================================
   META COUNTDOWNS (start/end dates)
   ========================================== */

var _countdownInterval = null;

function initializeMetaCountdowns() {
    updateMetaCountdowns();
    _countdownInterval = setInterval(updateMetaCountdowns, 1000);
}

function updateMetaCountdowns() {
    var now = new Date();
    updateSingleCountdown('metaStartValue', window.STARTS_AT, now, 'Rozpoczęcie');
    updateSingleCountdown('metaEndValue', window.ENDS_AT, now, 'Zakończenie');
}

function updateSingleCountdown(elementId, isoString, now, label) {
    var el = document.getElementById(elementId);
    if (!el) return;

    if (!isoString) {
        el.textContent = label === 'Rozpoczęcie' ? 'Bez daty' : 'Bez limitu';
        return;
    }

    var target = new Date(isoString);
    var diff = target - now;

    if (diff <= 0) {
        // Already passed — show date/time
        var dd = String(target.getDate()).padStart(2, '0');
        var mm = String(target.getMonth() + 1).padStart(2, '0');
        var yyyy = target.getFullYear();
        var hh = String(target.getHours()).padStart(2, '0');
        var min = String(target.getMinutes()).padStart(2, '0');
        el.textContent = dd + '.' + mm + '.' + yyyy + ' ' + hh + ':' + min;
        el.classList.remove('meta-value-countdown');
    } else {
        // Show countdown hh:mm:ss
        var totalSec = Math.floor(diff / 1000);
        var hours = Math.floor(totalSec / 3600);
        var minutes = Math.floor((totalSec % 3600) / 60);
        var seconds = totalSec % 60;
        el.textContent = String(hours).padStart(2, '0') + ':' +
            String(minutes).padStart(2, '0') + ':' +
            String(seconds).padStart(2, '0');
        el.classList.add('meta-value-countdown');
    }
}
