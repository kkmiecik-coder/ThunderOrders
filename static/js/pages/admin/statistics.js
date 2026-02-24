/**
 * Strona Statystyk Admina
 * - Przełączanie zakładek z URL param support
 * - Lazy loading danych via AJAX
 * - Cache załadowanych danych
 * - Chart.js z dark mode support (MutationObserver)
 */

(function () {
    'use strict';

    // ========================================
    // Stan aplikacji
    // ========================================

    var tabDataCache = {};
    var tabCharts = {};
    var currentRanges = {};

    var TAB_API_MAP = {
        przychody: '/admin/statistics/api/revenue',
        zamowienia: '/admin/statistics/api/orders',
        produkty: '/admin/statistics/api/products',
        klienci: '/admin/statistics/api/clients',
        exclusive: '/admin/statistics/api/exclusive',
        wysylka: '/admin/statistics/api/shipping',
        proxy: '/admin/statistics/api/proxy'
    };

    // ========================================
    // Pomocnicze: Dark mode & kolory
    // ========================================

    function isDarkMode() {
        return document.documentElement.getAttribute('data-theme') === 'dark';
    }

    function getChartColors() {
        var dark = isDarkMode();
        return {
            gridColor: dark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.05)',
            textColor: dark ? 'rgba(255, 255, 255, 0.7)' : '#666',
            tooltipBg: dark ? 'rgba(15, 12, 41, 0.95)' : 'rgba(0, 0, 0, 0.8)',
            tooltipBorder: dark ? 'rgba(240, 147, 251, 0.3)' : 'transparent',
            tooltipTitleColor: dark ? '#f0f0f0' : '#fff',
            tooltipBodyColor: dark ? 'rgba(255, 255, 255, 0.8)' : '#fff',
            lineColor: dark ? '#f093fb' : '#8338EC',
            lineBgColor: dark ? 'rgba(240, 147, 251, 0.15)' : 'rgba(131, 56, 236, 0.1)',
            barColor: dark ? 'rgba(240, 147, 251, 0.7)' : 'rgba(131, 56, 236, 0.7)',
            barBorderColor: dark ? '#f093fb' : '#5A189A',
            pointBorderColor: dark ? 'rgba(15, 12, 41, 0.9)' : '#fff',
            pieColors: dark
                ? ['#f093fb', '#4facfe', '#ff6b6b', '#51cf66', '#ffd43b', '#845ef7', '#ff922b', '#20c997', '#339af0', '#e64980']
                : ['#8338EC', '#4facfe', '#f5576c', '#2ecc71', '#f1c40f', '#764ba2', '#e67e22', '#1abc9c', '#3498db', '#e74c6c']
        };
    }

    // ========================================
    // Przełączanie zakładek
    // ========================================

    function initTabs() {
        var tabs = document.querySelectorAll('.statistics-tab');
        var panels = document.querySelectorAll('.tab-panel');

        tabs.forEach(function (tab) {
            tab.addEventListener('click', function () {
                var targetTab = this.getAttribute('data-tab');

                // Ustaw aktywną zakładkę
                tabs.forEach(function (t) { t.classList.remove('active'); });
                panels.forEach(function (p) { p.classList.remove('active'); });

                this.classList.add('active');
                var panel = document.getElementById('tab-' + targetTab);
                if (panel) {
                    panel.classList.add('active');
                }

                // Aktualizuj URL param
                var url = new URL(window.location);
                url.searchParams.set('tab', targetTab);
                window.history.replaceState({}, '', url);

                // Załaduj dane jeśli jeszcze nie załadowane
                loadTabData(targetTab);
            });
        });

        // Sprawdź URL param na start
        var params = new URLSearchParams(window.location.search);
        var initialTab = params.get('tab') || 'przychody';

        // Aktywuj odpowiednią zakładkę
        var targetTabBtn = document.querySelector('.statistics-tab[data-tab="' + initialTab + '"]');
        if (targetTabBtn) {
            targetTabBtn.click();
        } else {
            // Fallback: aktywuj pierwszą
            loadTabData('przychody');
        }
    }

    // ========================================
    // Ładowanie danych zakładki
    // ========================================

    function loadTabData(tabName, range) {
        var cacheKey = tabName + '_' + (range || 'default');

        // Użyj cache jeśli jest
        if (tabDataCache[cacheKey]) {
            renderTab(tabName, tabDataCache[cacheKey]);
            return;
        }

        var apiUrl = TAB_API_MAP[tabName];
        if (!apiUrl) return;

        var queryRange = range || currentRanges[tabName] || '30d';
        currentRanges[tabName] = queryRange;

        fetch(apiUrl + '?range=' + queryRange)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.success) {
                    tabDataCache[cacheKey] = data;
                    renderTab(tabName, data);
                } else {
                    showTabError(tabName, 'Nie udalo sie zaladowac danych.');
                }
            })
            .catch(function () {
                showTabError(tabName, 'Blad polaczenia z serwerem.');
            });
    }

    function showTabError(tabName, msg) {
        var panel = document.getElementById('tab-' + tabName);
        if (panel) {
            panel.innerHTML = '<div class="tab-error">' + msg + '</div>';
        }
    }

    // ========================================
    // Renderowanie zakładek
    // ========================================

    function renderTab(tabName, data) {
        switch (tabName) {
            case 'przychody': renderRevenue(data); break;
            case 'zamowienia': renderOrders(data); break;
            case 'produkty': renderProducts(data); break;
            case 'klienci': renderClients(data); break;
            case 'exclusive': renderExclusive(data); break;
            case 'wysylka': renderShipping(data); break;
            case 'proxy': renderProxy(data); break;
        }
    }

    // ========================================
    // Tab: Przychody
    // ========================================

    function renderRevenue(data) {
        var panel = document.getElementById('tab-przychody');
        var html = '';

        // KPI
        html += buildKpiGrid(data.kpis);

        // Wykres liniowy z dropdown
        html += '<div class="stats-widget">';
        html += '<div class="stats-widget-header">';
        html += '<h3 class="stats-widget-title">Przychody w czasie</h3>';
        html += buildRangeDropdown('przychody');
        html += '</div>';
        html += '<div class="stats-chart-container"><canvas id="chart-revenue-line"></canvas></div>';
        html += '</div>';

        // Metryki dodatkowe
        if (data.metrics) {
            html += '<div class="stats-metrics-row">';
            html += buildMetricCard('Srednia wartosc zamowienia', data.metrics.avg_order_value);
            html += buildMetricCard('Srednia marza produktow', data.metrics.avg_margin);
            html += '</div>';
        }

        // Tabela
        if (data.tables && data.tables[0]) {
            html += buildTableWidget(data.tables[0]);
        }

        panel.innerHTML = html;

        // Rysuj wykres
        if (data.charts && data.charts.main) {
            createLineChart('chart-revenue-line', data.charts.main, 'Przychod (PLN)', ' PLN');
        }

        // Dropdown event
        bindRangeDropdown('przychody');
    }

    // ========================================
    // Tab: Zamówienia
    // ========================================

    function renderOrders(data) {
        var panel = document.getElementById('tab-zamowienia');
        var html = '';

        // KPI
        html += buildKpiGrid(data.kpis);

        // Wykres słupkowy z dropdown
        html += '<div class="stats-widget">';
        html += '<div class="stats-widget-header">';
        html += '<h3 class="stats-widget-title">Zamowienia w czasie</h3>';
        html += buildRangeDropdown('zamowienia');
        html += '</div>';
        html += '<div class="stats-chart-container"><canvas id="chart-orders-bar"></canvas></div>';
        html += '</div>';

        // Wykresy kołowe
        html += '<div class="stats-charts-row">';
        html += '<div class="stats-widget">';
        html += '<h3 class="stats-widget-title">Podział wg typów</h3>';
        html += '<div class="stats-chart-container-small"><canvas id="chart-orders-pie-types"></canvas></div>';
        html += '</div>';
        html += '<div class="stats-widget">';
        html += '<h3 class="stats-widget-title">Podział wg statusów</h3>';
        html += '<div class="stats-chart-container-small"><canvas id="chart-orders-pie-statuses"></canvas></div>';
        html += '</div>';
        html += '</div>';

        // Metryki
        if (data.metrics) {
            html += '<div class="stats-metrics-row">';
            html += buildMetricCard('Srednia wartosc zamowienia', data.metrics.avg_order_value);
            html += buildMetricCard('Oplaconych w pelni', data.metrics.pct_fully_paid);
            html += '</div>';
        }

        panel.innerHTML = html;

        // Rysuj wykresy
        if (data.charts) {
            if (data.charts.bar) createBarChart('chart-orders-bar', data.charts.bar, 'Zamowienia');
            if (data.charts.pie_types) createPieChart('chart-orders-pie-types', data.charts.pie_types);
            if (data.charts.pie_statuses) createPieChart('chart-orders-pie-statuses', data.charts.pie_statuses);
        }

        bindRangeDropdown('zamowienia');
    }

    // ========================================
    // Tab: Produkty
    // ========================================

    function renderProducts(data) {
        var panel = document.getElementById('tab-produkty');
        var html = '';

        // KPI
        html += buildKpiGrid(data.kpis);

        // Wykres słupkowy: top produkty per przychód
        if (data.charts && data.charts.bar_revenue && data.charts.bar_revenue.labels.length > 0) {
            html += '<div class="stats-widget">';
            html += '<h3 class="stats-widget-title">Top 10 produktów wg przychodu</h3>';
            html += '<div class="stats-chart-container"><canvas id="chart-products-bar"></canvas></div>';
            html += '</div>';
        }

        // Tabele
        if (data.tables) {
            data.tables.forEach(function (t) {
                html += buildTableWidget(t);
            });
        }

        panel.innerHTML = html;

        if (data.charts && data.charts.bar_revenue && data.charts.bar_revenue.labels.length > 0) {
            createHorizontalBarChart('chart-products-bar', data.charts.bar_revenue, ' PLN');
        }
    }

    // ========================================
    // Tab: Klienci
    // ========================================

    function renderClients(data) {
        var panel = document.getElementById('tab-klienci');
        var html = '';

        // KPI
        html += buildKpiGrid(data.kpis);

        // Wykres liniowy: rejestracje
        html += '<div class="stats-widget">';
        html += '<div class="stats-widget-header">';
        html += '<h3 class="stats-widget-title">Rejestracje w czasie</h3>';
        html += buildRangeDropdown('klienci');
        html += '</div>';
        html += '<div class="stats-chart-container"><canvas id="chart-clients-line"></canvas></div>';
        html += '</div>';

        // Metryki
        if (data.metrics) {
            html += '<div class="stats-metrics-row">';
            html += buildMetricCard('Srednia wartosc klienta', data.metrics.avg_client_value);
            html += buildMetricCard('Z wiecej niz 1 zamowieniem', data.metrics.pct_repeat);
            html += '</div>';
        }

        // Tabela
        if (data.tables && data.tables[0]) {
            html += buildTableWidget(data.tables[0]);
        }

        panel.innerHTML = html;

        if (data.charts && data.charts.main) {
            createLineChart('chart-clients-line', data.charts.main, 'Rejestracje', '');
        }

        bindRangeDropdown('klienci');
    }

    // ========================================
    // Tab: Exclusive
    // ========================================

    function renderExclusive(data) {
        var panel = document.getElementById('tab-exclusive');
        var html = '';

        // KPI
        html += buildKpiGrid(data.kpis);

        // Wykres słupkowy: przychód per strona
        if (data.charts && data.charts.bar_revenue && data.charts.bar_revenue.labels.length > 0) {
            html += '<div class="stats-widget">';
            html += '<h3 class="stats-widget-title">Przychod per strona Exclusive</h3>';
            html += '<div class="stats-chart-container"><canvas id="chart-exclusive-bar"></canvas></div>';
            html += '</div>';
        }

        // Tabela
        if (data.tables && data.tables[0]) {
            html += buildTableWidget(data.tables[0]);
        }

        panel.innerHTML = html;

        if (data.charts && data.charts.bar_revenue && data.charts.bar_revenue.labels.length > 0) {
            createHorizontalBarChart('chart-exclusive-bar', data.charts.bar_revenue, ' PLN');
        }
    }

    // ========================================
    // Tab: Wysyłka
    // ========================================

    function renderShipping(data) {
        var panel = document.getElementById('tab-wysylka');
        var html = '';

        // KPI
        html += buildKpiGrid(data.kpis);

        // Wykresy kołowe
        html += '<div class="stats-charts-row">';

        if (data.charts && data.charts.pie_delivery && data.charts.pie_delivery.labels.length > 0) {
            html += '<div class="stats-widget">';
            html += '<h3 class="stats-widget-title">Metody dostawy</h3>';
            html += '<div class="stats-chart-container-small"><canvas id="chart-shipping-delivery"></canvas></div>';
            html += '</div>';
        }

        if (data.charts && data.charts.pie_couriers && data.charts.pie_couriers.labels.length > 0) {
            html += '<div class="stats-widget">';
            html += '<h3 class="stats-widget-title">Kurierzy</h3>';
            html += '<div class="stats-chart-container-small"><canvas id="chart-shipping-couriers"></canvas></div>';
            html += '</div>';
        }

        html += '</div>';

        // Tabela
        if (data.tables && data.tables[0]) {
            html += buildTableWidget(data.tables[0]);
        }

        panel.innerHTML = html;

        if (data.charts) {
            if (data.charts.pie_delivery && data.charts.pie_delivery.labels.length > 0) {
                createPieChart('chart-shipping-delivery', data.charts.pie_delivery);
            }
            if (data.charts.pie_couriers && data.charts.pie_couriers.labels.length > 0) {
                createPieChart('chart-shipping-couriers', data.charts.pie_couriers);
            }
        }
    }

    // ========================================
    // Tab: Proxy/Korea
    // ========================================

    function renderProxy(data) {
        var panel = document.getElementById('tab-proxy');
        var html = '';

        // KPI
        html += buildKpiGrid(data.kpis);

        // Wykresy kołowe
        html += '<div class="stats-charts-row">';

        if (data.charts && data.charts.pie_proxy && data.charts.pie_proxy.labels.length > 0) {
            html += '<div class="stats-widget">';
            html += '<h3 class="stats-widget-title">Statusy Proxy Orders</h3>';
            html += '<div class="stats-chart-container-small"><canvas id="chart-proxy-statuses"></canvas></div>';
            html += '</div>';
        }

        if (data.charts && data.charts.pie_poland && data.charts.pie_poland.labels.length > 0) {
            html += '<div class="stats-widget">';
            html += '<h3 class="stats-widget-title">Statusy Poland Orders</h3>';
            html += '<div class="stats-chart-container-small"><canvas id="chart-poland-statuses"></canvas></div>';
            html += '</div>';
        }

        html += '</div>';

        // Metryki
        if (data.metrics) {
            html += '<div class="stats-metrics-row">';
            html += buildMetricCard('Sr. koszt wysylki z Korei', data.metrics.avg_shipping_kr);
            html += buildMetricCard('Sr. koszt cla/VAT', data.metrics.avg_customs);
            html += '</div>';
        }

        panel.innerHTML = html;

        if (data.charts) {
            if (data.charts.pie_proxy && data.charts.pie_proxy.labels.length > 0) {
                createPieChart('chart-proxy-statuses', data.charts.pie_proxy);
            }
            if (data.charts.pie_poland && data.charts.pie_poland.labels.length > 0) {
                createPieChart('chart-poland-statuses', data.charts.pie_poland);
            }
        }
    }

    // ========================================
    // Budowanie komponentów HTML
    // ========================================

    function buildKpiGrid(kpis) {
        if (!kpis || kpis.length === 0) return '';
        var gradients = ['gradient-purple', 'gradient-pink', 'gradient-cyan'];
        var html = '<div class="stats-kpi-grid">';
        kpis.forEach(function (kpi, i) {
            html += '<div class="stat-kpi-card ' + gradients[i % 3] + '">';
            html += '<div class="stat-kpi-label">' + escapeHtml(kpi.label) + '</div>';
            html += '<div class="stat-kpi-value">' + escapeHtml(kpi.value) + '</div>';
            html += '</div>';
        });
        html += '</div>';
        return html;
    }

    function buildTableWidget(table) {
        if (!table || !table.rows || table.rows.length === 0) return '';
        var html = '<div class="stats-widget">';
        if (table.title) {
            html += '<h3 class="stats-widget-title">' + escapeHtml(table.title) + '</h3>';
        }
        html += '<div class="stats-table-container"><table class="stats-table">';
        html += '<thead><tr>';
        table.headers.forEach(function (h) {
            html += '<th>' + escapeHtml(h) + '</th>';
        });
        html += '</tr></thead><tbody>';
        table.rows.forEach(function (row) {
            html += '<tr>';
            row.forEach(function (cell) {
                html += '<td>' + escapeHtml(String(cell)) + '</td>';
            });
            html += '</tr>';
        });
        html += '</tbody></table></div></div>';
        return html;
    }

    function buildMetricCard(label, value) {
        return '<div class="stats-metric-card">' +
            '<div class="stats-metric-label">' + escapeHtml(label) + '</div>' +
            '<div class="stats-metric-value">' + escapeHtml(value || '-') + '</div>' +
            '</div>';
    }

    function buildRangeDropdown(tabName) {
        var currentRange = currentRanges[tabName] || '30d';
        var options = [
            { value: '7d', label: '7 dni' },
            { value: '14d', label: '14 dni' },
            { value: '30d', label: '30 dni' },
            { value: '3m', label: '3 miesiace' },
            { value: '12m', label: '12 miesiecy' },
            { value: 'ytd', label: 'Biezacy rok' }
        ];
        var html = '<select class="stats-range-dropdown" data-tab="' + tabName + '">';
        options.forEach(function (opt) {
            var selected = opt.value === currentRange ? ' selected' : '';
            html += '<option value="' + opt.value + '"' + selected + '>' + opt.label + '</option>';
        });
        html += '</select>';
        return html;
    }

    function bindRangeDropdown(tabName) {
        var dropdown = document.querySelector('.stats-range-dropdown[data-tab="' + tabName + '"]');
        if (!dropdown) return;
        dropdown.addEventListener('change', function () {
            var range = this.value;
            currentRanges[tabName] = range;
            // Wyczyść cache dla tego taba
            Object.keys(tabDataCache).forEach(function (key) {
                if (key.startsWith(tabName + '_')) {
                    delete tabDataCache[key];
                }
            });
            loadTabData(tabName, range);
        });
    }

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ========================================
    // Tworzenie wykresów Chart.js
    // ========================================

    function destroyChart(chartId) {
        if (tabCharts[chartId]) {
            tabCharts[chartId].destroy();
            delete tabCharts[chartId];
        }
    }

    function createLineChart(canvasId, chartData, label, suffix) {
        destroyChart(canvasId);
        var canvas = document.getElementById(canvasId);
        if (!canvas || typeof Chart === 'undefined') return;

        var colors = getChartColors();
        var ctx = canvas.getContext('2d');

        tabCharts[canvasId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: chartData.labels,
                datasets: [{
                    label: label,
                    data: chartData.values,
                    borderColor: colors.lineColor,
                    backgroundColor: colors.lineBgColor,
                    borderWidth: 2.5,
                    fill: true,
                    tension: 0.4,
                    pointRadius: chartData.labels.length > 60 ? 0 : 4,
                    pointHoverRadius: 6,
                    pointBackgroundColor: colors.lineColor,
                    pointBorderColor: colors.pointBorderColor,
                    pointBorderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: colors.tooltipBg,
                        borderColor: colors.tooltipBorder,
                        borderWidth: 1,
                        padding: 12,
                        titleColor: colors.tooltipTitleColor,
                        bodyColor: colors.tooltipBodyColor,
                        cornerRadius: 8,
                        callbacks: {
                            label: function (context) {
                                return context.parsed.y.toFixed(2) + (suffix || '');
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { color: colors.textColor },
                        grid: { color: colors.gridColor }
                    },
                    x: {
                        ticks: {
                            color: colors.textColor,
                            maxTicksLimit: 15
                        },
                        grid: { display: false }
                    }
                }
            }
        });
    }

    function createBarChart(canvasId, chartData, label) {
        destroyChart(canvasId);
        var canvas = document.getElementById(canvasId);
        if (!canvas || typeof Chart === 'undefined') return;

        var colors = getChartColors();
        var ctx = canvas.getContext('2d');

        tabCharts[canvasId] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: chartData.labels,
                datasets: [{
                    label: label,
                    data: chartData.values,
                    backgroundColor: colors.barColor,
                    borderColor: colors.barBorderColor,
                    borderWidth: 1,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: colors.tooltipBg,
                        borderColor: colors.tooltipBorder,
                        borderWidth: 1,
                        padding: 12,
                        titleColor: colors.tooltipTitleColor,
                        bodyColor: colors.tooltipBodyColor,
                        cornerRadius: 8
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { color: colors.textColor, stepSize: 1 },
                        grid: { color: colors.gridColor }
                    },
                    x: {
                        ticks: {
                            color: colors.textColor,
                            maxTicksLimit: 15
                        },
                        grid: { display: false }
                    }
                }
            }
        });
    }

    function createHorizontalBarChart(canvasId, chartData, suffix) {
        destroyChart(canvasId);
        var canvas = document.getElementById(canvasId);
        if (!canvas || typeof Chart === 'undefined') return;

        var colors = getChartColors();
        var ctx = canvas.getContext('2d');

        tabCharts[canvasId] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: chartData.labels,
                datasets: [{
                    data: chartData.values,
                    backgroundColor: colors.pieColors.slice(0, chartData.labels.length),
                    borderWidth: 0,
                    borderRadius: 4
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: colors.tooltipBg,
                        borderColor: colors.tooltipBorder,
                        borderWidth: 1,
                        padding: 12,
                        titleColor: colors.tooltipTitleColor,
                        bodyColor: colors.tooltipBodyColor,
                        cornerRadius: 8,
                        callbacks: {
                            label: function (context) {
                                return context.parsed.x.toFixed(2) + (suffix || '');
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        ticks: { color: colors.textColor },
                        grid: { color: colors.gridColor }
                    },
                    y: {
                        ticks: { color: colors.textColor },
                        grid: { display: false }
                    }
                }
            }
        });
    }

    function createPieChart(canvasId, chartData) {
        destroyChart(canvasId);
        var canvas = document.getElementById(canvasId);
        if (!canvas || typeof Chart === 'undefined') return;

        var colors = getChartColors();
        var ctx = canvas.getContext('2d');

        tabCharts[canvasId] = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: chartData.labels,
                datasets: [{
                    data: chartData.values,
                    backgroundColor: colors.pieColors.slice(0, chartData.labels.length),
                    borderWidth: 2,
                    borderColor: isDarkMode() ? 'rgba(15, 12, 41, 0.8)' : '#fff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '55%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: colors.textColor,
                            padding: 12,
                            usePointStyle: true,
                            pointStyleWidth: 8,
                            font: { size: 12 }
                        }
                    },
                    tooltip: {
                        backgroundColor: colors.tooltipBg,
                        borderColor: colors.tooltipBorder,
                        borderWidth: 1,
                        padding: 12,
                        titleColor: colors.tooltipTitleColor,
                        bodyColor: colors.tooltipBodyColor,
                        cornerRadius: 8,
                        callbacks: {
                            label: function (context) {
                                var total = context.dataset.data.reduce(function (a, b) { return a + b; }, 0);
                                var pct = total > 0 ? ((context.parsed / total) * 100).toFixed(1) : 0;
                                return context.label + ': ' + context.parsed + ' (' + pct + '%)';
                            }
                        }
                    }
                }
            }
        });
    }

    // ========================================
    // MutationObserver: dark mode switching
    // ========================================

    function initThemeObserver() {
        var observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                if (mutation.attributeName === 'data-theme') {
                    // Przerysuj wszystkie aktywne wykresy
                    Object.keys(tabCharts).forEach(function (chartId) {
                        var chart = tabCharts[chartId];
                        if (!chart) return;

                        var colors = getChartColors();

                        // Aktualizuj kolory tooltipów
                        if (chart.options.plugins && chart.options.plugins.tooltip) {
                            chart.options.plugins.tooltip.backgroundColor = colors.tooltipBg;
                            chart.options.plugins.tooltip.borderColor = colors.tooltipBorder;
                            chart.options.plugins.tooltip.titleColor = colors.tooltipTitleColor;
                            chart.options.plugins.tooltip.bodyColor = colors.tooltipBodyColor;
                        }

                        // Aktualizuj kolory osi
                        if (chart.options.scales) {
                            ['x', 'y'].forEach(function (axis) {
                                if (chart.options.scales[axis]) {
                                    if (chart.options.scales[axis].ticks) {
                                        chart.options.scales[axis].ticks.color = colors.textColor;
                                    }
                                    if (chart.options.scales[axis].grid) {
                                        chart.options.scales[axis].grid.color = colors.gridColor;
                                    }
                                }
                            });
                        }

                        // Aktualizuj kolory datasetu
                        if (chart.data.datasets[0]) {
                            var ds = chart.data.datasets[0];
                            var type = chart.config.type;

                            if (type === 'line') {
                                ds.borderColor = colors.lineColor;
                                ds.backgroundColor = colors.lineBgColor;
                                ds.pointBackgroundColor = colors.lineColor;
                                ds.pointBorderColor = colors.pointBorderColor;
                            } else if (type === 'bar' && chart.options.indexAxis !== 'y') {
                                ds.backgroundColor = colors.barColor;
                                ds.borderColor = colors.barBorderColor;
                            } else if (type === 'doughnut') {
                                ds.borderColor = isDarkMode() ? 'rgba(15, 12, 41, 0.8)' : '#fff';
                            }
                        }

                        // Aktualizuj legendę
                        if (chart.options.plugins && chart.options.plugins.legend && chart.options.plugins.legend.labels) {
                            chart.options.plugins.legend.labels.color = colors.textColor;
                        }

                        chart.update('none');
                    });
                }
            });
        });

        observer.observe(document.documentElement, { attributes: true });
    }

    // ========================================
    // Inicjalizacja
    // ========================================

    document.addEventListener('DOMContentLoaded', function () {
        initTabs();
        initThemeObserver();
    });

})();
