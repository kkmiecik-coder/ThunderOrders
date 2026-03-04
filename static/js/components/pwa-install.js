/**
 * PWA Install Prompt Handler
 * Shows a banner when the browser fires beforeinstallprompt.
 * 24h cooldown on dismiss via localStorage.
 */
(function () {
    var DISMISS_KEY = 'pwa-install-dismissed';
    var COOLDOWN_MS = 24 * 60 * 60 * 1000; // 24h

    var deferredPrompt = null;
    var banner = document.getElementById('pwa-install-banner');
    var installBtn = document.getElementById('pwa-install-btn');
    var dismissBtn = document.getElementById('pwa-dismiss-btn');

    if (!banner || !installBtn || !dismissBtn) return;

    // Check cooldown
    function isDismissed() {
        var ts = localStorage.getItem(DISMISS_KEY);
        if (!ts) return false;
        return (Date.now() - parseInt(ts, 10)) < COOLDOWN_MS;
    }

    // Check if already installed (standalone mode)
    function isInstalled() {
        return window.matchMedia('(display-mode: standalone)').matches ||
               window.navigator.standalone === true;
    }

    window.addEventListener('beforeinstallprompt', function (e) {
        e.preventDefault();
        deferredPrompt = e;

        if (isDismissed() || isInstalled()) return;

        banner.style.display = 'flex';
    });

    installBtn.addEventListener('click', function () {
        if (!deferredPrompt) return;
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(function (result) {
            banner.style.display = 'none';
            deferredPrompt = null;
        });
    });

    dismissBtn.addEventListener('click', function () {
        banner.style.display = 'none';
        localStorage.setItem(DISMISS_KEY, Date.now().toString());
    });

    // Hide if app becomes installed
    window.addEventListener('appinstalled', function () {
        banner.style.display = 'none';
        deferredPrompt = null;
    });
})();
