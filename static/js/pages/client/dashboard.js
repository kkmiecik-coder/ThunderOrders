document.addEventListener('DOMContentLoaded', function() {
    const isDarkMode = document.documentElement.getAttribute('data-theme') === 'dark';
    const textColor = isDarkMode ? 'rgba(255, 255, 255, 0.8)' : '#424242';
    const gridColor = isDarkMode ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)';

    // Orders Chart — odporne ładowanie Chart.js. Na mobilnym Safari 205 KB
    // vendora bywa nieukończone/zablokowane → `Chart` jest undefined i `new Chart`
    // rzucał ReferenceError, ubijając CAŁĄ resztę tego handlera DOMContentLoaded.
    // Teraz inicjalizacja wykresu jest NIEBLOKUJĄCA, a brak biblioteki jest obsłużony.
    function ensureChartJs() {
        return new Promise(function(resolve, reject) {
            if (typeof window.Chart !== 'undefined') { resolve(); return; }
            if (window.__chartJsFailed) {
                console.warn('Vendor Chart.js nie wczytał się (onerror) — ponawiam pobranie…');
            }

            // Ścieżkę bierzemy z istniejącego tagu vendora (zachowuje cache-busting),
            // z fallbackiem na znaną lokalizację.
            const existing = document.querySelector('script[src*="chart.umd"]');
            const baseSrc = existing ? existing.getAttribute('src')
                                     : '/static/js/vendor/chart.umd.min.js';
            let attempts = 0;

            (function tryLoad() {
                attempts++;
                const s = document.createElement('script');
                // Przy ponowieniu dokładamy cache-buster, by ominąć uszkodzony wpis w cache.
                s.src = attempts > 1
                    ? baseSrc + (baseSrc.indexOf('?') === -1 ? '?' : '&') + 'retry=' + attempts
                    : baseSrc;
                s.onload = function() {
                    if (typeof window.Chart !== 'undefined') resolve();
                    else if (attempts < 2) tryLoad();
                    else reject(new Error('Chart.js wczytany, ale obiekt Chart niedostępny'));
                };
                s.onerror = function() {
                    if (attempts < 2) tryLoad();
                    else reject(new Error('Nie udało się wczytać Chart.js'));
                };
                document.head.appendChild(s);
            })();
        });
    }

    const ordersCtx = document.getElementById('ordersChart');
    if (ordersCtx) {
        ensureChartJs()
            .then(function() { initOrdersChart(ordersCtx); })
            .catch(function(err) {
                console.error('Wykres zamówień niedostępny:', err);
                // Graceful fallback — komunikat zamiast pustego canvasu (opacity +
                // currentColor adaptują się do light/dark mode bez nowego CSS).
                const container = ordersCtx.closest('.chart-container');
                if (container) {
                    container.innerHTML = '<p style="text-align:center;padding:24px 16px;'
                        + 'font-size:13px;opacity:0.6;">Nie udało się załadować wykresu. '
                        + 'Odśwież stronę, aby spróbować ponownie.</p>';
                }
            });
    }

    // Buduje wykres zamówień — wołane dopiero gdy Chart.js jest dostępny.
    function initOrdersChart(ordersCtx) {
        const isMobile = window.innerWidth <= 768;
        let chartLabels = [];
        let chartValues = [];
        try {
            chartLabels = JSON.parse(ordersCtx.dataset.labels || '[]');
            chartValues = JSON.parse(ordersCtx.dataset.values || '[]');
        } catch (e) {
            console.error('Nieprawidłowe dane wykresu:', e);
        }

        const ordersChart = new Chart(ordersCtx.getContext('2d'), {
            type: 'line',
            data: {
                labels: chartLabels,
                datasets: [{
                    label: 'Liczba zamówień',
                    data: chartValues,
                    backgroundColor: 'rgba(255, 133, 0, 0.2)',
                    borderColor: '#FF8500',
                    borderWidth: isMobile ? 1.5 : 2,
                    fill: true,
                    tension: 0.4,
                    pointBackgroundColor: '#FF8500',
                    pointBorderColor: '#fff',
                    pointHoverRadius: isMobile ? 4 : 6,
                    pointRadius: isMobile ? 2 : 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: isDarkMode ? 'rgba(0, 0, 0, 0.8)' : 'white',
                        titleColor: textColor,
                        bodyColor: textColor,
                        borderColor: gridColor,
                        borderWidth: 1,
                        padding: isMobile ? 8 : 12,
                        titleFont: { size: isMobile ? 11 : 13 },
                        bodyFont: { size: isMobile ? 11 : 13 },
                        displayColors: false,
                        callbacks: {
                            label: function(context) {
                                return 'Zamówienia: ' + context.parsed.y;
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            color: textColor,
                            stepSize: 1,
                            precision: 0,
                            font: { size: isMobile ? 10 : 12 }
                        },
                        grid: { color: gridColor }
                    },
                    x: {
                        ticks: {
                            color: textColor,
                            maxRotation: isMobile ? 60 : 45,
                            minRotation: isMobile ? 30 : 0,
                            font: { size: isMobile ? 9 : 12 },
                            maxTicksLimit: isMobile ? 8 : undefined
                        },
                        grid: { color: gridColor }
                    }
                }
            }
        });

        // Theme change listener
        document.addEventListener('themeChanged', function(e) {
            const newTheme = e.detail.theme;
            const newTextColor = newTheme === 'dark' ? 'rgba(255, 255, 255, 0.8)' : '#424242';
            const newGridColor = newTheme === 'dark' ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)';

            ordersChart.options.scales.y.ticks.color = newTextColor;
            ordersChart.options.scales.y.grid.color = newGridColor;
            ordersChart.options.scales.x.ticks.color = newTextColor;
            ordersChart.options.scales.x.grid.color = newGridColor;
            ordersChart.options.plugins.tooltip.backgroundColor = newTheme === 'dark' ? 'rgba(0, 0, 0, 0.8)' : 'white';
            ordersChart.options.plugins.tooltip.titleColor = newTextColor;
            ordersChart.options.plugins.tooltip.bodyColor = newTextColor;
            ordersChart.update();
        });

        // Period change listener
        const periodSelect = document.getElementById('chartPeriod');
        if (periodSelect) {
            periodSelect.addEventListener('change', async function() {
                const period = this.value;

                try {
                    const response = await fetch(`/client/api/chart-data?period=${period}`);
                    const data = await response.json();

                    // Update chart data
                    ordersChart.data.labels = data.labels;
                    ordersChart.data.datasets[0].data = data.values;
                    ordersChart.update();
                } catch (error) {
                    console.error('Error fetching chart data:', error);
                }
            });
        }
    }

    // ====================================
    // EXCLUSIVE PAGES - DYNAMIC TIMING
    // ====================================
    let statusRefreshPending = false;

    function updateOfferTimings() {
        const timingElements = document.querySelectorAll('.offer-timing');
        const now = new Date();
        let needsStatusRefresh = false;

        timingElements.forEach(el => {
            const status = el.dataset.status;
            const startsAt = el.dataset.starts ? new Date(el.dataset.starts) : null;
            const endsAt = el.dataset.ends ? new Date(el.dataset.ends) : null;

            let text = '';

            if (status === 'scheduled' && startsAt) {
                const diffMs = startsAt - now;
                const diffHours = diffMs / (1000 * 60 * 60);

                if (diffHours > 24) {
                    text = `Start: ${formatDateTime(startsAt)}`;
                } else if (diffMs > 0) {
                    text = `Aktywna za ${formatCountdown(diffMs)}`;
                } else {
                    // Countdown finished — status should transition to active
                    text = 'Uruchamianie...';
                    needsStatusRefresh = true;
                }
            } else if (status === 'active') {
                if (endsAt) {
                    const diffMs = endsAt - now;
                    if (diffMs > 0) {
                        text = `Zamknięcie za ${formatCountdown(diffMs)}`;
                    } else {
                        // Countdown finished — status should transition to ended
                        text = 'Zamykanie...';
                        needsStatusRefresh = true;
                    }
                } else {
                    text = 'Bez daty zakończenia';
                }
            } else if (status === 'ended') {
                if (endsAt) {
                    text = `Zamknięto ${formatDateTime(endsAt)}`;
                } else {
                    text = 'Zakończona';
                }
            } else if (status === 'paused') {
                text = 'Sprzedaż wstrzymana';
            } else {
                text = '—';
            }

            el.textContent = text;
        });

        // If any countdown just expired, fetch fresh statuses from API (once)
        if (needsStatusRefresh && !statusRefreshPending) {
            statusRefreshPending = true;
            refreshOfferStatuses();
        }
    }

    async function refreshOfferStatuses() {
        try {
            const response = await fetch('/client/api/offer-pages?offset=0&limit=100');
            const data = await response.json();
            if (!data.success) return;

            const pageMap = {};
            data.pages.forEach(p => { pageMap[String(p.id)] = p; });

            // Update all visible cards (mobile)
            document.querySelectorAll('.offer-card').forEach(card => {
                // Find page id from matrix button or action link
                const matrixBtn = card.querySelector('.offer-matrix-btn');
                const actionLink = card.querySelector('.offer-action-btn');
                let pageId = matrixBtn ? matrixBtn.dataset.pageId : null;

                // Try to match by name if no matrix btn
                if (!pageId) {
                    const nameEl = card.querySelector('.offer-name');
                    if (nameEl) {
                        const page = data.pages.find(p => p.name === nameEl.textContent.trim());
                        if (page) pageId = page.id;
                    }
                }

                if (!pageId || !pageMap[pageId]) return;
                const page = pageMap[pageId];

                // Update status badge
                const badgesContainer = card.querySelector('.offer-card-badges') || card.querySelector('.offer-card-header');
                if (badgesContainer) {
                    const oldStatus = badgesContainer.querySelector('.offer-status');
                    if (oldStatus) {
                        const newStatus = document.createElement('span');
                        newStatus.className = `offer-status offer-status-${page.status_class}`;
                        if (page.is_live) {
                            newStatus.innerHTML = '<span class="live-dot"></span>LIVE';
                        } else {
                            newStatus.textContent = page.status_text;
                        }
                        oldStatus.replaceWith(newStatus);
                    }
                }

                // Update timing element data attributes
                const timingEl = card.querySelector('.offer-timing');
                if (timingEl) {
                    timingEl.dataset.status = page.status;
                    timingEl.dataset.starts = page.starts_at || '';
                    timingEl.dataset.ends = page.ends_at || '';
                    // Update important class
                    if (page.is_important) {
                        timingEl.classList.add('offer-timing-important');
                    } else {
                        timingEl.classList.remove('offer-timing-important');
                    }
                }
            });

            // Update all visible table rows (desktop)
            document.querySelectorAll('#offersTableBody tr').forEach(row => {
                const nameEl = row.querySelector('.offer-name');
                if (!nameEl) return;
                const page = data.pages.find(p => p.name === nameEl.textContent.trim());
                if (!page) return;

                // Update status badge in table
                const statusCell = row.querySelector('.offer-status');
                if (statusCell) {
                    const newStatus = document.createElement('span');
                    newStatus.className = `offer-status offer-status-${page.status_class}`;
                    if (page.is_live) {
                        newStatus.innerHTML = '<span class="live-dot"></span>LIVE';
                    } else {
                        newStatus.textContent = page.status_text;
                    }
                    statusCell.replaceWith(newStatus);
                }

                // Update timing element
                const timingEl = row.querySelector('.offer-timing');
                if (timingEl) {
                    timingEl.dataset.status = page.status;
                    timingEl.dataset.starts = page.starts_at || '';
                    timingEl.dataset.ends = page.ends_at || '';
                    if (page.is_important) {
                        timingEl.classList.add('offer-timing-important');
                    } else {
                        timingEl.classList.remove('offer-timing-important');
                    }
                }
            });

        } catch (err) {
            console.warn('Failed to refresh offer statuses:', err);
        } finally {
            statusRefreshPending = false;
            // Re-run timing update with fresh data
            updateOfferTimings();
        }
    }

    function formatDateTime(date) {
        const day = String(date.getDate()).padStart(2, '0');
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const year = date.getFullYear();
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${day}.${month}.${year} ${hours}:${minutes}`;
    }

    function formatCountdown(ms) {
        const totalSeconds = Math.floor(ms / 1000);
        const days = Math.floor(totalSeconds / 86400);
        const hours = Math.floor((totalSeconds % 86400) / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);

        if (days > 0) {
            return `${days}d ${hours}h`;
        } else if (hours > 0) {
            return `${hours}h ${minutes}m`;
        } else {
            return `${minutes}m`;
        }
    }

    // Initial update and refresh every minute
    updateOfferTimings();
    setInterval(updateOfferTimings, 60000);

    // ====================================
    // EXCLUSIVE PAGES - LAZY LOADING
    // ====================================
    (function() {
        const loadMoreBtn = document.getElementById('offersLoadMoreBtn');
        const tableBody = document.getElementById('offersTableBody');
        const cardsBody = document.getElementById('offersCardsBody');
        const showMoreContainer = document.getElementById('offersShowMore');

        // tableBody jest wymagane do działania przełącznika; loadMoreBtn może
        // nie istnieć (gdy domyślna zakładka jest pusta).
        if (!tableBody) return;

        const PAGE_SIZE = 5;
        let isLoading = false;
        let activeFilter = 'live';
        const tabCache = {
            live:     { pages: [], shownCount: 0, total: null, initialized: false },
            upcoming: { pages: [], shownCount: 0, total: null, initialized: false },
            closed:   { pages: [], shownCount: 0, total: null, initialized: false }
        };

        // Create table row HTML from page data
        function createTableRowHTML(page) {
            const statusHTML = getStatusHTML(page);
            const timingClass = page.status === 'active' || page.status === 'scheduled' ? ' offer-timing-important' : '';
            const isDisabled = page.status_class === 'closed';
            const buttonHTML = isDisabled
                ? `<a class="offer-action-btn" disabled aria-disabled="true">Otwórz →</a>`
                : `<a href="${page.page_url}" class="offer-action-btn" target="_blank">Otwórz →</a>`;

            const matrixBtnHTML = page.has_sets
                ? `<button type="button" class="offer-matrix-btn" data-page-id="${page.id}" title="Macierz setów">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M8.186 1.113a.5.5 0 0 0-.372 0L1.846 3.5 8 5.961 14.154 3.5 8.186 1.113zM15 4.239l-6.5 2.6v7.922l6.5-2.6V4.24zM7.5 14.762V6.838L1 4.239v7.923l6.5 2.6zM7.443.184a1.5 1.5 0 0 1 1.114 0l7.129 2.852A.5.5 0 0 1 16 3.5v8.662a1 1 0 0 1-.629.928l-7.185 2.874a.5.5 0 0 1-.372 0L.63 13.09a1 1 0 0 1-.63-.928V3.5a.5.5 0 0 1 .314-.464L7.443.184z"/>
                    </svg>
                </button>`
                : '';

            return `
                <tr>
                    <td><span class="offer-name">${page.name}</span></td>
                    <td><span class="offer-type-badge offer-type-${page.page_type || 'exclusive'}">${page.page_type === 'preorder' ? 'Pre-order' : 'Exclusive'}</span></td>
                    <td>${statusHTML}</td>
                    <td>
                        <span class="offer-timing${timingClass}"
                              data-status="${page.status}"
                              data-starts="${page.starts_at || ''}"
                              data-ends="${page.ends_at || ''}">
                        </span>
                    </td>
                    <td>
                        <div class="offer-card-actions">
                            ${matrixBtnHTML}
                            ${buttonHTML}
                        </div>
                    </td>
                </tr>
            `;
        }

        // Create card HTML from page data
        function createCardHTML(page) {
            const statusHTML = getStatusHTML(page);
            const timingClass = page.status === 'active' || page.status === 'scheduled' ? ' offer-timing-important' : '';
            const isDisabled = page.status_class === 'closed';
            const buttonHTML = isDisabled
                ? `<a class="offer-action-btn" disabled aria-disabled="true">Otwórz →</a>`
                : `<a href="${page.page_url}" class="offer-action-btn" target="_blank">Otwórz →</a>`;

            const matrixBtnHTML = page.has_sets
                ? `<button type="button" class="offer-matrix-btn" data-page-id="${page.id}" title="Macierz setów">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M8.186 1.113a.5.5 0 0 0-.372 0L1.846 3.5 8 5.961 14.154 3.5 8.186 1.113zM15 4.239l-6.5 2.6v7.922l6.5-2.6V4.24zM7.5 14.762V6.838L1 4.239v7.923l6.5 2.6zM7.443.184a1.5 1.5 0 0 1 1.114 0l7.129 2.852A.5.5 0 0 1 16 3.5v8.662a1 1 0 0 1-.629.928l-7.185 2.874a.5.5 0 0 1-.372 0L.63 13.09a1 1 0 0 1-.63-.928V3.5a.5.5 0 0 1 .314-.464L7.443.184z"/>
                    </svg>
                </button>`
                : '';

            const growButtonHTML = buttonHTML.replace('offer-action-btn"', 'offer-action-btn offer-action-btn-grow"');

            return `
                <div class="offer-card">
                    <div class="offer-card-name">
                        <span class="offer-name">${page.name}</span>
                    </div>
                    <div class="offer-card-badges">
                        <span class="offer-type-badge offer-type-${page.page_type || 'exclusive'}">${page.page_type === 'preorder' ? 'Pre-order' : 'Exclusive'}</span>
                        ${statusHTML}
                    </div>
                    <div class="offer-card-timing">
                        <span class="offer-timing${timingClass}"
                              data-status="${page.status}"
                              data-starts="${page.starts_at || ''}"
                              data-ends="${page.ends_at || ''}">
                        </span>
                    </div>
                    <div class="offer-card-footer">
                        <div class="offer-card-actions">
                            ${matrixBtnHTML}
                            ${growButtonHTML}
                        </div>
                    </div>
                </div>
            `;
        }

        // Get status badge HTML
        function getStatusHTML(page) {
            if (page.is_live) {
                return '<span class="offer-status offer-status-live"><span class="live-dot"></span>LIVE</span>';
            }
            return `<span class="offer-status offer-status-${page.status_class}">${page.status_text}</span>`;
        }

        // Pokazuje spinner i czyści dynamiczne wiersze/karty (przy pierwszym
        // pobraniu zakładki).
        function showLoading() {
            const loadingRow = tableBody.querySelector('.offer-loading-row');
            const loadingCard = cardsBody ? cardsBody.querySelector('.offer-card-loading') : null;
            const emptyRow = tableBody.querySelector('.offer-empty-row');
            const emptyCard = cardsBody ? cardsBody.querySelector('.offer-card-empty') : null;
            tableBody.querySelectorAll('tr').forEach(tr => {
                if (!tr.classList.contains('offer-empty-row') &&
                    !tr.classList.contains('offer-loading-row')) tr.remove();
            });
            if (cardsBody) cardsBody.querySelectorAll('.offer-card').forEach(c => c.remove());
            if (emptyRow) emptyRow.style.display = 'none';
            if (emptyCard) emptyCard.style.display = 'none';
            if (loadingRow) loadingRow.style.display = '';
            if (loadingCard) loadingCard.style.display = '';
            if (showMoreContainer) showMoreContainer.style.display = 'none';
        }

        // Czyści dynamiczne wiersze/karty (zostawia pusty stan) i renderuje
        // podany zbiór stron. Używane przy przełączaniu zakładek.
        function renderPages(pages) {
            const emptyRow = tableBody.querySelector('.offer-empty-row');
            const emptyCard = cardsBody ? cardsBody.querySelector('.offer-card-empty') : null;
            const loadingRow = tableBody.querySelector('.offer-loading-row');
            const loadingCard = cardsBody ? cardsBody.querySelector('.offer-card-loading') : null;
            if (loadingRow) loadingRow.style.display = 'none';
            if (loadingCard) loadingCard.style.display = 'none';

            // Usuń wszystkie wiersze oprócz pustego stanu i loadingu
            tableBody.querySelectorAll('tr').forEach(tr => {
                if (!tr.classList.contains('offer-empty-row') &&
                    !tr.classList.contains('offer-loading-row')) tr.remove();
            });
            if (cardsBody) {
                cardsBody.querySelectorAll('.offer-card').forEach(c => c.remove());
            }

            if (!pages || pages.length === 0) {
                const emptyTexts = {
                    live: 'Brak stron sprzedaży na żywo',
                    upcoming: 'Brak nadchodzących stron sprzedaży',
                    closed: 'Brak zamkniętych stron sprzedaży'
                };
                const emptyText = emptyTexts[activeFilter] || emptyTexts.live;
                if (emptyRow) {
                    emptyRow.style.display = '';
                    const cell = emptyRow.querySelector('.offer-empty-text');
                    if (cell) cell.textContent = emptyText;
                }
                if (emptyCard) {
                    emptyCard.style.display = '';
                    const span = emptyCard.querySelector('.offer-empty-text');
                    if (span) span.textContent = emptyText;
                }
                return;
            }
            if (emptyRow) emptyRow.style.display = 'none';
            if (emptyCard) emptyCard.style.display = 'none';

            pages.forEach(page => {
                const tpl = document.createElement('template');
                tpl.innerHTML = createTableRowHTML(page).trim();
                const newRow = tpl.content.firstElementChild;
                if (emptyRow) tableBody.insertBefore(newRow, emptyRow);
                else tableBody.appendChild(newRow);

                if (cardsBody) {
                    const tempDiv = document.createElement('div');
                    tempDiv.innerHTML = createCardHTML(page);
                    const newCard = tempDiv.firstElementChild;
                    if (emptyCard) cardsBody.insertBefore(newCard, emptyCard);
                    else cardsBody.appendChild(newCard);
                }
            });

            updateOfferTimings();
        }

        // Pokazuje/ukrywa i ustawia tekst "Pokaż więcej" wg stanu zakładki.
        function syncShowMore(total, shownCount) {
            if (!showMoreContainer || !loadMoreBtn) return;
            const remaining = Math.max(0, (total || 0) - shownCount);
            if (remaining <= 0) {
                showMoreContainer.style.display = 'none';
            } else {
                showMoreContainer.style.display = '';
                loadMoreBtn.disabled = false;
                loadMoreBtn.textContent = `Pokaż ${Math.min(remaining, PAGE_SIZE)} więcej →`;
            }
        }

        // Pobiera dane zakładki z API (z parametrem filter).
        async function fetchTabData(filter, offset, limit) {
            try {
                const response = await fetch(
                    `/client/api/offer-pages?filter=${filter}&offset=${offset}&limit=${limit}`
                );
                const data = await response.json();
                return data && data.success ? data : null;
            } catch (err) {
                console.error('Błąd pobierania stron zakładki:', err);
                window.showToast('Nie udało się załadować stron', 'error');
                return null;
            }
        }

        // Pobiera pierwsze PAGE_SIZE stron zakładki przy pierwszym wejściu.
        async function ensureTab(filter) {
            const cache = tabCache[filter];
            if (cache.initialized) return;
            showLoading();
            const data = await fetchTabData(filter, 0, PAGE_SIZE);
            if (activeFilter !== filter) return;       // stale guard
            cache.pages = data ? data.pages.slice() : [];
            cache.total = data ? data.total : cache.pages.length;
            cache.shownCount = cache.pages.length;
            cache.initialized = true;
        }

        // Renderuje aktualnie aktywną zakładkę z cache.
        function renderActive() {
            const cache = tabCache[activeFilter];
            renderPages(cache.pages.slice(0, cache.shownCount));
            syncShowMore(cache.total, cache.shownCount);
        }

        async function switchTab(filter) {
            if (filter === activeFilter) return;
            activeFilter = filter;
            document.querySelectorAll('.offer-filter-tab').forEach(btn => {
                const isActive = btn.dataset.filter === filter;
                btn.classList.toggle('active', isActive);
                btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
            });
            await ensureTab(filter);
            if (activeFilter !== filter) return;        // stale guard
            renderActive();
        }

        // "Pokaż więcej" — dociąga kolejne PAGE_SIZE stron aktywnej zakładki.
        async function loadMore() {
            if (isLoading) return;
            const cache = tabCache[activeFilter];
            const filterAtStart = activeFilter;

            // Jeśli mamy już więcej w cache niż pokazujemy — odsłoń bez fetcha.
            if (cache.pages.length > cache.shownCount) {
                cache.shownCount = Math.min(cache.shownCount + PAGE_SIZE, cache.pages.length);
                renderActive();
                return;
            }

            // Brak zapasu — dociągnij kolejne PAGE_SIZE z API.
            isLoading = true;
            if (loadMoreBtn) { loadMoreBtn.disabled = true; loadMoreBtn.textContent = 'Ładowanie…'; }
            const data = await fetchTabData(activeFilter, cache.pages.length, PAGE_SIZE);
            isLoading = false;
            if (activeFilter !== filterAtStart) return; // stale guard (user switched mid-fetch)
            if (data && data.pages.length) {
                cache.pages.push(...data.pages);
                cache.total = data.total;
                cache.shownCount = cache.pages.length;
            }
            renderActive();
        }

        if (loadMoreBtn) {
            loadMoreBtn.addEventListener('click', (e) => { e.preventDefault(); loadMore(); });
        }
        document.querySelectorAll('.offer-filter-tab').forEach(btn => {
            btn.addEventListener('click', () => switchTab(btn.dataset.filter));
        });

        // Start: pobierz i renderuj domyślną zakładkę (live) z loading state.
        ensureTab('live').then(() => { if (activeFilter === 'live') renderActive(); });
    })();

    // ====================================
    // SET MATRIX MODAL
    // ====================================
    (function() {
        const modal = document.getElementById('setMatrixModal');
        const modalTitle = document.getElementById('matrixModalTitle');
        const modalBody = document.getElementById('matrixModalBody');
        const modalClose = document.getElementById('matrixModalClose');

        if (!modal) return;

        // Open modal on button click (event delegation for dynamic buttons)
        document.addEventListener('click', function(e) {
            const btn = e.target.closest('.offer-matrix-btn');
            if (!btn) return;

            const pageId = btn.dataset.pageId;
            openMatrixModal(pageId);
        });

        // Close modal
        modalClose.addEventListener('click', closeMatrixModal);
        modal.addEventListener('click', function(e) {
            if (e.target === modal) closeMatrixModal();
        });
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && modal.classList.contains('active')) closeMatrixModal();
        });

        function openMatrixModal(pageId) {
            modal.classList.add('active');
            modalBody.innerHTML = '<div class="matrix-loading"><div class="spinner"></div><span>Ładowanie macierzy...</span></div>';

            fetch(`/client/api/offers/${pageId}/matrix`)
                .then(r => r.json())
                .then(data => {
                    if (!data.success) {
                        modalBody.innerHTML = '<div class="matrix-error">Nie udało się załadować danych</div>';
                        return;
                    }
                    modalTitle.textContent = `Macierz setów — ${data.page_name}`;
                    renderMatrix(data.sets);
                })
                .catch(() => {
                    modalBody.innerHTML = '<div class="matrix-error">Błąd połączenia z serwerem</div>';
                });
        }

        function closeMatrixModal() {
            modal.classList.remove('active');
        }

        function renderMatrix(sets) {
            if (!sets || sets.length === 0) {
                modalBody.innerHTML = '<div class="matrix-empty">Brak setów na tej stronie</div>';
                return;
            }

            let html = '<div class="sets-matrix-grid">';
            sets.forEach(set => {
                html += renderSetCard(set);
            });
            html += '</div>';
            modalBody.innerHTML = html;
        }

        function renderSetCard(set) {
            const products = set.products.filter(p => !p.is_full_set);
            const fullSetProduct = set.products.find(p => p.is_full_set);

            let html = '<div class="set-matrix-card">';

            // Header
            html += '<div class="set-matrix-header">';
            html += '<div class="set-header-left">';
            if (set.set_image) {
                html += `<img src="${set.set_image}" alt="${set.set_name}" class="set-image">`;
            }
            html += '<div class="set-info">';
            html += `<h3 class="set-name">${set.set_name}</h3>`;
            if (set.has_limit) {
                html += `<span class="set-count">${set.ordered_sets} / ${set.set_max_sets} kompletnych setów</span>`;
            } else {
                html += `<span class="set-count">${set.ordered_sets} kompletnych setów (bez limitu)</span>`;
            }
            html += '</div></div>';
            html += '<div class="set-header-legend">';
            html += '<span class="legend-label">Legenda:</span>';
            html += '<div class="legend-items">';
            html += '<div class="legend-item"><svg class="slot-check" width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/></svg><span>Zakupione</span></div>';
            html += '<div class="legend-item"><svg class="slot-check-own" width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/></svg><span>Twój zakup</span></div>';
            if (set.has_limit) {
                html += '<div class="legend-item"><svg class="slot-lock" width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1a2 2 0 0 1 2 2v4H6V3a2 2 0 0 1 2-2zm3 6V3a3 3 0 0 0-6 0v4a2 2 0 0 0-2 2v5a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2z"/></svg><span>Zablokowany</span></div>';
            }
            html += '</div></div>';
            html += '</div>';

            // Table
            if (products.length > 0) {
                html += '<div class="set-matrix-table-wrap"><table class="set-matrix-table"><thead><tr>';
                html += '<th class="matrix-product-col">Produkt</th>';
                for (let i = 0; i < set.set_max_sets; i++) {
                    html += `<th class="matrix-slot-col text-center">Set ${i + 1}</th>`;
                }
                if (set.has_limit) {
                    html += `<th class="matrix-slot-col matrix-locked-col text-center">Set ${set.set_max_sets + 1}</th>`;
                }
                html += '</tr></thead><tbody>';

                products.forEach(product => {
                    html += '<tr>';
                    html += `<td class="matrix-product-col"><span>${product.product_name}</span></td>`;
                    for (let idx = 0; idx < set.set_max_sets; idx++) {
                        html += '<td class="matrix-slot-col text-center">';
                        const slot = product.slots[idx];
                        if (slot && slot.filled) {
                            if (slot.is_own) {
                                html += `<span class="slot-check-own-wrap" data-tooltip="${slot.customer}">`;
                                html += '<svg class="slot-check-own" width="18" height="18" viewBox="0 0 16 16" fill="currentColor"><path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/></svg>';
                                html += '</span>';
                            } else {
                                html += '<svg class="slot-check" width="18" height="18" viewBox="0 0 16 16" fill="currentColor"><path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/></svg>';
                            }
                        }
                        html += '</td>';
                    }
                    if (set.has_limit) {
                        html += '<td class="matrix-slot-col matrix-locked-col text-center">';
                        html += '<svg class="slot-lock" width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1a2 2 0 0 1 2 2v4H6V3a2 2 0 0 1 2-2zm3 6V3a3 3 0 0 0-6 0v4a2 2 0 0 0-2 2v5a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2z"/></svg>';
                        html += '</td>';
                    }
                    html += '</tr>';
                });

                html += '</tbody></table></div>';

            }

            // Licznik produktów-kompletów kupionych przez zalogowanego użytkownika.
            // Pokazujemy zawsze gdy sekcja ma produkt-komplet — nawet z wartością 0.
            if (fullSetProduct) {
                const ownFullSets = set.own_full_sets || 0;
                html += '<div class="set-matrix-own-footer">';
                html += '<svg class="own-footer-icon" width="18" height="18" viewBox="0 0 16 16" fill="currentColor"><path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/></svg>';
                html += `<span class="own-footer-text">Kupione pełne sety przez Ciebie: <strong>${ownFullSets}</strong></span>`;
                html += '</div>';
            }

            html += '</div>';
            return html;
        }
    })();

    // ====================================
    // RECENT ORDERS - LAZY LOADING
    // ====================================
    (function() {
        const loadMoreBtn = document.getElementById('ordersLoadMoreBtn');
        const tableBody = document.getElementById('recentOrdersTableBody');
        const cardsBody = document.getElementById('recentOrdersCardsBody');
        const showMoreContainer = document.getElementById('ordersShowMore');

        if (!loadMoreBtn || !tableBody) return;

        let currentOffset = parseInt(loadMoreBtn.dataset.visible) + parseInt(loadMoreBtn.dataset.buffer);
        let isLoading = false;

        // Create table row HTML from order data
        function createRowHTML(order) {
            return `
                <tr onclick="window.location.href='${order.detail_url}'" style="cursor: pointer;">
                    <td>
                        <span class="order-number-link">${order.order_number}</span>
                    </td>
                    <td>
                        <span class="order-client">${order.customer_name}</span>
                    </td>
                    <td>
                        <span class="order-status" style="background-color: ${order.status_badge_color}; color: white;">
                            ${order.status_display_name}
                        </span>
                    </td>
                    <td class="text-right">
                        <span class="order-amount">${order.effective_grand_total.toFixed(2)} PLN</span>
                    </td>
                </tr>
            `;
        }

        // Create mobile card HTML from order data
        function createCardHTML(order) {
            return `
                <a href="${order.detail_url}" class="recent-order-card">
                    <div class="recent-order-card-top">
                        <span class="order-number-link">${order.order_number}</span>
                        <span class="order-status" style="background-color: ${order.status_badge_color}; color: white;">
                            ${order.status_display_name}
                        </span>
                    </div>
                    <div class="recent-order-card-bottom">
                        <span class="order-client">${order.customer_name}</span>
                        <span class="order-amount">${order.effective_grand_total.toFixed(2)} PLN</span>
                    </div>
                </a>
            `;
        }

        // Fetch more orders from API
        async function fetchMoreOrders(offset, limit = 5) {
            try {
                const response = await fetch(`/client/api/recent-orders?offset=${offset}&limit=${limit}`);
                const data = await response.json();
                return data;
            } catch (error) {
                console.error('Error fetching recent orders:', error);
                return null;
            }
        }

        // Update button text
        function updateButtonText(remaining) {
            if (remaining <= 0) {
                showMoreContainer.style.display = 'none';
            } else {
                loadMoreBtn.textContent = `Pokaż ${Math.min(remaining, 5)} więcej →`;
                loadMoreBtn.dataset.remaining = remaining;
            }
        }

        // Handle load more click
        loadMoreBtn.addEventListener('click', async function(e) {
            e.preventDefault();

            if (isLoading) return;

            // 1. Show buffered items first (both table rows and cards)
            const bufferedRows = tableBody.querySelectorAll('.orders-buffered');
            const bufferedCards = cardsBody ? cardsBody.querySelectorAll('.orders-buffered') : [];
            let shownFromBuffer = 0;

            bufferedRows.forEach((row, index) => {
                if (index < 5 && row.style.display === 'none') {
                    row.style.display = '';
                    row.classList.remove('orders-buffered');
                    shownFromBuffer++;
                }
            });

            bufferedCards.forEach((card, index) => {
                if (index < 5 && card.style.display === 'none') {
                    card.style.display = '';
                    card.classList.remove('orders-buffered');
                }
            });

            // Calculate new remaining
            let remaining = parseInt(loadMoreBtn.dataset.remaining) - shownFromBuffer;

            // 2. If we showed buffered rows, fetch more for the buffer in background
            if (shownFromBuffer > 0 && remaining > 0) {
                isLoading = true;
                loadMoreBtn.textContent = 'Ładowanie...';

                const data = await fetchMoreOrders(currentOffset, 5);

                if (data && data.success && data.orders.length > 0) {
                    // Add new rows as buffered (hidden)
                    data.orders.forEach(order => {
                        // Table row
                        const rowHTML = createRowHTML(order);
                        const tempTable = document.createElement('table');
                        tempTable.innerHTML = `<tbody>${rowHTML}</tbody>`;
                        const newRow = tempTable.querySelector('tr');
                        newRow.classList.add('orders-buffered');
                        newRow.style.display = 'none';
                        tableBody.appendChild(newRow);

                        // Mobile card
                        if (cardsBody) {
                            const cardHTML = createCardHTML(order);
                            const tempDiv = document.createElement('div');
                            tempDiv.innerHTML = cardHTML;
                            const newCard = tempDiv.firstElementChild;
                            newCard.classList.add('orders-buffered');
                            newCard.style.display = 'none';
                            cardsBody.appendChild(newCard);
                        }
                    });

                    currentOffset += data.orders.length;
                }

                isLoading = false;
            }

            // Recalculate remaining based on actual visible rows
            const visibleRows = tableBody.querySelectorAll('tr:not([style*="display: none"])').length;
            const total = parseInt(loadMoreBtn.dataset.total);
            remaining = Math.max(0, total - visibleRows);

            updateButtonText(remaining);
        });
    })();

    // ====================================
    // ACHIEVEMENTS WIDGET
    // ====================================
    (function() {
        fetch('/achievements/api/my', {
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.success) return;
            var unlocked = data.achievements.filter(function(a) { return a.unlocked; });
            var recent = unlocked.slice(-5).reverse();
            var badgesEl = document.getElementById('widget-badges');
            var galleryUrl = badgesEl ? (badgesEl.dataset.galleryUrl || '#') : '#';

            if (recent.length === 0) {
                badgesEl.innerHTML = '<div style="font-size:12px;opacity:0.5;">Brak zdobytych odznak</div>';
            } else {
                var badgesHtml = recent.map(function(a) {
                    var icon = a.has_icon
                        ? '<img src="/static/uploads/achievements/' + a.slug + '@256.png" style="width:36px;height:36px;object-fit:contain;">'
                        : '&#127942;';
                    return '<div class="widget-badge">'
                        + '<div class="widget-badge-icon badge-icon ' + a.rarity + '">' + icon + '</div>'
                        + '<div class="widget-badge-name">' + a.name + '</div>'
                        + '</div>';
                }).join('');
                if (unlocked.length > 5) {
                    badgesHtml += '<a href="' + galleryUrl + '" class="widget-badge widget-badge-more">'
                        + '<div class="widget-badge-icon">+' + (unlocked.length - 5) + '</div>'
                        + '<div class="widget-badge-name">więcej</div>'
                        + '</a>';
                }
                badgesEl.innerHTML = badgesHtml;
            }

        })
        .catch(function() {});
    })();
});
