/**
 * ThunderOrders - Main App JavaScript
 * Sidebar collapse, Dark Mode, Mobile Menu, User Dropdown
 */

// ==========================================
// Login Preloader Logic (runs immediately)
// ==========================================
(function() {
  var preloader = document.getElementById('login-preloader');
  var shouldShow = sessionStorage.getItem('showLoginPreloader');
  var startTime = parseInt(sessionStorage.getItem('loginPreloaderStart')) || 0;

  if (shouldShow === 'true' && preloader) {
    // Preloader is already visible (set by inline script in base.html)
    // Calculate remaining time (minimum 2s total from login click)
    var elapsed = Date.now() - startTime;
    var minDuration = 2000;
    var remaining = Math.max(0, minDuration - elapsed);

    // Hide preloader after remaining time with fade out animation
    var hidePreloader = function() {
      // Remove instant class to enable transition, then remove visible
      preloader.classList.remove('instant');

      // Force reflow to apply transition
      preloader.offsetHeight;

      // Now fade out (transition will apply)
      preloader.classList.remove('visible');

      // Clear flags
      sessionStorage.removeItem('showLoginPreloader');
      sessionStorage.removeItem('loginPreloaderStart');
    };

    // Wait for remaining time before hiding
    setTimeout(hidePreloader, remaining);
  }
})();

// ==========================================
// State Management
// ==========================================
const AppState = {
  sidebarCollapsed: false,
  darkMode: false,
  mobileMenuOpen: false,
  userDropdownOpen: false,
};

// ==========================================
// DOM Elements
// ==========================================
const DOM = {
  html: document.documentElement,
  sidebar: document.getElementById('sidebar'),
  sidebarToggle: document.getElementById('sidebarToggle'),
  sidebarBackdrop: document.getElementById('sidebarBackdrop'),
  darkModeToggle: document.getElementById('darkModeToggle'),
  mobileDarkModeToggle: document.getElementById('mobileDarkModeToggle'),
  userDropdownBtn: document.getElementById('userDropdownBtn'),
  userDropdownMenu: document.getElementById('userDropdownMenu'),
  mobileMenuBtn: document.getElementById('mobileMenuBtn'),
  mobileMenuOverlay: document.getElementById('mobileMenuOverlay'),
  mobileMenuClose: document.getElementById('mobileMenuClose'),
};

// ==========================================
// Sidebar Collapse/Expand
// ==========================================
function toggleSidebar() {
  if (!DOM.sidebar) return;

  AppState.sidebarCollapsed = !AppState.sidebarCollapsed;
  DOM.sidebar.setAttribute('data-collapsed', AppState.sidebarCollapsed);

  // Update content padding immediately (CSS transition will animate it)
  updateContentPadding();

  // Save to backend
  saveSidebarState(AppState.sidebarCollapsed);

  // Save to localStorage as fallback
  localStorage.setItem('sidebarCollapsed', AppState.sidebarCollapsed);
}

function updateContentPadding() {
  // NOTE: This function is deprecated for dashboards using proper layout CSS
  // (.main-wrapper + .main-content handle padding now)
  // Kept for backwards compatibility with any legacy pages

  // Only apply to elements that explicitly need dynamic padding
  // (NOT .client-dashboard or .kpop-dashboard - they use layout CSS)
  const legacyDashboard = document.querySelector('.legacy-dashboard');

  if (!legacyDashboard) return;

  // Check if mobile (width < 768px)
  const isMobile = window.innerWidth < 768;

  if (isMobile) {
    legacyDashboard.style.paddingLeft = 'var(--space-4)';
    legacyDashboard.style.paddingTop = '60px';
  } else {
    const computedStyle = getComputedStyle(document.documentElement);
    const sidebarWidth = AppState.sidebarCollapsed
      ? parseInt(computedStyle.getPropertyValue('--sidebar-width-collapsed'))
      : parseInt(computedStyle.getPropertyValue('--sidebar-width'));
    const extraMargin = 32;
    const topbarHeight = computedStyle.getPropertyValue('--topbar-height') || '64px';

    legacyDashboard.style.paddingLeft = `${sidebarWidth + extraMargin}px`;
    legacyDashboard.style.paddingTop = topbarHeight;
  }
}

async function saveSidebarState(collapsed) {
  try {
    await fetch('/api/preferences/sidebar', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ collapsed }),
    });
  } catch (error) {
    console.error('Failed to save sidebar state:', error);
  }
}

// ==========================================
// Dark Mode Toggle
// ==========================================
function toggleDarkMode() {
  AppState.darkMode = !AppState.darkMode;
  applyDarkMode(AppState.darkMode);

  // Save to backend
  saveDarkModeState(AppState.darkMode);

  // Save to localStorage as fallback
  localStorage.setItem('darkMode', AppState.darkMode);
}

function applyDarkMode(isDark) {
  DOM.html.setAttribute('data-theme', isDark ? 'dark' : 'light');
}

async function saveDarkModeState(enabled) {
  try {
    await fetch('/api/preferences/dark-mode', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ enabled }),
    });
  } catch (error) {
    console.error('Failed to save dark mode state:', error);
  }
}

// Auto-detect system dark mode preference (only if user hasn't set preference)
function detectSystemDarkMode() {
  // Check if user has a saved preference
  const savedDarkMode = localStorage.getItem('darkMode');
  if (savedDarkMode !== null) {
    return savedDarkMode === 'true';
  }

  // Otherwise, check system preference
  if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return true;
  }

  return false;
}

