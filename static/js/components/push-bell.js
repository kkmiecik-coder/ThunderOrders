/**
 * Notification Center - Bell dropdown with notification list, badge, and push status.
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
    var markAllBtn = document.getElementById('notifMarkAllBtn');
    var pushDot = document.getElementById('notifPushDot');
    var pushText = document.getElementById('notifPushText');
    var mobileBellBtn = document.getElementById('mobilePushBtn');
    var mobileBadge = document.getElementById('mobileNotifBadge');
    var mobileBellText = document.getElementById('mobilePushText');

    if (!bellBtn) return;

    // === State ===
    var currentOffset = 0;
    var hasMore = false;
    var POLL_INTERVAL = 60000;
    var pollTimer = null;
    var isOpen = false;
    var loadedNotifIds = new Set();
    var currentUnreadCount = 0;

    // === Notification type → icon mapping ===
    var TYPE_ICONS = {
        order_status_changes: 'img/icons/check-circle.svg',
        payment_updates: 'img/icons/payment.svg',
        shipping_updates: 'img/icons/truck.svg',
        new_exclusive_pages: 'img/icons/exclusive.svg',
        cost_added: 'img/icons/payment-pending.svg',
        admin_alerts: 'img/icons/bell.svg'
    };
    var DEFAULT_ICON = 'img/icons/bell.svg';

    function getIconPath(notifType) {
        var path = TYPE_ICONS[notifType] || DEFAULT_ICON;
        // Build URL using the static prefix from the page
        var staticBase = document.querySelector('link[href*="/static/css/"]');
        if (staticBase) {
            var href = staticBase.getAttribute('href');
            var idx = href.indexOf('/static/');
            if (idx !== -1) {
                return href.substring(0, idx) + '/static/' + path;
            }
        }
        return '/static/' + path;
    }

    // === Badge ===
    function updateBadge(count) {
        count = parseInt(count, 10) || 0;
        currentUnreadCount = count;
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
        // Show/hide mark-all button
        if (markAllBtn) {
            markAllBtn.style.display = count > 0 ? '' : 'none';
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
        var item = document.createElement('div');
        item.className = 'notif-item' + (n.is_read ? '' : ' notif-unread');
        item.dataset.notifId = n.id;

        // Type icon
        var iconWrap = document.createElement('div');
        iconWrap.className = 'notif-item-icon';
        var iconImg = document.createElement('img');
        iconImg.src = getIconPath(n.notification_type);
        iconImg.alt = '';
        iconWrap.appendChild(iconImg);
        item.appendChild(iconWrap);

        // Content (clickable link)
        var link = document.createElement('a');
        link.href = n.url || '#';
        link.className = 'notif-item-content';

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

        link.appendChild(titleRow);

        if (n.body) {
            var body = document.createElement('div');
            body.className = 'notif-item-body';
            body.textContent = n.body;
            link.appendChild(body);
        }

        var time = document.createElement('div');
        time.className = 'notif-item-time';
        time.textContent = relativeTime(n.created_at);
        link.appendChild(time);

        item.appendChild(link);

        // Delete button
        var delBtn = document.createElement('button');
        delBtn.className = 'notif-item-delete';
        delBtn.title = 'Usuń';
        delBtn.innerHTML = '&times;';
        delBtn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            deleteNotification(n.id, item);
        });
        item.appendChild(delBtn);

        // Click on link = mark as read
        link.addEventListener('click', function () {
            if (!n.is_read) {
                markAsRead([n.id]);
                item.classList.remove('notif-unread');
                var d = item.querySelector('.notif-unread-dot');
                if (d) d.remove();
                n.is_read = true;
            }
        });

        return item;
    }

    // === API helpers ===
    function fetchUnreadCount() {
        fetch('/notifications/unread-count', { credentials: 'same-origin' })
            .then(function (r) { return r.json(); })
            .then(function (data) { updateBadge(data.count || 0); })
            .catch(function () {});
    }

    function fetchNotifications(offset, append) {
        var url = '/notifications/list?offset=' + offset + '&limit=10';
        fetch(url, { credentials: 'same-origin' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var notifications = data.notifications || [];
                hasMore = data.has_more || false;
                updateBadge(data.unread_count || 0);

                if (!append) {
                    var items = notifList.querySelectorAll('.notif-item');
                    items.forEach(function (el) { el.remove(); });
                    loadedNotifIds.clear();
                }

                if (notifications.length === 0 && !append) {
                    notifEmpty.style.display = '';
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

                var readCount = 0;
                notifications.forEach(function (n) { if (n.is_read) readCount++; });
                currentOffset = (append ? currentOffset : 0) + readCount;
            })
            .catch(function () {});
    }

    function markAsRead(ids) {
        fetch('/notifications/mark-read', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: ids })
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success) updateBadge(data.unread_count || 0);
        })
        .catch(function () {});
    }

    function markAllAsRead() {
        fetch('/notifications/mark-all-read', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' }
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success) {
                updateBadge(0);
                // Update UI
                notifList.querySelectorAll('.notif-unread').forEach(function (el) {
                    el.classList.remove('notif-unread');
                    var dot = el.querySelector('.notif-unread-dot');
                    if (dot) dot.remove();
                });
            }
        })
        .catch(function () {});
    }

    function deleteNotification(id, element) {
        fetch('/notifications/delete', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: id })
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success) {
                loadedNotifIds.delete(id);
                element.remove();
                updateBadge(data.unread_count);
                // Show empty state if no items left
                if (notifList.querySelectorAll('.notif-item').length === 0) {
                    notifEmpty.style.display = '';
                    loadMoreBtn.style.display = 'none';
                }
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
    }

    // === Event listeners ===
    bellBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        if (isOpen) closeDropdown();
        else openDropdown();
    });

    document.addEventListener('click', function (e) {
        if (isOpen && dropdown && !dropdown.contains(e.target) && !bellBtn.contains(e.target)) {
            closeDropdown();
        }
    });

    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            fetchNotifications(currentOffset, true);
        });
    }

    if (markAllBtn) {
        markAllBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            markAllAsRead();
        });
    }

    if (mobileBellBtn) {
        mobileBellBtn.addEventListener('click', function () {
            window.location.href = '/profile/#push';
        });
    }

    if (dropdown) {
        dropdown.addEventListener('click', function (e) {
            e.stopPropagation();
        });
    }

    // === Polling ===
    function startPolling() {
        if (pollTimer) clearInterval(pollTimer);
        pollTimer = setInterval(fetchUnreadCount, POLL_INTERVAL);
    }

    // Listen for subscription changes (compatibility with push-banner.js)
    window.addEventListener('push-subscription-changed', function () {
        updatePushStatus();
    });

    // === Init ===
    fetchUnreadCount();
    updatePushStatus();
    startPolling();
})();
