/**
 * Client Orders List - Enhanced Interactions with Custom Select and Filter Badges
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize Mobile Filters Toggle
    initFiltersToggle();

    // Initialize Custom Selects (Status, Payment Status, Proof Status)
    initCustomSelect('status');
    initCustomSelect('payment-status');
    initCustomSelect('proof-status');

    // Initialize Active Filters Display
    initActiveFilters();

    // Initialize Search Input with Debounce
    initSearchInput();

    // Add loading state to action buttons
    const actionButtons = document.querySelectorAll('.btn-icon');
    actionButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            this.style.opacity = '0.6';
            this.style.pointerEvents = 'none';
        });
    });

    // Smooth scroll to top on pagination
    const paginationLinks = document.querySelectorAll('.pagination-btn');
    paginationLinks.forEach(link => {
        link.addEventListener('click', function() {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    });

    // Add keyboard navigation for table rows
    const tableRows = document.querySelectorAll('.orders-table tbody tr');
    tableRows.forEach((row, index) => {
        row.setAttribute('tabindex', '0');
        row.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                const link = this.querySelector('.order-number-link');
                if (link) {
                    window.location.href = link.href;
                }
            }
        });
    });
});

/**
 * Initialize Mobile Filters Toggle
 */
function initFiltersToggle() {
    const toggleBtn = document.getElementById('filters-toggle');
    const filtersPanel = document.querySelector('.filters-panel');

    if (!toggleBtn || !filtersPanel) return;

    toggleBtn.addEventListener('click', function() {
        filtersPanel.classList.toggle('filters-open');
    });

    // Keep filters open if any filter is active
    const params = new URLSearchParams(window.location.search);
    const hasActiveFilters = params.has('status') || params.has('statuses') || params.has('date_from') || params.has('date_to') ||
                             params.has('search') || params.has('payment_status') || params.has('proof_status');

    if (hasActiveFilters) {
        filtersPanel.classList.add('filters-open');
    }
}

/**
 * Initialize Custom Select (Generic - works for any filter)
 * @param {string} prefix - The prefix used in element IDs (e.g., 'status', 'payment-status', 'proof-status')
 */
function initCustomSelect(prefix) {
    const wrapper = document.getElementById(`${prefix}-select-wrapper`);
    const trigger = document.getElementById(`${prefix}-trigger`);
    const dropdown = document.getElementById(`${prefix}-dropdown`);
    const input = document.getElementById(`${prefix}-input`);
    const label = document.getElementById(`${prefix}-label`);

    if (!wrapper || !trigger || !dropdown || !input || !label) return;

    const options = dropdown.querySelectorAll('.select-option');

    // Set initial label based on current value
    const currentValue = input.value;
    if (currentValue) {
        const selectedOption = Array.from(options).find(opt => opt.dataset.value === currentValue);
        if (selectedOption) {
            label.textContent = selectedOption.querySelector('span').textContent;
            selectedOption.classList.add('selected');
        }
    }

    // Toggle dropdown
    trigger.addEventListener('click', function(e) {
        e.stopPropagation();
        // Close other dropdowns first
        document.querySelectorAll('.custom-select-wrapper.open').forEach(w => {
            if (w !== wrapper) w.classList.remove('open');
        });
        wrapper.classList.toggle('open');
    });

    // Select option
    options.forEach(option => {
        option.addEventListener('click', function(e) {
            e.stopPropagation();
            const value = this.dataset.value;
            const text = this.querySelector('span').textContent;

            // Update input and label
            input.value = value;
            label.textContent = text;

            // Update selected state
            options.forEach(opt => opt.classList.remove('selected'));
            this.classList.add('selected');

            // Close dropdown
            wrapper.classList.remove('open');

            // Update active filters display
            updateActiveFilters();
        });
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', function(e) {
        if (!wrapper.contains(e.target)) {
            wrapper.classList.remove('open');
        }
    });
}

/**
 * Initialize Active Filters Display
 */
function initActiveFilters() {
    updateActiveFilters();
}

/**
 * Update Active Filters Badges
 */
function updateActiveFilters() {
    const activeFiltersContainer = document.getElementById('active-filters');
    const badgesContainer = document.getElementById('filters-badges');

    if (!activeFiltersContainer || !badgesContainer) return;

    // Clear existing badges
    badgesContainer.innerHTML = '';

    const filters = getActiveFilters();

    if (filters.length === 0) {
        activeFiltersContainer.style.display = 'none';
        return;
    }

    // Show active filters section
    activeFiltersContainer.style.display = 'flex';

    // Create badges
    filters.forEach(filter => {
        const badge = createFilterBadge(filter.label, filter.name, filter.value, filter.isMulti || false);
        badgesContainer.appendChild(badge);
    });
}

/**
 * Get Active Filters
 */
