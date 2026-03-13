// static/js/components/achievements-checker.js
// Checks for unseen achievements on every page load (with debouncing)
(function() {
    'use strict';

    var CACHE_KEY = 'achievements_last_check';
    var CACHE_TTL = 30000; // 30 seconds

    function shouldCheck() {
        var lastCheck = sessionStorage.getItem(CACHE_KEY);
        if (!lastCheck) return true;
        return (Date.now() - parseInt(lastCheck, 10)) > CACHE_TTL;
    }

    function markChecked() {
        sessionStorage.setItem(CACHE_KEY, Date.now().toString());
    }

    function checkUnseen() {
        if (!shouldCheck()) return;

        fetch('/achievements/api/unseen', {
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            markChecked();
            if (data.success && data.achievements && data.achievements.length > 0) {
                showUnlockAnimation(data.achievements);
            }
        })
        .catch(function() { /* silent fail */ });
    }

    function showUnlockAnimation(achievements) {
        // Delegate to achievement-unlock.js
        if (window.AchievementUnlock) {
            window.AchievementUnlock.show(achievements);
        }
    }

    // Run on DOMContentLoaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', checkUnseen);
    } else {
        checkUnseen();
    }
})();