// Listen for system dark mode changes
if (window.matchMedia) {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    // Only apply if user hasn't manually set preference
    const savedDarkMode = localStorage.getItem('darkMode');
    if (savedDarkMode === null) {
      AppState.darkMode = e.matches;
      applyDarkMode(AppState.darkMode);
    }
  });
}

// ==========================================
// User Dropdown Toggle
// ==========================================
function toggleUserDropdown(e) {
  if (e) e.stopPropagation();

  AppState.userDropdownOpen = !AppState.userDropdownOpen;

  if (DOM.userDropdownMenu) {
    if (AppState.userDropdownOpen) {
      DOM.userDropdownMenu.classList.add('active');
    } else {
      DOM.userDropdownMenu.classList.remove('active');
    }
  }
}

// Close dropdown when clicking outside
function handleClickOutside(e) {
  if (
    AppState.userDropdownOpen &&
    DOM.userDropdownBtn &&
    DOM.userDropdownMenu &&
    !DOM.userDropdownBtn.contains(e.target) &&
    !DOM.userDropdownMenu.contains(e.target)
  ) {
    toggleUserDropdown();
  }
}

// ==========================================
// Mobile Menu Toggle
// ==========================================
function toggleMobileMenu() {
  AppState.mobileMenuOpen = !AppState.mobileMenuOpen;

  if (DOM.mobileMenuOverlay) {
    if (AppState.mobileMenuOpen) {
      DOM.mobileMenuOverlay.classList.add('active');
      document.body.style.overflow = 'hidden';

      // Copy sidebar menu to mobile menu
      copyMenuToMobile();
    } else {
      DOM.mobileMenuOverlay.classList.remove('active');
      document.body.style.overflow = '';
    }
  }
}

function copyMenuToMobile() {
  const sidebarMenu = document.querySelector('.sidebar-menu');
  const mobileMenuNav = document.querySelector('.mobile-menu-nav');

  if (sidebarMenu && mobileMenuNav) {
    // Clone the menu
    const clonedMenu = sidebarMenu.cloneNode(true);

    // Clear mobile nav and append cloned menu
    mobileMenuNav.innerHTML = '';
    mobileMenuNav.appendChild(clonedMenu);

    // Close mobile menu when clicking on a link
    const links = mobileMenuNav.querySelectorAll('a');
    links.forEach(link => {
      link.addEventListener('click', () => {
        toggleMobileMenu();
      });
    });
  }
}

// ==========================================
// Mobile Sidebar Toggle (for tablet/mobile)
// ==========================================
function toggleMobileSidebar() {
  if (DOM.sidebar) {
    DOM.sidebar.classList.toggle('mobile-open');

    if (DOM.sidebarBackdrop) {
      DOM.sidebarBackdrop.classList.toggle('active');
    }

    document.body.style.overflow = DOM.sidebar.classList.contains('mobile-open') ? 'hidden' : '';
  }
}

// ==========================================
// Initialization
// ==========================================
function init() {
  // Initialize sidebar state from attribute
  if (DOM.sidebar) {
    const collapsedAttr = DOM.sidebar.getAttribute('data-collapsed');
    AppState.sidebarCollapsed = collapsedAttr === 'true';
  }

  // Initialize dark mode
  const currentTheme = DOM.html.getAttribute('data-theme');
  AppState.darkMode = currentTheme === 'dark';

  // If no theme set, check system preference or localStorage
  if (!currentTheme) {
    AppState.darkMode = detectSystemDarkMode();
    applyDarkMode(AppState.darkMode);
  }

  // Set initial content padding based on sidebar state
  updateContentPadding();

  // Event Listeners
  if (DOM.sidebarToggle) {
    DOM.sidebarToggle.addEventListener('click', toggleSidebar);
  }

  if (DOM.darkModeToggle) {
    DOM.darkModeToggle.addEventListener('click', toggleDarkMode);
  }

  if (DOM.mobileDarkModeToggle) {
    DOM.mobileDarkModeToggle.addEventListener('click', toggleDarkMode);
  }

  if (DOM.userDropdownBtn) {
    DOM.userDropdownBtn.addEventListener('click', toggleUserDropdown);
  }

  if (DOM.mobileMenuBtn) {
    DOM.mobileMenuBtn.addEventListener('click', toggleMobileMenu);
  }

  if (DOM.mobileMenuClose) {
    DOM.mobileMenuClose.addEventListener('click', toggleMobileMenu);
  }

  // Close mobile menu when clicking on overlay
  if (DOM.mobileMenuOverlay) {
    DOM.mobileMenuOverlay.addEventListener('click', (e) => {
      if (e.target === DOM.mobileMenuOverlay) {
        toggleMobileMenu();
      }
    });
  }

  // Close dropdown when clicking outside
  document.addEventListener('click', handleClickOutside);

  // Sidebar backdrop click (mobile)
  if (DOM.sidebarBackdrop) {
    DOM.sidebarBackdrop.addEventListener('click', toggleMobileSidebar);
  }

  // Global search shortcut (Cmd/Ctrl + K)
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      // TODO: Open global search modal
      console.log('Global search triggered');
    }
  });

  // Update content padding on window resize
  window.addEventListener('resize', () => {
    updateContentPadding();
  });
}

// ==========================================
// Run on DOM Ready
// ==========================================
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

// Expose functions globally for debugging
window.ThunderOrders = {
  toggleSidebar,
  toggleDarkMode,
  toggleUserDropdown,
  toggleMobileMenu,
  toggleMobileSidebar,
  AppState,
};
