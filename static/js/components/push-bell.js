/**
 * Notification Center - Bell dropdown (desktop) + full-screen overlay (mobile).
 */
(function () {
    'use strict';

    // === DOM Elements (desktop) ===
    var bellBtn = document.getElementById('pushBellBtn');
    var badge = document.getElementById('notifBadge');
    var dropdown = document.getElementById('notifDropdown');
    var notifList = document.getElementById('notifList');
    var notifEmpty = document.getElementById('notifEmpty');
    var loadMoreBtn = document.getElementById('notifLoadMore');
    var markAllBtn = document.getElementById('notifMarkAllBtn');
    var pushDot = document.getElementById('notifPushDot');
    var pushText = document.getElementById('notifPushText');

    // === DOM Elements (mobile) ===
    var mobileBellBtn = document.getElementById('mobilePushBtn');
    var mobileBadge = document.getElementById('mobileNotifBadge');
    var mobileOverlay = document.getElementById('mobileNotifOverlay');
    var mobileNotifList = document.getElementById('mobileNotifList');
    var mobileNotifEmpty = document.getElementById('mobileNotifEmpty');
    var mobileLoadMoreBtn = document.getElementById('mobileNotifLoadMore');
    var mobileMarkAllBtn = document.getElementById('mobileMarkAllBtn');
    var mobileBackBtn = document.getElementById('mobileNotifBack');

    // === DOM Elements (notification popup) ===
    var notifPopup = document.getElementById('notifPopup');
    var notifPopupIcon = notifPopup ? notifPopup.querySelector('.notif-popup-icon') : null;
    var notifPopupTitle = document.getElementById('notifPopupTitle');
    var notifPopupBody = document.getElementById('notifPopupBody');
    var notifPopupMobile = document.getElementById('notifPopupMobile');
    var notifPopupMobileIcon = notifPopupMobile ? notifPopupMobile.querySelector('.notif-popup-icon') : null;
    var notifPopupMobileTitle = document.getElementById('notifPopupMobileTitle');
    var notifPopupMobileBody = document.getElementById('notifPopupMobileBody');

    if (!bellBtn) return;

    // === State (desktop) ===
    var currentOffset = 0;
    var hasMore = false;
    var POLL_INTERVAL = 60000;
    var pollTimer = null;
    var isOpen = false;
    var loadedNotifIds = new Set();
    var currentUnreadCount = 0;
    var popupDismissTimer = null;
    var lastSeenNotifId = 0;
    var initialPollDone = false;

    // === State (mobile) ===
    var mobileOffset = 0;
    var mobileHasMore = false;
    var isMobileOpen = false;
    var mobileLoadedIds = new Set();

    // === State: unread IDs seen while dropdown/overlay was open ===
    var seenUnreadIds = new Set();
    var mobileSeenUnreadIds = new Set();

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
        // Show/hide mark-all buttons
        if (markAllBtn) {
            markAllBtn.style.display = count > 0 ? '' : 'none';
        }
        if (mobileMarkAllBtn) {
            mobileMarkAllBtn.style.display = count > 0 ? '' : 'none';
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
    function renderNotifItem(n, targetListEl) {
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

        // Content
        var link = document.createElement('div');
        link.className = 'notif-item-content';
        link.style.cursor = 'pointer';

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
            deleteNotification(n.id, item, targetListEl);
        });
        item.appendChild(delBtn);

        // Click = mark as read + navigate if URL exists
        link.addEventListener('click', function (e) {
            e.preventDefault();
            if (!n.is_read) {
                markAsRead([n.id]);
                item.classList.remove('notif-unread');
                var d = item.querySelector('.notif-unread-dot');
                if (d) d.remove();
                n.is_read = true;
            }
            if (n.url) {
                window.location.href = n.url;
            }
        });

        return item;
    }

    // === API helpers ===
    function fetchUnreadCount() {
        fetch('/notifications/unread-count', { credentials: 'same-origin' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var newCount = data.count || 0;
                var previousCount = currentUnreadCount;
                updateBadge(newCount);
                if (newCount > previousCount && initialPollDone) {
                    fetchLatestNotification();
                }
                initialPollDone = true;
            })
            .catch(function () {});
    }

    // === Notification Popup ===
    function fetchLatestNotification() {
        fetch('/notifications/list?offset=0&limit=1', { credentials: 'same-origin' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var notifications = data.notifications || [];
                if (notifications.length > 0 && !notifications[0].is_read) {
                    showNotifPopup(notifications[0]);
                }
            })
            .catch(function () {});
    }

    function showNotifPopup(notif) {
        if (isOpen || isMobileOpen) return;
        if (notif.id <= lastSeenNotifId) return;
        lastSeenNotifId = notif.id;

        if (window.innerWidth <= 768) {
            showMobilePopup(notif);
        } else {
            showDesktopPopup(notif);
        }
    }

    function showDesktopPopup(notif) {
        if (!notifPopup) return;

        var iconImg = notifPopupIcon ? notifPopupIcon.querySelector('img') : null;
        if (iconImg) iconImg.src = getIconPath(notif.notification_type);

        if (notifPopupTitle) notifPopupTitle.textContent = notif.title || '';
        if (notifPopupBody) notifPopupBody.textContent = notif.body || '';

        notifPopup.dataset.url = notif.url || '';
        notifPopup.dataset.notifId = notif.id;

        notifPopup.classList.remove('closing');
        notifPopup.classList.add('active');

        if (popupDismissTimer) clearTimeout(popupDismissTimer);
        popupDismissTimer = setTimeout(function () { dismissPopup(); }, 3000);
    }

    function showMobilePopup(notif) {
        if (!notifPopupMobile) return;

        var iconImg = notifPopupMobileIcon ? notifPopupMobileIcon.querySelector('img') : null;
        if (iconImg) iconImg.src = getIconPath(notif.notification_type);

        if (notifPopupMobileTitle) notifPopupMobileTitle.textContent = notif.title || '';
        if (notifPopupMobileBody) notifPopupMobileBody.textContent = notif.body || '';

        notifPopupMobile.dataset.url = notif.url || '';
        notifPopupMobile.dataset.notifId = notif.id;

        notifPopupMobile.classList.remove('closing');
        notifPopupMobile.classList.add('active');

        if (popupDismissTimer) clearTimeout(popupDismissTimer);
        popupDismissTimer = setTimeout(function () { dismissPopup(); }, 3000);
    }

    function dismissPopup() {
        if (popupDismissTimer) {
            clearTimeout(popupDismissTimer);
            popupDismissTimer = null;
        }
        [notifPopup, notifPopupMobile].forEach(function (el) {
            if (el && el.classList.contains('active')) {
                el.classList.add('closing');
                setTimeout(function () {
                    el.classList.remove('active', 'closing');
                }, 300);
            }
        });
    }

    // Desktop: fetch notifications into desktop dropdown
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

                if (!append) {
                    seenUnreadIds.clear();
                }

                if (notifications.length === 0 && !append) {
                    notifEmpty.style.display = '';
                } else {
                    notifEmpty.style.display = 'none';
                    notifications.forEach(function (n) {
                        if (!loadedNotifIds.has(n.id)) {
                            loadedNotifIds.add(n.id);
                            notifList.appendChild(renderNotifItem(n, notifList));
                        }
                        if (!n.is_read) {
                            seenUnreadIds.add(n.id);
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

    // Mobile: fetch notifications into mobile overlay
    function fetchMobileNotifications(offset, append) {
        if (!mobileNotifList) return;
        var url = '/notifications/list?offset=' + offset + '&limit=10';
        fetch(url, { credentials: 'same-origin' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var notifications = data.notifications || [];
                mobileHasMore = data.has_more || false;
                updateBadge(data.unread_count || 0);

                if (!append) {
                    mobileNotifList.querySelectorAll('.notif-item').forEach(function (el) { el.remove(); });
                    mobileLoadedIds.clear();
                    mobileSeenUnreadIds.clear();
                }

                if (notifications.length === 0 && !append) {
                    if (mobileNotifEmpty) mobileNotifEmpty.style.display = '';
                } else {
                    if (mobileNotifEmpty) mobileNotifEmpty.style.display = 'none';
                    notifications.forEach(function (n) {
                        if (!mobileLoadedIds.has(n.id)) {
                            mobileLoadedIds.add(n.id);
                            mobileNotifList.appendChild(renderNotifItem(n, mobileNotifList));
                        }
                        if (!n.is_read) {
                            mobileSeenUnreadIds.add(n.id);
                        }
                    });
                }

                if (mobileLoadMoreBtn) mobileLoadMoreBtn.style.display = mobileHasMore ? '' : 'none';

                var readCount = 0;
                notifications.forEach(function (n) { if (n.is_read) readCount++; });
                mobileOffset = (append ? mobileOffset : 0) + readCount;
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
                // Update both desktop and mobile UI
                [notifList, mobileNotifList].forEach(function (list) {
                    if (!list) return;
                    list.querySelectorAll('.notif-unread').forEach(function (el) {
                        el.classList.remove('notif-unread');
                        var dot = el.querySelector('.notif-unread-dot');
                        if (dot) dot.remove();
                    });
                });
            }
        })
        .catch(function () {});
    }

    function deleteNotification(id, element, listEl) {
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
                mobileLoadedIds.delete(id);
                element.remove();
                updateBadge(data.unread_count);
                // Show empty state if no items left in the list where item was deleted
                if (listEl && listEl.querySelectorAll('.notif-item').length === 0) {
                    var emptyEl = (listEl === mobileNotifList) ? mobileNotifEmpty : notifEmpty;
                    var loadBtn = (listEl === mobileNotifList) ? mobileLoadMoreBtn : loadMoreBtn;
                    if (emptyEl) emptyEl.style.display = '';
                    if (loadBtn) loadBtn.style.display = 'none';
                }
            }
        })
        .catch(function () {});
    }

    // === Mark seen unread notifications as read ===
    function markSeenAsRead(idSet, listEl) {
        if (idSet.size === 0) return;
        var ids = Array.from(idSet);
        idSet.clear();
        markAsRead(ids);
        // Update UI immediately
        if (listEl) {
            ids.forEach(function (id) {
                var item = listEl.querySelector('.notif-item[data-notif-id="' + id + '"]');
                if (item) {
                    item.classList.remove('notif-unread');
                    var dot = item.querySelector('.notif-unread-dot');
                    if (dot) dot.remove();
                }
            });
        }
    }

    // Mark as read when navigating away while dropdown/overlay is open
    window.addEventListener('beforeunload', function () {
        var allSeenIds = [];
        seenUnreadIds.forEach(function (id) { allSeenIds.push(id); });
        mobileSeenUnreadIds.forEach(function (id) { allSeenIds.push(id); });
        if (allSeenIds.length === 0) return;
        // Use sendBeacon for reliability during page unload
        var data = JSON.stringify({ ids: allSeenIds });
        navigator.sendBeacon('/notifications/mark-read', new Blob([data], { type: 'application/json' }));
    });

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

    // === Desktop: Open/Close dropdown ===
    function openDropdown() {
        dismissPopup();
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
        markSeenAsRead(seenUnreadIds, notifList);
    }

    // === Mobile: Open/Close overlay ===
    function openMobileOverlay() {
        dismissPopup();
        if (!mobileOverlay || isMobileOpen) return;
        isMobileOpen = true;
        mobileOverlay.classList.add('active');
        document.body.style.overflow = 'hidden';
        fetchMobileNotifications(0, false);
    }

    function closeMobileOverlay() {
        if (!mobileOverlay || !isMobileOpen) return;
        isMobileOpen = false;
        mobileOverlay.classList.remove('active');
        document.body.style.overflow = '';
        markSeenAsRead(mobileSeenUnreadIds, mobileNotifList);
    }

    // === Event listeners (desktop) ===
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

    if (dropdown) {
        dropdown.addEventListener('click', function (e) {
            e.stopPropagation();
        });
    }

    // === Event listeners (mobile) ===
    if (mobileBellBtn) {
        mobileBellBtn.addEventListener('click', function () {
            openMobileOverlay();
        });
    }

    if (mobileBackBtn) {
        mobileBackBtn.addEventListener('click', function () {
            closeMobileOverlay();
        });
    }

    if (mobileLoadMoreBtn) {
        mobileLoadMoreBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            fetchMobileNotifications(mobileOffset, true);
        });
    }

    if (mobileMarkAllBtn) {
        mobileMarkAllBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            markAllAsRead();
        });
    }

    // === Popup event listeners ===
    if (notifPopup) {
        notifPopup.addEventListener('click', function (e) {
            if (e.target.closest('.notif-popup-close')) {
                e.stopPropagation();
                dismissPopup();
                return;
            }
            var url = notifPopup.dataset.url;
            var nId = notifPopup.dataset.notifId;
            if (nId) markAsRead([parseInt(nId, 10)]);
            dismissPopup();
            if (url) window.location.href = url;
        });
    }

    if (notifPopupMobile) {
        notifPopupMobile.addEventListener('click', function (e) {
            if (e.target.closest('.notif-popup-close')) {
                e.stopPropagation();
                dismissPopup();
                return;
            }
            var url = notifPopupMobile.dataset.url;
            var nId = notifPopupMobile.dataset.notifId;
            if (nId) markAsRead([parseInt(nId, 10)]);
            dismissPopup();
            if (url) window.location.href = url;
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
