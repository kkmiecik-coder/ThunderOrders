/**
 * Notification Center - Bell dropdown with notification list, badge, and push status.
 * Replaces the old push toggle dropdown.
 */
(function () {
    'use strict';

    // === DOM Elements ===
    var bellBtn = document.getElementById('pushBellBtn');
    var badge = document.getElementById('notifBadge');
    var dropdown = document.getElementById('notifDropdown');
    var notifList = document.getElementById('notifList');
    var notifEmpty = document.getElementById('notifEmpty');
    var loadMoreBtn = document.getElementById('notifLoadMore');
    var pushDot = document.getElementById('notifPushDot');
    var pushText = document.getElementById('notifPushText');
    var mobileBellBtn = document.getElementById('mobilePushBtn');
    var mobileBadge = document.getElementById('mobileNotifBadge');
    var mobileBellText = document.getElementById('mobilePushText');

    if (!bellBtn) return;

    // === State ===
    var currentOffset = 0;
    var hasMore = false;
    var markReadTimer = null;
    var MARK_READ_DELAY = 2000;
    var POLL_INTERVAL = 60000;
    var pollTimer = null;
    var isOpen = false;
    var loadedNotifIds = new Set();

    // === Badge ===
    function updateBadge(count) {
        count = parseInt(count, 10) || 0;
        if (badge) {
            badge.textContent = count > 99 ? '99+' : count;
            badge.style.display = count > 0 ? '' : 'none';
        }
        if (mobileBadge) {
            mobileBadge.textContent = count > 99 ? '99+' : count;
            mobileBadge.style.display = count > 0 ? '' : 'none';
        }
        if (mobileBellText) {
            mobileBellText.textContent = count > 0 ? ('Powiadomienia (' + count + ')') : 'Powiadomienia';
        }
    }

    // === Relative time in Polish ===
    function relativeTime(isoStr) {
        if (!isoStr) return '';
        var date = new Date(isoStr);
        var now = new Date();
        var diffMs = now - date;
        var diffSec = Math.floor(diffMs / 1000);
        var diffMin = Math.floor(diffSec / 60);
        var diffHour = Math.floor(diffMin / 60);
        var diffDay = Math.floor(diffHour / 24);

        if (diffSec < 60) return 'teraz';
        if (diffMin < 60) return diffMin + ' min temu';
        if (diffHour < 24) return diffHour + ' godz. temu';
        if (diffDay === 1) return 'wczoraj';
        if (diffDay < 30) return diffDay + ' dni temu';
        return date.toLocaleDateString('pl-PL', { day: 'numeric', month: 'short' });
    }

    // === Render single notification ===
    function renderNotifItem(n) {
        var item = document.createElement('a');
        item.href = n.url || '#';
        item.className = 'notif-item' + (n.is_read ? '' : ' notif-unread');
        item.dataset.notifId = n.id;

        var content = document.createElement('div');
        content.className = 'notif-item-content';

        var titleRow = document.createElement('div');
        titleRow.className = 'notif-item-title-row';

        var title = document.createElement('span');
        title.className = 'notif-item-title';
        title.textContent = n.title;
        titleRow.appendChild(title);

        if (!n.is_read) {
            var dot = document.createElement('span');
            dot.className = 'notif-unread-dot';
            titleRow.appendChild(dot);
        }

        content.appendChild(titleRow);

        if (n.body) {
            var body = document.createElement('div');
            body.className = 'notif-item-body';
            body.textContent = n.body;
            content.appendChild(body);
        }

        var time = document.createElement('div');
        time.className = 'notif-item-time';
        time.textContent = relativeTime(n.created_at);
        content.appendChild(time);

        item.appendChild(content);
        return item;
    }

    // === Fetch unread count ===
    function fetchUnreadCount() {
        fetch('/notifications/unread-count', { credentials: 'same-origin' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                updateBadge(data.count || 0);
            })
            .catch(function () {});
    }

    // === Fetch notifications ===
    function fetchNotifications(offset, append) {
        var url = '/notifications/list?offset=' + offset + '&limit=10';
        fetch(url, { credentials: 'same-origin' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var notifications = data.notifications || [];
                hasMore = data.has_more || false;
                updateBadge(data.unread_count || 0);

                if (!append) {
                    // Clear existing items (keep empty state element)
                    var items = notifList.querySelectorAll('.notif-item');
                    items.forEach(function (el) { el.remove(); });
                    loadedNotifIds.clear();
                }

                if (notifications.length === 0 && !append) {
                    notifEmpty.style.display = 'block';
                } else {
                    notifEmpty.style.display = 'none';
                    notifications.forEach(function (n) {
                        if (!loadedNotifIds.has(n.id)) {
                            loadedNotifIds.add(n.id);
                            notifList.appendChild(renderNotifItem(n));
                        }
                    });
                }

                loadMoreBtn.style.display = hasMore ? '' : 'none';

                // Count read items for offset tracking
                var readCount = 0;
                notifications.forEach(function (n) { if (n.is_read) readCount++; });
                currentOffset = (append ? currentOffset : 0) + readCount;

                // Start mark-read timer
                startMarkReadTimer();
            })
            .catch(function () {});
    }

    // === Mark visible unread as read ===
    function startMarkReadTimer() {
        clearMarkReadTimer();
        markReadTimer = setTimeout(function () {
            markVisibleAsRead();
        }, MARK_READ_DELAY);
    }

    function clearMarkReadTimer() {
        if (markReadTimer) {
            clearTimeout(markReadTimer);
            markReadTimer = null;
        }
    }

    function markVisibleAsRead() {
        var unreadItems = notifList.querySelectorAll('.notif-unread');
        if (unreadItems.length === 0) return;

        var ids = [];
        unreadItems.forEach(function (el) {
            ids.push(parseInt(el.dataset.notifId, 10));
        });

        fetch('/notifications/mark-read', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: ids })
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success) {
                updateBadge(data.unread_count || 0);
                // Update UI - remove unread styling
                unreadItems.forEach(function (el) {
                    el.classList.remove('notif-unread');
                    var dot = el.querySelector('.notif-unread-dot');
                    if (dot) dot.remove();
                });
            }
        })
        .catch(function () {});
    }

    // === Push status ===
    function updatePushStatus() {
        var PN = window.PushNotifications;
        if (!PN || !PN.isSupported()) {
            if (pushDot) pushDot.className = 'notif-push-dot notif-push-off';
            if (pushText) pushText.textContent = 'Push: niedostępne';
            return;
        }

        PN.isSubscribed().then(function (subscribed) {
            if (pushDot) pushDot.className = 'notif-push-dot ' + (subscribed ? 'notif-push-on' : 'notif-push-off');
            if (pushText) pushText.textContent = subscribed ? 'Push: włączone' : 'Push: wyłączone';
        });
    }

    // === Open/Close dropdown ===
    function openDropdown() {
        if (isOpen) return;
        isOpen = true;
        dropdown.classList.add('active');
        fetchNotifications(0, false);
        updatePushStatus();
    }

    function closeDropdown() {
        if (!isOpen) return;
        isOpen = false;
        dropdown.classList.remove('active');
        clearMarkReadTimer();
    }

    // === Event listeners ===
    bellBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        if (isOpen) {
            closeDropdown();
        } else {
            openDropdown();
        }
    });

    // Close on outside click
    document.addEventListener('click', function (e) {
        if (isOpen && dropdown && !dropdown.contains(e.target) && !bellBtn.contains(e.target)) {
            closeDropdown();
        }
    });

    // Load more
    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            fetchNotifications(currentOffset, true);
        });
    }

    // Mobile bell - open dropdown on desktop-like behavior or navigate
    if (mobileBellBtn) {
        mobileBellBtn.addEventListener('click', function () {
            // On mobile, navigate to profile#push or toggle dropdown
            // For simplicity: navigate to notifications section of profile
            window.location.href = '/profile/#push';
        });
    }

    // Prevent dropdown links from closing on click (let them navigate)
    if (dropdown) {
        dropdown.addEventListener('click', function (e) {
            e.stopPropagation();
        });
    }

    // === Polling ===
    function startPolling() {
        stopPolling();
        pollTimer = setInterval(fetchUnreadCount, POLL_INTERVAL);
    }

    function stopPolling() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    // Listen for subscription changes (compatibility with push-banner.js)
    window.addEventListener('push-subscription-changed', function (e) {
        updatePushStatus();
    });

    // === Init ===
    fetchUnreadCount();
    updatePushStatus();
    startPolling();
})();
