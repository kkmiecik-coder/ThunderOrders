/**
 * PWA Bottom Navigation Bar
 * Only active in standalone (PWA) mode.
 */
(function () {
    'use strict';

    // --- PWA Detection ---
    const isPWA = window.matchMedia('(display-mode: standalone)').matches
                || window.navigator.standalone === true;

    if (!isPWA) return;  // Exit early if not PWA

    // --- Viewport fit for safe areas ---
    const viewport = document.querySelector('meta[name="viewport"]');
    if (viewport && !viewport.content.includes('viewport-fit')) {
        viewport.content += ', viewport-fit=cover';
    }

    // --- DOM References ---
    const bottomBar = document.getElementById('pwaBottomBar');
    const sheet = document.getElementById('pwaBottomSheet');
    const sheetBackdrop = document.getElementById('pwaSheetBackdrop');
    const sheetClose = document.getElementById('pwaSheetClose');
    const sheetTitle = document.getElementById('pwaSheetTitle');
    const sheetBody = document.getElementById('pwaSheetBody');
    const searchBtn = document.getElementById('pwaSearchBtn');
    const moreBtn = document.getElementById('pwaMoreBtn');
    const moreBadge = document.getElementById('pwaMoreBadge');

    if (!bottomBar || !sheet) return;

    // --- Enable bottom bar (remove aria-hidden) ---
    bottomBar.removeAttribute('aria-hidden');

    // --- Sheet titles map ---
    const sheetTitles = {
        'client-more': 'Więcej',
        'admin-more': 'Więcej',
        'admin-orders': 'Zamówienia',
        'admin-warehouse': 'Magazyn'
    };

    // --- Template ID map ---
    const sheetTemplates = {
        'client-more': 'pwaSheetClientMore',
        'admin-more': 'pwaSheetAdminMore',
        'admin-orders': 'pwaSheetAdminOrders',
        'admin-warehouse': 'pwaSheetAdminWarehouse'
    };

    // --- Sheet Open/Close ---
    let sheetOpen = false;
    let currentSheetName = null;
    let closedByPopstate = false;

    function openSheet(sheetName) {
        const templateId = sheetTemplates[sheetName];
        const template = document.getElementById(templateId);
        if (!template) return;

        sheetTitle.textContent = sheetTitles[sheetName] || '';
        sheetBody.innerHTML = '';
        sheetBody.appendChild(template.content.cloneNode(true));

        // Bind accordion toggles
        sheetBody.querySelectorAll('.pwa-sheet-accordion-toggle').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var accordion = btn.closest('.pwa-sheet-accordion');
                if (accordion) accordion.classList.toggle('open');
            });
        });

        // Bind search button inside sheet
        var sheetSearchBtn = sheetBody.querySelector('#pwaSheetSearchBtn');
        if (sheetSearchBtn) {
            sheetSearchBtn.addEventListener('click', function () {
                closeSheet();
                var overlay = document.getElementById('globalSearchMobileOverlay');
                var input = document.getElementById('globalSearchMobileInput');
                if (overlay) {
                    overlay.classList.add('active');
                    if (input) setTimeout(function () { input.focus(); }, 150);
                }
            });
        }

        // Bind notification button inside sheet
        var sheetNotifBtn = sheetBody.querySelector('#pwaSheetNotifBtn');
        if (sheetNotifBtn) {
            sheetNotifBtn.addEventListener('click', function () {
                closeSheet();
                if (typeof window.openMobileNotifOverlay === 'function') {
                    window.openMobileNotifOverlay();
                }
            });
        }

        sheet.classList.add('open');
        sheetOpen = true;
        currentSheetName = sheetName;

        // Push history state for Android back button
        history.pushState({ pwaSheet: true }, '');
    }

    function closeSheet(fromPopstate) {
        if (!sheetOpen) return;
        sheet.classList.remove('open');
        sheetOpen = false;

        // Clean up history entry if not closed by back button
        if (!fromPopstate) {
            closedByPopstate = true;
            history.back();
        }

        currentSheetName = null;
    }

    // --- Event: Sheet buttons (data-sheet attribute) ---
    bottomBar.querySelectorAll('[data-sheet]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var name = btn.getAttribute('data-sheet');
            if (sheetOpen && currentSheetName === name) {
                // Same sheet — just close
                closeSheet();
            } else if (sheetOpen) {
                // Different sheet — close then reopen
                sheet.classList.remove('open');
                sheetOpen = false;
                currentSheetName = null;
                // Reopen without extra history entry (reuse existing)
                setTimeout(function () { openSheet(name); }, 50);
            } else {
                openSheet(name);
            }
        });
    });

    // --- Event: Close sheet ---
    if (sheetClose) sheetClose.addEventListener('click', function () { closeSheet(); });
    if (sheetBackdrop) sheetBackdrop.addEventListener('click', function () { closeSheet(); });

    // --- Event: Android back button ---
    window.addEventListener('popstate', function (e) {
        if (closedByPopstate) {
            closedByPopstate = false;
            return;  // Ignore — triggered by our own history.back()
        }
        if (sheetOpen) {
            closeSheet(true);
        }
    });

    // --- Event: Search button ---
    if (searchBtn) {
        searchBtn.addEventListener('click', function () {
            // Trigger existing mobile search overlay
            var overlay = document.getElementById('globalSearchMobileOverlay');
            var input = document.getElementById('globalSearchMobileInput');
            if (overlay) {
                overlay.classList.add('active');
                if (input) {
                    setTimeout(function () { input.focus(); }, 100);
                }
            }
        });
    }

    // --- Notification Badge Polling ---
    function updateBadge() {
        fetch('/notifications/unread-count', {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            var count = data.count || 0;
            // Bottom bar badge
            if (moreBadge) {
                moreBadge.textContent = count;
                moreBadge.style.display = count > 0 ? 'flex' : 'none';
            }
            // Sheet badge (if open)
            var sheetBadge = document.getElementById('pwaSheetNotifBadge');
            if (sheetBadge) {
                sheetBadge.textContent = count;
                sheetBadge.style.display = count > 0 ? 'flex' : 'none';
            }
        })
        .catch(function () { /* silent fail */ });
    }

    // Poll every 60 seconds
    updateBadge();
    setInterval(updateBadge, 60000);

    // Also update on visibility change
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible') {
            updateBadge();
        }
    });

})();
