/**
 * Offer Summary Page
 * Tab switching, Chart.js with granularity toggle, orders search/pagination, products sorting
 * Based on offer-live.js without Socket.IO, JS matrix/products rendering, meta countdowns
 */

document.addEventListener('DOMContentLoaded', function () {
    initializeLiveTabs();
    initializeOrdersTimelineChart();
    initializeOrdersTab();
    initializeProductsTab();
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
                localStorage.setItem('offerSummaryActiveTab', targetTab);
            } catch (e) { /* ignore */ }
        });
    });

    try {
        var savedTab = localStorage.getItem('offerSummaryActiveTab');
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
    filteredOrders = (window.SUMMARY_ORDERS || []).slice();

    var searchInput = document.getElementById('ordersSearch');
    if (searchInput) {
        searchInput.addEventListener('input', debounce(function () {
            currentPage = 1;
            applyOrdersFilters();
        }, 300));
    }
}

function applyOrdersFilters() {
    var allOrders = window.SUMMARY_ORDERS || [];
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

    if (filteredOrders.length === 0 && (window.SUMMARY_ORDERS || []).length > 0) {
        filteredOrders = (window.SUMMARY_ORDERS || []).slice();
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

        var statusIcon = '';

        if (item.is_full_set) {
            cls += ' item-full-set';
            badge = '<span class="item-badge item-badge-set">SET</span>';
        } else if (item.is_bonus) {
            cls += ' item-bonus';
            badge = '<span class="item-badge item-badge-bonus">GRATIS</span>';
        } else if (item.is_custom) {
            cls += ' item-custom';
            badge = '<span class="item-badge item-badge-custom">R\u0118CZNY</span>';
        } else if (item.is_set_fulfilled === true) {
            cls += ' item-fulfilled';
            statusIcon = '<span class="item-status item-status-ok">&#10003;</span>';
        } else if (item.is_set_fulfilled === false) {
            cls += ' item-unfulfilled';
            statusIcon = '<span class="item-status item-status-fail">&#10007;</span>';
        }

        var name = item.product_name;
        if (name.length > 35) name = name.substring(0, 35) + '...';

        var priceHTML = '';
        if (includeFinancials && item.total) {
            priceHTML = '<span class="item-price">' + parseFloat(item.total).toFixed(2) + ' PLN</span>';
        }

        itemsHTML += '<div class="' + cls + '">' +
            badge +
            '<span class="item-name">' + escapeHtml(name) + '</span>' +
            '<span class="item-qty">x' + item.quantity + '</span>' +
            statusIcon +
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
            case 'fulfillment-desc': return parseFloat(b.dataset.fulfillment) - parseFloat(a.dataset.fulfillment);
            case 'fulfillment-asc': return parseFloat(a.dataset.fulfillment) - parseFloat(b.dataset.fulfillment);
            default: return 0;
        }
    });

    for (var i = 0; i < rows.length; i++) {
        tbody.appendChild(rows[i]);
    }
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

function initializeMatrixToggle() {
    var btn = document.getElementById('matrixToggleNames');
    if (!btn) return;

    var container = document.querySelector('.sets-matrix-grid');
    if (!container) return;

    var showNames = false;
    try {
        showNames = localStorage.getItem('matrixShowNames') === 'true';
    } catch (e) { /* ignore */ }

    if (showNames) {
        container.classList.add('show-names');
        btn.classList.add('active');
    }

    btn.addEventListener('click', function () {
        showNames = !showNames;
        container.classList.toggle('show-names', showNames);
        btn.classList.toggle('active', showNames);
        try {
            localStorage.setItem('matrixShowNames', showNames);
        } catch (e) { /* ignore */ }
    });
}
