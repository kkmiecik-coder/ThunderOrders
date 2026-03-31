/**
 * QR Tracking - Admin Pages
 * Charts (Chart.js), AJAX interactions, campaign management
 */

(function () {
    'use strict';

    // ========================================
    // State
    // ========================================

    var charts = {};
    var currentVisitsPage = 1;

    // ========================================
    // Helpers
    // ========================================

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

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

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
            lineColorSecondary: dark ? '#4facfe' : '#4facfe',
            lineBgColor: dark ? 'rgba(240, 147, 251, 0.15)' : 'rgba(131, 56, 236, 0.1)',
            lineBgColorSecondary: dark ? 'rgba(79, 172, 254, 0.1)' : 'rgba(79, 172, 254, 0.08)',
            barColor: dark ? 'rgba(240, 147, 251, 0.7)' : 'rgba(131, 56, 236, 0.7)',
            barBorderColor: dark ? '#f093fb' : '#5A189A',
            pointBorderColor: dark ? 'rgba(15, 12, 41, 0.9)' : '#fff',
            doughnutBorder: dark ? 'rgba(15, 12, 41, 0.8)' : '#fff',
            pieColors: dark
                ? ['#f093fb', '#4facfe', '#ff6b6b', '#51cf66', '#ffd43b', '#845ef7', '#ff922b', '#20c997', '#339af0', '#e64980']
                : ['#8338EC', '#4facfe', '#f5576c', '#2ecc71', '#f1c40f', '#764ba2', '#e67e22', '#1abc9c', '#3498db', '#e74c6c']
        };
    }

    // ========================================
    // Auto-slug from campaign name
    // ========================================

    window.autoSlug = function (name) {
        var polishChars = {
            'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n',
            'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
            'Ą': 'A', 'Ć': 'C', 'Ę': 'E', 'Ł': 'L', 'Ń': 'N',
            'Ó': 'O', 'Ś': 'S', 'Ź': 'Z', 'Ż': 'Z'
        };

        var slug = name;
        Object.keys(polishChars).forEach(function (pl) {
            slug = slug.split(pl).join(polishChars[pl]);
        });

        slug = slug.toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '');

        var slugInput = document.getElementById('slug');
        if (slugInput) {
            slugInput.value = slug;
        }
    };

    // ========================================
    // Toggle campaign active/inactive (AJAX)
    // ========================================

    window.toggleCampaign = function (id, checkbox) {
        fetch('/admin/qr-tracking/' + id + '/toggle', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            }
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.success) {
                if (window.Toast) {
                    window.Toast.show(data.message, 'success');
                }
            } else {
                checkbox.checked = !checkbox.checked;
                if (window.Toast) {
                    window.Toast.show(data.error || 'Wystąpił błąd', 'error');
                }
            }
        })
        .catch(function () {
            checkbox.checked = !checkbox.checked;
            if (window.Toast) {
                window.Toast.show('Błąd połączenia z serwerem', 'error');
            }
        });
    };

    // ========================================
    // Delete campaign (with confirmation)
    // ========================================

    // ========================================
    // Reset visits (with confirmation, AJAX)
    // ========================================

    window.resetVisits = function (id, name, count) {
        if (count === 0) {
            if (window.Toast) {
                window.Toast.show('Kampania "' + name + '" nie ma żadnych wizyt.', 'info');
            }
            return;
        }

        if (!confirm('Czy na pewno chcesz usunąć wszystkie wizyty (' + count + ') kampanii "' + name + '"?\nTa operacja jest nieodwracalna.')) {
            return;
        }

        fetch('/admin/qr-tracking/' + id + '/reset-visits', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            }
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.success) {
                if (window.Toast) {
                    window.Toast.show(data.message, 'success');
                }
                // Reload page to update visit counts
                setTimeout(function () { location.reload(); }, 800);
            } else {
                if (window.Toast) {
                    window.Toast.show(data.error || 'Wystąpił błąd', 'error');
                }
            }
        })
        .catch(function () {
            if (window.Toast) {
                window.Toast.show('Błąd połączenia z serwerem', 'error');
            }
        });
    };

    // ========================================
    // Delete campaign (with confirmation)
    // ========================================

    window.deleteCampaign = function (id, name) {
        if (!confirm('Czy na pewno chcesz usunąć kampanię "' + name + '"?\nTa operacja jest nieodwracalna.')) {
            return;
        }

        var form = document.getElementById('delete-form');
        if (form) {
            form.action = '/admin/qr-tracking/' + id + '/delete';
            form.submit();
        }
    };

    // ========================================
    // Load stats (detail page)
    // ========================================

    function loadStats() {
        var campaignIdInput = document.getElementById('campaign-id');
        if (!campaignIdInput) return;

        var campaignId = campaignIdInput.value;

        // Read filter values
        var dateFrom = '';
        var dateTo = '';
        var granularity = 'daily';

        var dateFromEl = document.getElementById('filter-date-from');
        var dateToEl = document.getElementById('filter-date-to');
        var granularityEl = document.getElementById('filter-granularity');

        if (dateFromEl) dateFrom = dateFromEl.value;
        if (dateToEl) dateTo = dateToEl.value;
        if (granularityEl) granularity = granularityEl.value;

        // Build query string
        var params = [];
        if (dateFrom) params.push('date_from=' + encodeURIComponent(dateFrom));
        if (dateTo) params.push('date_to=' + encodeURIComponent(dateTo));
        if (granularity) params.push('granularity=' + encodeURIComponent(granularity));
        var queryString = params.length > 0 ? '?' + params.join('&') : '';

        fetch('/admin/qr-tracking/' + campaignId + '/api/stats' + queryString)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.success) {
                    updateSummaryCards(data);
                    renderTimelineChart(data.timeline);
                    renderDoughnutChart('chart-devices', 'devices', data.devices);
                    renderDoughnutChart('chart-browsers', 'browsers', data.browsers);
                    renderBarChart(data.countries);
                    loadRecentVisits(campaignId);
                }
            })
            .catch(function (err) {
                console.error('QR Tracking stats error:', err);
            });
    }

    // Expose for filter button
    window.loadStats = loadStats;

    // ========================================
    // Update summary cards
    // ========================================

    function updateSummaryCards(data) {
        var totalEl = document.getElementById('stat-total');
        var uniqueEl = document.getElementById('stat-unique');
        var todayEl = document.getElementById('stat-today');
        var weekEl = document.getElementById('stat-week');

        if (totalEl) totalEl.textContent = data.total_visits || 0;
        if (uniqueEl) uniqueEl.textContent = data.unique_visits || 0;

        // Calculate today and this week from timeline
        var today = new Date().toISOString().split('T')[0];
        var todayCount = 0;
        var weekCount = 0;
        var now = new Date();
        var weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
        var weekAgoStr = weekAgo.toISOString().split('T')[0];

        if (data.timeline) {
            data.timeline.forEach(function (entry) {
                if (entry.date === today) {
                    todayCount = entry.total;
                }
                if (entry.date >= weekAgoStr) {
                    weekCount += entry.total;
                }
            });
        }

        if (todayEl) todayEl.textContent = todayCount;
        if (weekEl) weekEl.textContent = weekCount;
    }

    // ========================================
    // Chart: Timeline (line chart)
    // ========================================

    function renderTimelineChart(timelineData) {
        destroyChart('chart-timeline');
        var canvas = document.getElementById('chart-timeline');
        if (!canvas || typeof Chart === 'undefined') return;
        if (!timelineData || timelineData.length === 0) return;

        var colors = getChartColors();
        var ctx = canvas.getContext('2d');

        var totalValues = timelineData.map(function (d) { return d.total; });
        var uniqueValues = timelineData.map(function (d) { return d.unique; });

        // Determine granularity for scroll width
        var granularityEl = document.getElementById('filter-granularity');
        var granularity = granularityEl ? granularityEl.value : 'daily';

        // Format labels based on granularity
        var labels;
        if (granularity === 'hourly') {
            // Check if all entries are from the same day
            var dates = {};
            timelineData.forEach(function (d) {
                var day = d.date.substring(0, 10);
                dates[day] = true;
            });
            var dayCount = Object.keys(dates).length;
            if (dayCount === 1) {
                // Single day - show only hours
                labels = timelineData.map(function (d) { return d.date.substring(11); });
            } else {
                // Multiple days - show short date + hour
                labels = timelineData.map(function (d) {
                    return d.date.substring(5, 10) + ' ' + d.date.substring(11);
                });
            }
        } else {
            labels = timelineData.map(function (d) { return d.date; });
        }

        var scrollInner = document.getElementById('timeline-scroll-inner');
        var scrollWrapper = document.getElementById('timeline-scroll-wrapper');

        // Calculate minimum width: more data points = wider chart for hourly
        var minPointWidth = granularity === 'hourly' ? 40 : 50;
        var needsScroll = labels.length > 20 && (granularity === 'hourly' || granularity === 'daily');
        var calculatedWidth = labels.length * minPointWidth;
        var wrapperWidth = scrollWrapper ? scrollWrapper.clientWidth : 800;

        if (scrollInner) {
            if (needsScroll && calculatedWidth > wrapperWidth) {
                scrollInner.style.width = calculatedWidth + 'px';
                canvas.style.width = calculatedWidth + 'px';
                canvas.width = calculatedWidth;
            } else {
                scrollInner.style.width = '100%';
                canvas.style.width = '100%';
            }
        }

        var useResponsive = !(needsScroll && calculatedWidth > wrapperWidth);

        charts['chart-timeline'] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Wszystkie',
                        data: totalValues,
                        borderColor: colors.lineColor,
                        backgroundColor: colors.lineBgColor,
                        borderWidth: 2.5,
                        fill: true,
                        tension: 0.4,
                        pointRadius: labels.length > 60 ? 0 : 4,
                        pointHoverRadius: 6,
                        pointBackgroundColor: colors.lineColor,
                        pointBorderColor: colors.pointBorderColor,
                        pointBorderWidth: 2
                    },
                    {
                        label: 'Unikalne',
                        data: uniqueValues,
                        borderColor: colors.lineColorSecondary,
                        backgroundColor: colors.lineBgColorSecondary,
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4,
                        pointRadius: labels.length > 60 ? 0 : 3,
                        pointHoverRadius: 5,
                        pointBackgroundColor: colors.lineColorSecondary,
                        pointBorderColor: colors.pointBorderColor,
                        pointBorderWidth: 2,
                        borderDash: [5, 3]
                    }
                ]
            },
            options: {
                responsive: useResponsive,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            color: colors.textColor,
                            usePointStyle: true,
                            padding: 16,
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
                            maxTicksLimit: needsScroll ? labels.length : 15,
                            maxRotation: granularity === 'hourly' ? 90 : 45,
                            font: { size: granularity === 'hourly' ? 10 : 12 }
                        },
                        grid: { display: false }
                    }
                }
            }
        });
    }

    // ========================================
    // Chart: Doughnut (devices / browsers)
    // ========================================

    function renderDoughnutChart(canvasId, chartKey, items) {
        destroyChart(canvasId);
        var canvas = document.getElementById(canvasId);
        if (!canvas || typeof Chart === 'undefined') return;
        if (!items || items.length === 0) {
            var container = canvas.parentElement;
            if (container) {
                container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-tertiary);font-size:var(--text-sm);">Brak danych</div>';
            }
            return;
        }

        var colors = getChartColors();
        var ctx = canvas.getContext('2d');

        var labels = items.map(function (d) { return d.name; });
        var values = items.map(function (d) { return d.count; });

        charts[canvasId] = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: colors.pieColors.slice(0, labels.length),
                    borderWidth: 2,
                    borderColor: colors.doughnutBorder
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
    // Chart: Bar (countries - horizontal)
    // ========================================

    function renderBarChart(countriesData) {
        destroyChart('chart-countries');
        var canvas = document.getElementById('chart-countries');
        if (!canvas || typeof Chart === 'undefined') return;
        if (!countriesData || countriesData.length === 0) {
            var container = canvas.parentElement;
            if (container) {
                container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-tertiary);font-size:var(--text-sm);">Brak danych</div>';
            }
            return;
        }

        var colors = getChartColors();
        var ctx = canvas.getContext('2d');

        // Limit to top 10
        var top = countriesData.slice(0, 10);
        var labels = top.map(function (d) { return d.name; });
        var values = top.map(function (d) { return d.count; });

        charts['chart-countries'] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Wizyty',
                    data: values,
                    backgroundColor: colors.pieColors.slice(0, labels.length),
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
                        cornerRadius: 8
                    }
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        ticks: { color: colors.textColor, stepSize: 1 },
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

    // ========================================
    // Chart helpers
    // ========================================

    function destroyChart(chartId) {
        if (charts[chartId]) {
            charts[chartId].destroy();
            delete charts[chartId];
        }
    }

    // ========================================
    // Recent visits table
    // ========================================

    function loadRecentVisits(campaignId, page) {
        page = page || 1;
        currentVisitsPage = page;

        fetch('/admin/qr-tracking/' + campaignId + '/api/visits?page=' + page)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.success) {
                    renderVisitsTable(data);
                    renderVisitsPagination(campaignId, data);
                }
            })
            .catch(function (err) {
                console.error('QR Tracking visits error:', err);
            });
    }

    // Expose for pagination buttons
    window.loadRecentVisits = loadRecentVisits;

    function renderVisitsTable(data) {
        var tbody = document.getElementById('visits-tbody');
        if (!tbody) return;

        if (!data.visits || data.visits.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:40px; color:var(--text-tertiary);">Brak wizyt</td></tr>';
            return;
        }

        var html = '';
        data.visits.forEach(function (v) {
            html += '<tr>';
            html += '<td>' + escapeHtml(v.visited_at || '-') + '</td>';
            html += '<td>' + escapeHtml(v.device_type || '-') + '</td>';
            html += '<td class="qrt-hide-mobile">' + escapeHtml(v.browser || '-') + '</td>';
            html += '<td class="qrt-hide-mobile">' + escapeHtml(v.os || '-') + '</td>';
            html += '<td>' + escapeHtml(v.country || '-');
            if (v.city) html += ', ' + escapeHtml(v.city);
            html += '</td>';
            html += '<td class="qrt-hide-mobile">' + escapeHtml(v.ip_address || '-') + '</td>';
            html += '<td>';
            if (v.is_unique) {
                html += '<span class="qrt-badge qrt-badge-unique">Unikalna</span>';
            }
            html += '</td>';
            html += '</tr>';
        });

        tbody.innerHTML = html;
    }

    function renderVisitsPagination(campaignId, data) {
        var container = document.getElementById('visits-pagination');
        if (!container) return;

        if (data.pages <= 1) {
            container.innerHTML = '';
            return;
        }

        var html = '';
        html += '<button class="btn-page" onclick="loadRecentVisits(' + campaignId + ', ' + (data.page - 1) + ')" ' + (data.has_prev ? '' : 'disabled') + '>&laquo; Poprzednia</button>';
        html += '<span class="page-info">Strona ' + data.page + ' z ' + data.pages + ' (' + data.total + ' wizyt)</span>';
        html += '<button class="btn-page" onclick="loadRecentVisits(' + campaignId + ', ' + (data.page + 1) + ')" ' + (data.has_next ? '' : 'disabled') + '>Nastepna &raquo;</button>';

        container.innerHTML = html;
    }

    // ========================================
    // MutationObserver: dark mode switching
    // ========================================

    function initThemeObserver() {
        var observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                if (mutation.attributeName === 'data-theme') {
                    // Re-render all charts with new colors
                    var campaignIdInput = document.getElementById('campaign-id');
                    if (campaignIdInput) {
                        loadStats();
                    }
                }
            });
        });

        observer.observe(document.documentElement, { attributes: true });
    }

    // ========================================
    // Init on DOMContentLoaded
    // ========================================

    document.addEventListener('DOMContentLoaded', function () {
        // Detail page: load stats if campaign-id present
        var campaignIdInput = document.getElementById('campaign-id');
        if (campaignIdInput) {
            loadStats();

            // Auto-refresh on filter change
            var filterIds = ['filter-date-from', 'filter-date-to', 'filter-granularity'];
            filterIds.forEach(function (id) {
                var el = document.getElementById(id);
                if (el) {
                    el.addEventListener('change', loadStats);
                }
            });
        }

        // Init theme observer for chart color switching
        initThemeObserver();
    });

})();