function getActiveFilters() {
    const filters = [];
    const params = new URLSearchParams(window.location.search);

    // Status filter (single)
    const status = params.get('status');
    if (status) {
        const statusDropdown = document.getElementById('status-dropdown');
        const selectedOption = statusDropdown?.querySelector(`[data-value="${status}"]`);
        const label = selectedOption?.querySelector('span')?.textContent || status;
        filters.push({ name: 'status', label: `Status: ${label}`, value: status });
    }

    // Statuses filter (multiple, comma-separated)
    const statuses = params.get('statuses');
    if (statuses) {
        const statusList = statuses.split(',').map(s => s.trim()).filter(s => s);
        const statusDropdown = document.getElementById('status-dropdown');

        statusList.forEach(statusSlug => {
            const selectedOption = statusDropdown?.querySelector(`[data-value="${statusSlug}"]`);
            const label = selectedOption?.querySelector('span')?.textContent || statusSlug;
            filters.push({ name: 'statuses', label: `Status: ${label}`, value: statusSlug, isMulti: true });
        });
    }

    // Date from filter
    const dateFrom = params.get('date_from');
    if (dateFrom) {
        filters.push({ name: 'date_from', label: `Od: ${dateFrom}`, value: dateFrom });
    }

    // Date to filter
    const dateTo = params.get('date_to');
    if (dateTo) {
        filters.push({ name: 'date_to', label: `Do: ${dateTo}`, value: dateTo });
    }

    // Search filter
    const search = params.get('search');
    if (search) {
        filters.push({ name: 'search', label: `Szukaj: "${search}"`, value: search });
    }

    // Payment status filter
    const paymentStatus = params.get('payment_status');
    if (paymentStatus) {
        const dropdown = document.getElementById('payment-status-dropdown');
        const selectedOption = dropdown?.querySelector(`[data-value="${paymentStatus}"]`);
        const label = selectedOption?.querySelector('span')?.textContent || paymentStatus;
        filters.push({ name: 'payment_status', label: `Płatność: ${label}`, value: paymentStatus });
    }

    // Proof status filter
    const proofStatus = params.get('proof_status');
    if (proofStatus) {
        const dropdown = document.getElementById('proof-status-dropdown');
        const selectedOption = dropdown?.querySelector(`[data-value="${proofStatus}"]`);
        const label = selectedOption?.querySelector('span')?.textContent || proofStatus;
        filters.push({ name: 'proof_status', label: `Dowód: ${label}`, value: proofStatus });
    }

    return filters;
}

/**
 * Create Filter Badge Element
 */
function createFilterBadge(label, name, value, isMulti = false) {
    const badge = document.createElement('div');
    badge.className = 'filter-badge';
    badge.innerHTML = `
        <span>${label}</span>
        <span class="filter-badge-remove" data-filter="${name}" data-value="${value}" data-multi="${isMulti}">
            <svg viewBox="0 0 12 12" fill="currentColor">
                <path d="M10 2L6 6L2 2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                <path d="M2 10L6 6L10 10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
        </span>
    `;

    // Add remove handler
    const removeBtn = badge.querySelector('.filter-badge-remove');
    removeBtn.addEventListener('click', function() {
        const filterName = this.dataset.filter;
        const filterValue = this.dataset.value;
        const isMultiFilter = this.dataset.multi === 'true';

        if (isMultiFilter) {
            removeMultiFilter(filterName, filterValue);
        } else {
            removeFilter(filterName);
        }
    });

    return badge;
}

/**
 * Remove Single Filter
 */
function removeFilter(filterName) {
    const params = new URLSearchParams(window.location.search);
    params.delete(filterName);

    // Preserve pagination if exists
    const page = params.get('page');
    if (!page) {
        params.delete('page');
    }

    // Redirect with updated params
    const newUrl = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
    window.location.href = newUrl;
}

/**
 * Remove Single Value from Multi-Value Filter (e.g., statuses)
 */
function removeMultiFilter(filterName, valueToRemove) {
    const params = new URLSearchParams(window.location.search);
    const currentValue = params.get(filterName);

    if (!currentValue) {
        return;
    }

    // Split, filter out the value, rejoin
    const values = currentValue.split(',').map(v => v.trim()).filter(v => v && v !== valueToRemove);

    if (values.length > 0) {
        params.set(filterName, values.join(','));
    } else {
        params.delete(filterName);
    }

    // Reset pagination when filter changes
    params.delete('page');

    // Redirect with updated params
    const newUrl = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
    window.location.href = newUrl;
}

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
    if (typeof window.showToast === 'function') {
        window.showToast(message, type);
    } else {
        console.log(`[${type.toUpperCase()}] ${message}`);
    }
}

/**
 * Toggle visibility of hidden order items
 * Called from onclick in template
 */
window.toggleOrderItems = function(orderId, totalItems) {
    const hiddenItems = document.getElementById(`hiddenItems-${orderId}`);
    const toggleBtn = hiddenItems?.parentElement.querySelector('.items-toggle-btn .toggle-text');

    if (!hiddenItems || !toggleBtn) return;

    const isHidden = hiddenItems.style.display === 'none';

    if (isHidden) {
        // Show hidden items
        hiddenItems.style.display = 'flex';
        toggleBtn.textContent = 'Ukryj pozostałe';
    } else {
        // Hide items
        hiddenItems.style.display = 'none';
        toggleBtn.textContent = `W sumie ${totalItems} przedmiotów - pokaż pozostałe`;
    }
};

/**
 * Initialize search input with debounce
 */
function initSearchInput() {
    const searchInput = document.getElementById('search');
    if (!searchInput) return;

    let searchTimeout = null;

    searchInput.addEventListener('input', function() {
        const value = this.value.trim();

        // Clear previous timeout
        if (searchTimeout) {
            clearTimeout(searchTimeout);
        }

        // Don't trigger for very short queries
        if (value.length > 0 && value.length < 3) {
            return;
        }

        // Debounce: wait 300ms after user stops typing
        searchTimeout = setTimeout(() => {
            // Auto-submit form
            const form = this.closest('form');
            if (form) {
                form.submit();
            }
        }, 300);
    });
}
