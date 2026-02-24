/**
 * Global Search Component
 * Dropdown search under topbar with role-based results and keyboard navigation
 */

(function() {
  'use strict';

  // ==========================================
  // SVG Icons (inline to avoid extra requests)
  // ==========================================
  const ICONS = {
    order: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 4h12M2 4v9a1 1 0 001 1h10a1 1 0 001-1V4M6 4V2h4v2M6 7h4"/></svg>',
    product: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2" width="12" height="12" rx="1"/><path d="M2 6h12M6 6v8"/></svg>',
    client: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="5" r="3"/><path d="M2 14c0-2.5 2.7-4.5 6-4.5s6 2 6 4.5"/></svg>',
    exclusive: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 1l2.1 4.3 4.7.7-3.4 3.3.8 4.7L8 11.8 3.8 14l.8-4.7L1.2 6l4.7-.7z"/></svg>',
    proxy: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M1 8h14M1 4h14M1 12h14"/><circle cx="12" cy="8" r="2"/></svg>',
    shipping: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M1 3h9v7H1zM10 6h3l2 3v3h-5"/><circle cx="4" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/></svg>',
    nav: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M5 3l6 5-6 5"/></svg>',
    arrow: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 8h10M9 4l4 4-4 4"/></svg>',
    search: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14"/></svg>'
  };

  // Category display names
  const CATEGORY_NAMES = {
    navigation: 'Nawigacja',
    orders: 'Zamówienia',
    products: 'Produkty',
    clients: 'Klienci',
    exclusive: 'Exclusive',
    proxy_orders: 'Proxy Orders',
    poland_orders: 'Poland Orders',
    shipping_requests: 'Zlecenia wysyłki'
  };

  const CATEGORY_ICONS = {
    navigation: ICONS.nav,
    orders: ICONS.order,
    products: ICONS.product,
    clients: ICONS.client,
    exclusive: ICONS.exclusive,
    proxy_orders: ICONS.proxy,
    poland_orders: ICONS.proxy,
    shipping_requests: ICONS.shipping
  };

  // ==========================================
  // State
  // ==========================================
  let isOpen = false;
  let isMobileOpen = false;
  let activeIndex = -1;
  let allItems = [];
  let debounceTimer = null;
  let currentQuery = '';

  // ==========================================
  // DOM References
  // ==========================================
  let wrapper, input, dropdown, backdrop, searchBtn;
  let mobileOverlay, mobileInput, mobileResults;
  let mobileSearchBtn;

  // ==========================================
  // Initialization
  // ==========================================
  function init() {
    // Desktop elements
    wrapper = document.getElementById('globalSearchWrapper');
    input = document.getElementById('globalSearchInput');
    dropdown = document.getElementById('globalSearchDropdown');
    backdrop = document.getElementById('globalSearchBackdrop');
    searchBtn = document.getElementById('globalSearchBtn');

    // Mobile elements
    mobileOverlay = document.getElementById('globalSearchMobileOverlay');
    mobileInput = document.getElementById('globalSearchMobileInput');
    mobileResults = document.getElementById('globalSearchMobileResults');
    mobileSearchBtn = document.getElementById('mobileSearchBtn');

    if (!wrapper || !input || !dropdown) return;

    // Desktop: click search button to open
    if (searchBtn) {
      searchBtn.addEventListener('click', open);
    }

    // Desktop: close when clicking outside search wrapper
    document.addEventListener('click', function(e) {
      if (!isOpen) return;
      if (wrapper.contains(e.target) || e.target === searchBtn || searchBtn.contains(e.target)) return;
      close();
    });

    // Desktop: input events
    input.addEventListener('input', onInputChange);
    input.addEventListener('keydown', onKeyDown);

    // Mobile: search button
    if (mobileSearchBtn) {
      mobileSearchBtn.addEventListener('click', openMobile);
    }

    // Mobile: back button
    var mobileBack = document.getElementById('globalSearchMobileBack');
    if (mobileBack) {
      mobileBack.addEventListener('click', closeMobile);
    }

    // Mobile: input events
    if (mobileInput) {
      mobileInput.addEventListener('input', onMobileInputChange);
      mobileInput.addEventListener('keydown', onMobileKeyDown);
    }

    // Keyboard shortcut: Cmd/Ctrl+K (handled in app.js, calls GlobalSearch.open())
  }

  // ==========================================
  // Open / Close (Desktop)
  // ==========================================
  function open() {
    if (isOpen) return;
    isOpen = true;

    wrapper.classList.add('active');
    dropdown.classList.add('visible');

    // Focus input
    requestAnimationFrame(function() {
      input.focus();
      input.select();
    });

    // If input has text, re-trigger search; otherwise show hint
    var existing = input.value.trim();
    if (existing) {
      handleQuery(existing, dropdown);
    } else {
      showHint();
    }
  }

  function close() {
    if (!isOpen) return;
    isOpen = false;

    wrapper.classList.remove('active');
    dropdown.classList.remove('visible');

    activeIndex = -1;
  }

  // ==========================================
  // Open / Close (Mobile)
  // ==========================================
  function openMobile() {
    if (!mobileOverlay) return;
    isMobileOpen = true;
    mobileOverlay.classList.add('active');
    document.body.style.overflow = 'hidden';

    requestAnimationFrame(function() {
      if (mobileInput) {
        mobileInput.focus();
      }
    });

    // Show hint
    if (mobileResults && (!mobileInput || !mobileInput.value.trim())) {
      mobileResults.innerHTML = renderHintHTML();
    }
  }

  function closeMobile() {
    if (!mobileOverlay) return;
    isMobileOpen = false;
    mobileOverlay.classList.remove('active');
    document.body.style.overflow = '';

    if (mobileInput) {
      mobileInput.value = '';
    }
    if (mobileResults) {
      mobileResults.innerHTML = '';
    }
    currentQuery = '';
    activeIndex = -1;
    allItems = [];
  }

  // ==========================================
  // Input Handling
  // ==========================================
  function onInputChange() {
    var query = input.value.trim();
    handleQuery(query, dropdown);
  }

  function onMobileInputChange() {
    var query = mobileInput.value.trim();
    handleQuery(query, mobileResults);
  }

  function handleQuery(query, container) {
    currentQuery = query;
    activeIndex = -1;

    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }

    if (query.length === 0) {
      showHint(container);
      return;
    }

    if (query.length < 1) {
      return;
    }

    // Show loading
    showLoading(container);

    // Debounce search
    debounceTimer = setTimeout(function() {
      performSearch(query, container);
    }, 250);
  }

  function onKeyDown(e) {
    handleKeyNavigation(e, dropdown, input);
  }

  function onMobileKeyDown(e) {
    handleKeyNavigation(e, mobileResults, mobileInput);
  }

  function handleKeyNavigation(e, container, inputEl) {
    if (e.key === 'Escape') {
      e.preventDefault();
      if (isMobileOpen) {
        closeMobile();
      } else {
        close();
      }
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIndex = Math.min(activeIndex + 1, allItems.length - 1);
      updateActiveItem(container);
      return;
    }

    if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = Math.max(activeIndex - 1, -1);
      updateActiveItem(container);
      if (activeIndex === -1) {
        inputEl.focus();
      }
      return;
    }

    if (e.key === 'Enter' && activeIndex >= 0 && activeIndex < allItems.length) {
      e.preventDefault();
      var item = allItems[activeIndex];
      if (item && item.url) {
        window.location.href = item.url;
      }
      return;
    }
  }

  function updateActiveItem(container) {
    var items = container.querySelectorAll('.global-search-item');
    items.forEach(function(el, i) {
      el.classList.toggle('active', i === activeIndex);
    });

    // Scroll active item into view
    if (activeIndex >= 0 && items[activeIndex]) {
      items[activeIndex].scrollIntoView({ block: 'nearest' });
    }
  }

  // ==========================================
  // API Search
  // ==========================================
  function performSearch(query, container) {
    fetch('/api/search?q=' + encodeURIComponent(query), {
      method: 'GET',
      headers: {
        'Accept': 'application/json'
      }
    })
    .then(function(response) {
      return response.json();
    })
    .then(function(data) {
      // Check if query is still current (user may have typed more)
      if (query !== currentQuery) return;

      if (data.success) {
        renderResults(data.results, query, container);
      } else {
        showEmpty(container, data.message || 'Brak wyników');
      }
    })
    .catch(function() {
      if (query !== currentQuery) return;
      showEmpty(container, 'Błąd wyszukiwania');
    });
  }

  // ==========================================
  // Rendering
  // ==========================================
  function renderResults(results, query, container) {
    allItems = [];
    var html = '';
    var categoryOrder = ['navigation', 'orders', 'products', 'clients', 'exclusive', 'proxy_orders', 'poland_orders', 'shipping_requests'];

    categoryOrder.forEach(function(category) {
      if (!results[category] || results[category].length === 0) return;

      var items = results[category];
      var categoryName = CATEGORY_NAMES[category] || category;
      var categoryIcon = CATEGORY_ICONS[category] || ICONS.nav;

      html += '<div class="global-search-category">';
      html += '<div class="global-search-category-title">' + escapeHtml(categoryName) + '</div>';

      items.forEach(function(item) {
        var idx = allItems.length;
        allItems.push(item);

        html += '<a href="' + escapeHtml(item.url) + '" class="global-search-item" data-index="' + idx + '">';
        html += '<div class="global-search-item-icon">' + categoryIcon + '</div>';
        html += '<div class="global-search-item-content">';
        html += '<div class="global-search-item-title">' + highlightMatch(item.title, query) + '</div>';
        if (item.subtitle) {
          html += '<div class="global-search-item-subtitle">' + highlightMatch(item.subtitle, query) + '</div>';
        }
        html += '</div>';

        if (item.badge) {
          html += '<span class="global-search-badge" style="background:' + (item.badge_bg || 'var(--bg-tertiary)') + ';color:' + (item.badge_color || 'var(--text-secondary)') + '">' + escapeHtml(item.badge) + '</span>';
        }

        html += '<div class="global-search-item-arrow">' + ICONS.arrow + '</div>';
        html += '</a>';
      });

      html += '</div>';
    });

    if (allItems.length === 0) {
      showEmpty(container, 'Brak wyników dla "' + query + '"');
      return;
    }

    // Wrap results in scrollable div, footer stays outside
    var footerHtml = '<div class="global-search-footer">';
    footerHtml += '<span><kbd>&uarr;</kbd> <kbd>&darr;</kbd> nawiguj</span>';
    footerHtml += '<span><kbd>Enter</kbd> otwórz</span>';
    footerHtml += '<span><kbd>Esc</kbd> zamknij</span>';
    footerHtml += '</div>';

    container.innerHTML = '<div class="global-search-results">' + html + '</div>' + footerHtml;

    // Add hover listeners to items
    var itemElements = container.querySelectorAll('.global-search-item');
    itemElements.forEach(function(el) {
      el.addEventListener('mouseenter', function() {
        activeIndex = parseInt(el.dataset.index);
        updateActiveItem(container);
      });
      el.addEventListener('click', function(e) {
        // Link navigation handled by <a> tag
        if (isMobileOpen) closeMobile();
        else close();
      });
    });
  }

  function showHint(container) {
    container = container || dropdown;
    container.innerHTML = renderHintHTML();
  }

  function renderHintHTML() {
    return '<div class="global-search-hint">Wpisz aby wyszukać...</div>';
  }

  function showLoading(container) {
    container = container || dropdown;
    container.innerHTML = '<div class="global-search-loading"><div class="global-search-spinner"></div><div>Szukam...</div></div>';
  }

  function showEmpty(container, message) {
    container = container || dropdown;
    container.innerHTML = '<div class="global-search-empty">' +
      '<div class="global-search-empty-icon">' + ICONS.search + '</div>' +
      '<div>' + escapeHtml(message) + '</div>' +
      '</div>';
  }

  // ==========================================
  // Utilities
  // ==========================================
  function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function highlightMatch(text, query) {
    if (!text || !query) return escapeHtml(text);
    var escaped = escapeHtml(text);
    var queryEscaped = escapeRegex(query);
    var regex = new RegExp('(' + queryEscaped + ')', 'gi');
    return escaped.replace(regex, '<span class="global-search-highlight">$1</span>');
  }

  function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  // ==========================================
  // Init on DOM Ready
  // ==========================================
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // ==========================================
  // Public API
  // ==========================================
  window.GlobalSearch = {
    open: function() {
      // Check if on mobile
      if (window.innerWidth <= 768) {
        openMobile();
      } else {
        open();
      }
    },
    close: function() {
      close();
      closeMobile();
    },
    openMobile: openMobile,
    closeMobile: closeMobile
  };

})();
