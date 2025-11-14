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
    console.log('=== setupCategoryTooltips CALLED ===');
    const sidebar = document.getElementById('sidebar');
    console.log('Sidebar element:', sidebar);
    if (!sidebar) {
        console.error('Sidebar not found!');
        return;
    }

    const categories = sidebar.querySelectorAll('.sidebar-category');
    console.log('Found categories:', categories.length);

    categories.forEach((category, index) => {
        const subcategories = category.querySelector('.sidebar-subcategories');
        const arrow = category; // The ::before pseudo-element is on the category itself
        console.log(`Category ${index}:`, category, 'has subcategories:', !!subcategories);

        if (subcategories) {
            console.log(`Adding event listeners to category ${index}`);

            // Function to show tooltip
            const showTooltip = function() {
                const isCollapsed = sidebar.getAttribute('data-collapsed') === 'true';
                if (isCollapsed) {
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
                    category.classList.add('tooltip-visible');
                }
            };

            // Function to hide tooltip
            const hideTooltip = function() {
                const isCollapsed = sidebar.getAttribute('data-collapsed') === 'true';
                if (isCollapsed) {
                    // Hide subcategories tooltip
                    subcategories.style.removeProperty('opacity');
                    subcategories.style.removeProperty('visibility');
                    subcategories.style.removeProperty('pointer-events');
                    subcategories.style.removeProperty('top');
                    category.style.removeProperty('--arrow-top');

                    // Remove class to hide ::before arrow
                    category.classList.remove('tooltip-visible');
                }
            };

            // Show tooltip on mouseenter on category
            category.addEventListener('mouseenter', function() {
                console.log('MOUSEENTER on category', index);
                const isCollapsed = sidebar.getAttribute('data-collapsed') === 'true';
                console.log('Sidebar collapsed:', isCollapsed);

                if (isCollapsed) {
                    console.log('========== TOOLTIP DEBUG START ==========');
                    showTooltip();

                    // Wait for next frame to get computed styles
                    requestAnimationFrame(() => {
                        const rect = subcategories.getBoundingClientRect();
                        const computed = window.getComputedStyle(subcategories);
                        const parentRect = category.getBoundingClientRect();
                        const sidebarRect = sidebar.getBoundingClientRect();

                        console.log('📍 POSITION INFO:');
                        console.log('  Tooltip bounding rect:', {
                            top: rect.top,
                            left: rect.left,
                            right: rect.right,
                            bottom: rect.bottom,
                            width: rect.width,
                            height: rect.height
                        });
                        console.log('  Category bounding rect:', {
                            top: parentRect.top,
                            left: parentRect.left,
                            right: parentRect.right,
                            width: parentRect.width
                        });
                        console.log('  Sidebar bounding rect:', {
                            left: sidebarRect.left,
                            right: sidebarRect.right,
                            width: sidebarRect.width
                        });
                        console.log('  Window dimensions:', {
                            width: window.innerWidth,
                            height: window.innerHeight
                        });

                        console.log('🎨 COMPUTED STYLES:');
                        console.log('  display:', computed.display);
                        console.log('  position:', computed.position);
                        console.log('  opacity:', computed.opacity);
                        console.log('  visibility:', computed.visibility);
                        console.log('  pointer-events:', computed.pointerEvents);
                        console.log('  z-index:', computed.zIndex);
                        console.log('  left:', computed.left);
                        console.log('  top:', computed.top);
                        console.log('  width:', computed.width);
                        console.log('  height:', computed.height);
                        console.log('  overflow:', computed.overflow);
                        console.log('  overflow-x:', computed.overflowX);
                        console.log('  overflow-y:', computed.overflowY);
                        console.log('  background:', computed.background);

                        console.log('🔍 VISIBILITY CHECKS:');
                        console.log('  Is tooltip visible on screen?',
                            rect.left < window.innerWidth &&
                            rect.right > 0 &&
                            rect.top < window.innerHeight &&
                            rect.bottom > 0
                        );
                        console.log('  Is tooltip AFTER sidebar?', rect.left > sidebarRect.right);
                        console.log('  Distance from sidebar:', rect.left - sidebarRect.right, 'px');

                        console.log('🧱 PARENT CHECKS:');
                        let parent = subcategories.parentElement;
                        let level = 0;
                        while (parent && level < 5) {
                            const pComputed = window.getComputedStyle(parent);
                            console.log(`  Parent ${level} (${parent.tagName}.${parent.className}):`);
                            console.log('    overflow:', pComputed.overflow);
                            console.log('    position:', pComputed.position);
                            console.log('    z-index:', pComputed.zIndex);
                            parent = parent.parentElement;
                            level++;
                        }

                        console.log('✅ INLINE STYLES:');
                        console.log('  style.opacity:', subcategories.style.opacity);
                        console.log('  style.visibility:', subcategories.style.visibility);
                        console.log('  style.pointerEvents:', subcategories.style.pointerEvents);

                        console.log('========== TOOLTIP DEBUG END ==========');
                    });
                }
            });

            // Keep tooltip visible when hovering over it
            subcategories.addEventListener('mouseenter', function() {
                console.log('MOUSEENTER on tooltip', index);
                showTooltip(); // Keep it visible
            });

            // Hide tooltip when leaving the tooltip
            subcategories.addEventListener('mouseleave', function() {
                console.log('MOUSELEAVE on tooltip', index);
                hideTooltip();
            });

            // Hide tooltip on mouseleave from category (with small delay to allow moving to tooltip)
            category.addEventListener('mouseleave', function(e) {
                console.log('MOUSELEAVE on category', index);
                const isCollapsed = sidebar.getAttribute('data-collapsed') === 'true';

                if (isCollapsed) {
                    // Check if we're moving to the tooltip
                    setTimeout(() => {
                        // Only hide if we're not hovering over the tooltip
                        const tooltipHovered = subcategories.matches(':hover');
                        if (!tooltipHovered && !category.matches(':hover')) {
                            console.log('Hiding tooltip...');
                            hideTooltip();
                        }
                    }, 50); // Small delay to detect if moving to tooltip
                }
            });
        }
    });

    console.log('=== setupCategoryTooltips COMPLETE ===');
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('=== sidebar.js DOMContentLoaded FIRED ===');
    restoreCategoryStates();
    setupCategoryTooltips();
});
