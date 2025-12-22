/**
 * Client Orders List - Enhanced Interactions
 */

document.addEventListener('DOMContentLoaded', function() {
    // Auto-submit filters on change (except date inputs)
    const filterForm = document.querySelector('.client-filters');
    if (filterForm) {
        const statusSelect = filterForm.querySelector('#status');

        if (statusSelect) {
            statusSelect.addEventListener('change', function() {
                filterForm.submit();
            });
        }
    }

    // Add loading state to action buttons
    const actionButtons = document.querySelectorAll('.btn-icon');
    actionButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            // Add subtle loading indication
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

    // Enhance empty state button
    const emptyStateBtn = document.querySelector('.empty-state .btn-primary');
    if (emptyStateBtn) {
        emptyStateBtn.addEventListener('click', function(e) {
            // For now it's a placeholder, but we can add interaction later
            if (this.getAttribute('href') === '#') {
                e.preventDefault();
                showToast('Funkcja "Nowe zamówienie" będzie wkrótce dostępna', 'info');
            }
        });
    }
});

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
    // Check if toast system exists
    if (typeof window.showToast === 'function') {
        window.showToast(message, type);
    } else {
        // Fallback to console
        console.log(`[${type.toUpperCase()}] ${message}`);
    }
}
