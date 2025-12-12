/**
 * Sidebar Component JavaScript
 * Handles collapsible categories and state management
 */

/**
 * Toggle sidebar category expand/collapse
 * @param {HTMLElement} headerElement - The category header element that was clicked
 */
function toggleSidebarCategory(headerElement) {
    const sidebar = document.getElementById('sidebar');
    const isCollapsed = sidebar && sidebar.getAttribute('data-collapsed') === 'true';

    // Don't toggle if sidebar is collapsed (show tooltip menu instead)
    if (isCollapsed) {
        return;
    }

    const categoryItem = headerElement.closest('.sidebar-category');

    if (!categoryItem) {
        console.error('Category item not found');
        return;
    }

    // Toggle expanded class
    categoryItem.classList.toggle('expanded');

    // Save state to localStorage
    const categoryName = categoryItem.querySelector('.sidebar-text').textContent.trim();
    const isExpanded = categoryItem.classList.contains('expanded');

    saveCategoryState(categoryName, isExpanded);
}

/**
 * Save category expanded state to localStorage
 * @param {string} categoryName - Name of the category
 * @param {boolean} isExpanded - Whether category is expanded
 */
function saveCategoryState(categoryName, isExpanded) {
    try {
        const states = JSON.parse(localStorage.getItem('sidebarCategoryStates') || '{}');
        states[categoryName] = isExpanded;
        localStorage.setItem('sidebarCategoryStates', JSON.stringify(states));
    } catch (error) {
        console.error('Error saving category state:', error);
    }
}

/**
 * Restore category states from localStorage
 */
function restoreCategoryStates() {
    try {
        const states = JSON.parse(localStorage.getItem('sidebarCategoryStates') || '{}');

        document.querySelectorAll('.sidebar-category').forEach(category => {
            const categoryName = category.querySelector('.sidebar-text').textContent.trim();
            const isExpanded = states[categoryName];

            // If state exists and is true, or if one of the subcategories is active, expand it
            const hasActiveSubcategory = category.querySelector('.sidebar-sublink.active');

            if (isExpanded === true || hasActiveSubcategory) {
                category.classList.add('expanded');
            } else if (isExpanded === false) {
                category.classList.remove('expanded');
            }
            // If no state exists (undefined), leave it as default (collapsed)
        });
    } catch (error) {
        console.error('Error restoring category states:', error);
    }
}

/**
 * Handle category tooltip display in collapsed sidebar
 * Uses JavaScript hover because CSS :hover had specificity issues
 */
function setupCategoryTooltips() {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar) {
        // Sidebar not present on this page (e.g., exclusive pages) - this is OK
        return;
    }

    const categories = sidebar.querySelectorAll('.sidebar-category');

    categories.forEach((category) => {
        const subcategories = category.querySelector('.sidebar-subcategories');
        let hoverTimeout = null; // Track timeout for cleanup

        if (subcategories) {

            // Function to show tooltip
            const showTooltip = function() {
                const isCollapsed = sidebar.getAttribute('data-collapsed') === 'true';
                if (!isCollapsed) return;

                // Clear any pending hide timeout
                if (hoverTimeout) {
                    clearTimeout(hoverTimeout);
                    hoverTimeout = null;
                }

                // Calculate position: align tooltip with category icon
                const categoryRect = category.getBoundingClientRect();
                const arrowVerticalCenter = categoryRect.top + (categoryRect.height / 2);

                // Position tooltip
                subcategories.style.setProperty('top', `${categoryRect.top}px`, 'important');

                // Position arrow (centered with icon)
                const arrowTop = arrowVerticalCenter;
                category.style.setProperty('--arrow-top', `${arrowTop}px`);

                // Show subcategories tooltip
                subcategories.style.setProperty('opacity', '1', 'important');
                subcategories.style.setProperty('visibility', 'visible', 'important');
                subcategories.style.setProperty('pointer-events', 'auto', 'important');
                subcategories.style.setProperty('display', 'block', 'important');
                category.classList.add('tooltip-visible');
            };

            // Function to hide tooltip
            const hideTooltip = function() {
                const isCollapsed = sidebar.getAttribute('data-collapsed') === 'true';
                if (!isCollapsed) return;

                // Clear any pending timeout
                if (hoverTimeout) {
                    clearTimeout(hoverTimeout);
                    hoverTimeout = null;
                }

                // Hide subcategories tooltip
                subcategories.style.removeProperty('opacity');
                subcategories.style.removeProperty('visibility');
                subcategories.style.removeProperty('pointer-events');
                subcategories.style.removeProperty('display');
                subcategories.style.removeProperty('top');
                category.style.removeProperty('--arrow-top');

                // Remove class to hide ::before arrow
                category.classList.remove('tooltip-visible');
            };

            // Delayed hide with proper cleanup
            const scheduleHide = function() {
                const isCollapsed = sidebar.getAttribute('data-collapsed') === 'true';
                if (!isCollapsed) return;

                // Clear any existing timeout
                if (hoverTimeout) {
                    clearTimeout(hoverTimeout);
                }

                // Schedule hide with longer delay
                hoverTimeout = setTimeout(() => {
                    // Only hide if we're not hovering over category OR tooltip
                    const tooltipHovered = subcategories.matches(':hover');
                    const categoryHovered = category.matches(':hover');

                    if (!tooltipHovered && !categoryHovered) {
                        hideTooltip();
                    }
                }, 150); // Increased from 50ms to 150ms for smoother transition
            };

            // Show tooltip on mouseenter on category
            category.addEventListener('mouseenter', function() {
                const isCollapsed = sidebar.getAttribute('data-collapsed') === 'true';
                if (isCollapsed) {
                    showTooltip();
                }
            });

            // Keep tooltip visible when hovering over it
            subcategories.addEventListener('mouseenter', function() {
                const isCollapsed = sidebar.getAttribute('data-collapsed') === 'true';
                if (isCollapsed) {
                    showTooltip(); // Keep it visible and cancel any pending hide
                }
            });

            // Hide tooltip when leaving the tooltip
            subcategories.addEventListener('mouseleave', function() {
                scheduleHide();
            });

            // Hide tooltip on mouseleave from category (with delay to allow moving to tooltip)
            category.addEventListener('mouseleave', function() {
                scheduleHide();
            });
        }
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    restoreCategoryStates();
    setupCategoryTooltips();
});
