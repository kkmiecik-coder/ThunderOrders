/**
 * Sidebar Component JavaScript
 * Handles collapsible categories and state management
 */

// Flyout menu state
let currentFlyout = null;
let flyoutHideTimeout = null;

/**
 * Toggle sidebar category expand/collapse
 * @param {HTMLElement} headerElement - The category header element that was clicked
 */
function toggleSidebarCategory(headerElement) {
    const sidebar = document.getElementById('sidebar');
    const isCollapsed = sidebar && sidebar.getAttribute('data-collapsed') === 'true';
    const isMobile = window.innerWidth <= 768;
    const isMobileOpen = sidebar && sidebar.classList.contains('mobile-open');

    // Don't toggle if sidebar is collapsed on desktop - flyout menu will handle this
    // On mobile, always allow toggle (even if data-collapsed is true, sidebar shows full width)
    if (isCollapsed && !isMobile && !isMobileOpen) {
        return;
    }

    const categoryItem = headerElement.closest('.sidebar-category');

    if (!categoryItem) {
        console.error('Category item not found');
        return;
    }

    const wasExpanded = categoryItem.classList.contains('expanded');

    // Collapse all other categories (accordion behavior)
    document.querySelectorAll('.sidebar-category.expanded').forEach(otherCategory => {
        if (otherCategory !== categoryItem) {
            otherCategory.classList.remove('expanded');
            const otherName = otherCategory.querySelector('.sidebar-text').textContent.trim();
            saveCategoryState(otherName, false);
        }
    });

    // Toggle clicked category
    categoryItem.classList.toggle('expanded', !wasExpanded);

    // Save state to localStorage
    const categoryName = categoryItem.querySelector('.sidebar-text').textContent.trim();
    saveCategoryState(categoryName, !wasExpanded);
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
        let alreadyExpanded = false;

        const categories = document.querySelectorAll('.sidebar-category');

        // Priority: first expand the category with an active subcategory
        categories.forEach(category => {
            const hasActiveSubcategory = category.querySelector('.sidebar-sublink.active');
            if (hasActiveSubcategory && !alreadyExpanded) {
                category.classList.add('expanded');
                alreadyExpanded = true;
            } else {
                category.classList.remove('expanded');
            }
        });

        // If no active subcategory found, restore last saved expanded category
        if (!alreadyExpanded) {
            categories.forEach(category => {
                const categoryName = category.querySelector('.sidebar-text').textContent.trim();
                if (states[categoryName] === true && !alreadyExpanded) {
                    category.classList.add('expanded');
                    alreadyExpanded = true;
                }
            });
        }
    } catch (error) {
        console.error('Error restoring category states:', error);
    }
}

/**
 * Show flyout menu for a category
 * @param {HTMLElement} categoryHeader - The category header element
 */
function showFlyout(categoryHeader) {
    const sidebar = document.getElementById('sidebar');
    const isCollapsed = sidebar && sidebar.getAttribute('data-collapsed') === 'true';

    // Only show flyout when sidebar is collapsed
    if (!isCollapsed) {
        return;
    }

    // Clear any pending hide timeout
    if (flyoutHideTimeout) {
        clearTimeout(flyoutHideTimeout);
        flyoutHideTimeout = null;
    }

    const categoryItem = categoryHeader.closest('.sidebar-category');
    if (!categoryItem) return;

    const subcategoriesContainer = categoryItem.querySelector('.sidebar-subcategories');
    if (!subcategoriesContainer) return;

    // Get category position
    const headerRect = categoryHeader.getBoundingClientRect();

    // Create or get flyout element
    let flyout = document.getElementById('sidebar-flyout');
    if (!flyout) {
        flyout = document.createElement('div');
        flyout.id = 'sidebar-flyout';
        flyout.className = 'sidebar-flyout';
        document.body.appendChild(flyout);

        // Add mouse leave handler to flyout
        flyout.addEventListener('mouseenter', () => {
            if (flyoutHideTimeout) {
                clearTimeout(flyoutHideTimeout);
                flyoutHideTimeout = null;
            }
        });

        flyout.addEventListener('mouseleave', () => {
            hideFlyout();
        });
    }

    // Clone subcategories content
    const subcategoryItems = subcategoriesContainer.querySelectorAll('.sidebar-subitem');
    const flyoutList = document.createElement('ul');
    flyoutList.className = 'sidebar-flyout-list';

    subcategoryItems.forEach(item => {
        const link = item.querySelector('.sidebar-sublink');
        if (!link) return;

        const flyoutItem = document.createElement('li');
        flyoutItem.className = 'sidebar-flyout-item';

        const flyoutLink = document.createElement('a');
        flyoutLink.href = link.href;
        flyoutLink.className = 'sidebar-flyout-link';

        if (link.classList.contains('active')) {
            flyoutLink.classList.add('active');
        }
        if (link.classList.contains('disabled')) {
            flyoutLink.classList.add('disabled');
        }

        // Get text - either from .sidebar-text span or directly from link
        const textSpan = link.querySelector('.sidebar-text');
        if (textSpan) {
            flyoutLink.textContent = textSpan.textContent;
        } else {
            // Fallback: get text directly from the link (sublinks don't have .sidebar-text)
            flyoutLink.textContent = link.textContent.trim();
        }

        flyoutItem.appendChild(flyoutLink);
        flyoutList.appendChild(flyoutItem);
    });

    // Update flyout content
    flyout.innerHTML = '';
    flyout.appendChild(flyoutList);

    // Position flyout (align top with header top)
    flyout.style.top = `${headerRect.top}px`;

    // Check if flyout would go off-screen (bottom)
    const flyoutHeight = flyout.offsetHeight;
    const viewportHeight = window.innerHeight;

    if (headerRect.top + flyoutHeight > viewportHeight) {
        // Adjust position to keep it on screen
        flyout.style.top = `${Math.max(10, viewportHeight - flyoutHeight - 10)}px`;
    }

    // Show flyout
    currentFlyout = flyout;
    requestAnimationFrame(() => {
        flyout.classList.add('visible');
    });
}

/**
 * Hide flyout menu with delay
 */
function hideFlyout() {
    if (flyoutHideTimeout) {
        clearTimeout(flyoutHideTimeout);
    }

    flyoutHideTimeout = setTimeout(() => {
        const flyout = document.getElementById('sidebar-flyout');
        if (flyout) {
            flyout.classList.remove('visible');
        }
        currentFlyout = null;
        flyoutHideTimeout = null;
    }, 250); // 250ms delay
}

/**
 * Initialize flyout event listeners for all categories
 */
function initializeFlyoutListeners() {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar) return;

    const categoryHeaders = sidebar.querySelectorAll('.sidebar-category-header');

    categoryHeaders.forEach(header => {
        header.addEventListener('mouseenter', () => {
            showFlyout(header);
        });

        header.addEventListener('mouseleave', () => {
            hideFlyout();
        });
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    restoreCategoryStates();
    initializeFlyoutListeners();
});
