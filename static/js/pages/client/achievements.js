// static/js/pages/client/achievements.js
document.addEventListener('DOMContentLoaded', function() {
    'use strict';

    var grid = document.getElementById('achievements-grid');
    var filters = document.getElementById('achievements-filters');
    var modal = document.getElementById('badge-detail-modal');
    var allData = [];
    var shimmerTimer = null;

    var RARITY_LABELS = {
        common: 'Pospolite',
        rare: 'Rzadkie',
        epic: 'Epickie',
        legendary: 'Legendarne',
    };

    var RARITY_RANK = { common: 1, rare: 2, epic: 3, legendary: 4 };

    // Fetch achievements
    fetch('/achievements/api/my', {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (!data.success) return;
        allData = data.achievements;
        document.getElementById('summary-unlocked').textContent = data.summary.unlocked;
        document.getElementById('summary-total').textContent = data.summary.total;
        renderGrid(allData);
    })
    .catch(function() {
        grid.innerHTML = '<div class="achievements-empty">Nie udało się załadować odznak</div>';
    });

    // Filter clicks
    if (filters) {
        filters.addEventListener('click', function(e) {
            var pill = e.target.closest('.filter-pill');
            if (!pill) return;
            filters.querySelectorAll('.filter-pill').forEach(function(p) {
                p.classList.remove('active');
            });
            pill.classList.add('active');
            var cat = pill.dataset.category;
            var filtered = cat === 'all'
                ? allData
                : allData.filter(function(a) { return a.category === cat; });
            renderGrid(filtered);
        });
    }

    function sortAchievements(achievements) {
        return achievements.slice().sort(function(a, b) {
            // Unlocked first
            if (a.unlocked !== b.unlocked) return a.unlocked ? -1 : 1;
            // Within same group: higher rarity first
            var ra = RARITY_RANK[a.rarity] || 0;
            var rb = RARITY_RANK[b.rarity] || 0;
            if (ra !== rb) return rb - ra;
            // Then by sort_order
            return (a.sort_order || 0) - (b.sort_order || 0);
        });
    }

    function renderGrid(achievements) {
        if (!achievements || achievements.length === 0) {
            grid.innerHTML = '<div class="achievements-empty">Brak odznak w tej kategorii</div>';
            return;
        }

        var sorted = sortAchievements(achievements);
        var unlocked = sorted.filter(function(a) { return a.unlocked; });
        var locked = sorted.filter(function(a) { return !a.unlocked; });

        var html = '';
        var idx = 0;

        // Render unlocked cards
        unlocked.forEach(function(a) {
            html += buildCard(a, false, idx);
            idx++;
        });

        // Section divider
        if (unlocked.length > 0 && locked.length > 0) {
            var dividerDelay = Math.min(idx * 0.04, 0.6);
            html += '<div class="achievements-divider" style="--enter-delay:' + dividerDelay + 's; animation: card-enter 0.5s cubic-bezier(0.22,1,0.36,1) both; animation-delay: ' + dividerDelay + 's;">'
                + '<div class="achievements-divider__line"></div>'
                + '<span class="achievements-divider__text">Do zdobycia</span>'
                + '<div class="achievements-divider__line"></div>'
                + '</div>';
            idx++;
        }

        // Render locked cards
        locked.forEach(function(a) {
            html += buildCard(a, true, idx);
            idx++;
        });

        grid.innerHTML = html;

        // Attach click handlers
        grid.querySelectorAll('.achievement-card').forEach(function(card) {
            card.addEventListener('click', function() {
                var ach = JSON.parse(decodeURIComponent(this.dataset.ach));
                openBadgeModal(ach);
            });
        });

        // Start random shimmer on unlocked cards
        startRandomShimmer();
    }

    function buildCard(a, isLocked, index) {
        var delay = Math.min(index * 0.04, 0.8);
        var iconSrc = a.icon_filename
            ? '/static/uploads/achievements/' + a.icon_filename
            : '';
        var iconContent = isLocked
            ? '<span>&#128274;</span>'
            : (iconSrc
                ? '<img src="' + iconSrc + '" alt="">'
                : '<span>&#127942;</span>');

        var progressHtml = '';
        if (isLocked && a.progress) {
            var pct = Math.min(100, a.progress.percent);
            progressHtml = '<div class="badge-progress">' + a.progress.current + ' / ' + a.progress.target + '</div>'
                + '<div class="badge-progress-bar"><div class="badge-progress-fill" style="width:' + pct + '%"></div></div>';
        }

        var rarityLabel = '<div class="badge-rarity ' + a.rarity + '">' + (RARITY_LABELS[a.rarity] || '') + '</div>';

        // Stat percentage under rarity
        var statHtml = '';
        if (a.stat_percentage > 0) {
            statHtml = '<div class="badge-stat">' + a.stat_percentage + '% użytkowników</div>';
        }

        var safeData = encodeURIComponent(JSON.stringify(a));
        var stateClass = isLocked ? 'locked' : 'unlocked';

        return '<div class="achievement-card ' + stateClass + '" data-rarity="' + a.rarity + '" data-ach="' + safeData + '" style="--enter-delay:' + delay + 's">'
            + '<div class="badge-icon ' + a.rarity + '">' + iconContent + '</div>'
            + '<div class="badge-name">' + escapeHtml(a.name) + '</div>'
            + rarityLabel
            + statHtml
            + progressHtml
            + '</div>';
    }

    // ================================================
    // Random Shimmer — one card at a time
    // ================================================
    function startRandomShimmer() {
        if (shimmerTimer) clearTimeout(shimmerTimer);

        function triggerNext() {
            var cards = grid.querySelectorAll('.achievement-card.unlocked');
            if (cards.length === 0) return;

            // Remove previous shimmer
            var prev = grid.querySelector('.achievement-card.shimmer-active');
            if (prev) prev.classList.remove('shimmer-active');

            // Pick random card
            var idx = Math.floor(Math.random() * cards.length);
            var card = cards[idx];

            // Force reflow so animation restarts
            void card.offsetHeight;
            card.classList.add('shimmer-active');

            // Remove class after animation (900ms) then schedule next
            shimmerTimer = setTimeout(function() {
                card.classList.remove('shimmer-active');
                // Random delay before next shimmer: 1.5–4.5s
                shimmerTimer = setTimeout(triggerNext, 1500 + Math.random() * 3000);
            }, 950);
        }

        // Start after entry animations settle
        shimmerTimer = setTimeout(triggerNext, 1800);
    }

    // ================================================
    // Badge Spotlight Modal
    // ================================================
    if (modal) {
        document.getElementById('badge-modal-close').addEventListener('click', closeModal);
        modal.addEventListener('click', function(e) {
            if (e.target === modal) closeModal();
        });
    }

    function closeModal() {
        modal.classList.add('closing');
        setTimeout(function() {
            modal.classList.remove('active', 'closing', 'locked-modal');
            clearLegendaryParticles();
            clearLegendaryShimmer();
        }, 300);
    }

    // ================================================
    // Legendary Particles
    // ================================================
    var particleContainer = null;
    var shimmerWrap = null;

    function spawnLegendaryShimmer() {
        clearLegendaryShimmer();
        var card = modal.querySelector('.badge-spotlight__card');
        if (!card) return;
        shimmerWrap = document.createElement('div');
        shimmerWrap.className = 'legendary-shimmer-wrap';
        var stripe = document.createElement('div');
        stripe.className = 'legendary-shimmer-stripe';
        shimmerWrap.appendChild(stripe);
        card.appendChild(shimmerWrap);
    }

    function clearLegendaryShimmer() {
        if (shimmerWrap && shimmerWrap.parentNode) {
            shimmerWrap.parentNode.removeChild(shimmerWrap);
        }
        shimmerWrap = null;
    }

    function spawnLegendaryParticles() {
        clearLegendaryParticles();

        var card = modal.querySelector('.badge-spotlight__card');
        if (!card) return;

        particleContainer = document.createElement('div');
        particleContainer.className = 'legendary-particles-wrap';
        particleContainer.style.cssText = 'position:absolute;inset:0;pointer-events:none;z-index:0;overflow:hidden;';
        modal.appendChild(particleContainer);

        // Wait for card to be positioned, then spawn particles from its edges
        setTimeout(function() {
            var rect = card.getBoundingClientRect();
            var modalRect = modal.getBoundingClientRect();
            // Card center relative to modal
            var cx = rect.left - modalRect.left + rect.width / 2;
            var cy = rect.top - modalRect.top + rect.height / 2;
            var hw = rect.width / 2;
            var hh = rect.height / 2;

            var count = 150;
            for (var i = 0; i < count; i++) {
                var p = document.createElement('div');
                p.className = 'legendary-particle';

                // Pick a random point on the card edge
                var side = Math.floor(Math.random() * 4);
                var startX, startY;
                if (side === 0) { // top
                    startX = cx - hw + Math.random() * rect.width;
                    startY = cy - hh;
                } else if (side === 1) { // right
                    startX = cx + hw;
                    startY = cy - hh + Math.random() * rect.height;
                } else if (side === 2) { // bottom
                    startX = cx - hw + Math.random() * rect.width;
                    startY = cy + hh;
                } else { // left
                    startX = cx - hw;
                    startY = cy - hh + Math.random() * rect.height;
                }

                // Direction: outward from card center
                var angle = Math.atan2(startY - cy, startX - cx);
                angle += (Math.random() - 0.5) * 0.8; // add spread
                var dist = 60 + Math.random() * 140;
                var dx = Math.cos(angle) * dist;
                var dy = Math.sin(angle) * dist;

                var dur = 2 + Math.random() * 3;
                var delay = Math.random() * 4;
                var size = 2 + Math.random() * 4;

                p.style.left = startX + 'px';
                p.style.top = startY + 'px';
                p.style.setProperty('--p-dx', dx + 'px');
                p.style.setProperty('--p-dy', dy + 'px');
                p.style.setProperty('--p-duration', dur + 's');
                p.style.setProperty('--p-delay', delay + 's');
                p.style.setProperty('--p-size', size + 'px');

                particleContainer.appendChild(p);
            }
        }, 150);
    }

    function clearLegendaryParticles() {
        if (particleContainer && particleContainer.parentNode) {
            particleContainer.parentNode.removeChild(particleContainer);
        }
        particleContainer = null;
    }

    function openBadgeModal(a) {
        // Remove previous state so animations can restart
        modal.classList.remove('active', 'closing', 'locked-modal');

        // Set rarity on modal for CSS variables
        modal.setAttribute('data-rarity', a.rarity);

        // Locked/unlocked state
        if (!a.unlocked) {
            modal.classList.add('locked-modal');
        }

        // Icon
        var iconEl = document.getElementById('badge-detail-icon');
        iconEl.className = 'badge-spotlight__icon';

        if (a.unlocked && a.icon_filename) {
            iconEl.innerHTML = '<img src="/static/uploads/achievements/' + a.icon_filename + '">';
        } else if (a.unlocked) {
            iconEl.innerHTML = '<span style="font-size:52px;">&#127942;</span>';
        } else {
            iconEl.innerHTML = '<span style="font-size:52px;">&#128274;</span>';
        }

        // Name & Description
        document.getElementById('badge-detail-name').textContent = a.name;
        document.getElementById('badge-detail-desc').textContent = a.description;

        // Rarity tag
        var rarityEl = document.getElementById('badge-detail-rarity');
        rarityEl.textContent = '\u2726 ' + (RARITY_LABELS[a.rarity] || a.rarity);
        rarityEl.className = 'badge-spotlight__rarity ' + a.rarity;

        // Progress (locked only)
        var progressWrap = document.getElementById('badge-detail-progress');
        if (!a.unlocked && a.progress) {
            var pct = Math.min(100, a.progress.percent);
            progressWrap.innerHTML =
                '<div class="badge-spotlight__progress-label">' + a.progress.current + ' / ' + a.progress.target + '</div>'
                + '<div class="badge-spotlight__progress-track">'
                + '<div class="badge-spotlight__progress-fill" style="width:0%"></div>'
                + '</div>'
                + '<div class="badge-spotlight__progress-pct">' + pct + '%</div>';
            progressWrap.style.display = '';
            // Animate fill after a short delay
            setTimeout(function() {
                var fill = progressWrap.querySelector('.badge-spotlight__progress-fill');
                if (fill) fill.style.width = pct + '%';
            }, 400);
        } else {
            progressWrap.innerHTML = '';
            progressWrap.style.display = 'none';
        }

        // Stat
        var statEl = document.getElementById('badge-detail-stat');
        statEl.textContent = a.stat_percentage > 0
            ? 'Posiada ' + a.stat_percentage + '% użytkowników'
            : '';

        // Unlock date
        var dateEl = document.getElementById('badge-detail-unlock-date');
        if (a.unlocked && a.unlocked_at) {
            var d = new Date(a.unlocked_at);
            dateEl.textContent = 'Zdobyte: ' + d.toLocaleDateString('pl-PL');
            dateEl.style.display = '';
        } else {
            dateEl.textContent = '';
            dateEl.style.display = 'none';
        }

        // Share button + reset panel
        var shareBtn = document.getElementById('btn-share-badge');
        shareBtn.style.display = a.unlocked ? 'inline-flex' : 'none';
        shareBtn.onclick = function() { shareBadge(a.id); };

        // Legendary effects
        clearLegendaryParticles();
        clearLegendaryShimmer();
        if (a.rarity === 'legendary' && a.unlocked) {
            setTimeout(function() {
                spawnLegendaryParticles();
                spawnLegendaryShimmer();
            }, 100);
        }

        // Double rAF ensures browser processes removal before re-adding
        // This reliably restarts all CSS animations (rings, stagger, etc.)
        requestAnimationFrame(function() {
            requestAnimationFrame(function() {
                modal.classList.add('active');
            });
        });
    }

    // ================================================
    // Share Preview Modal
    // ================================================
    var shareModal = document.getElementById('share-preview-modal');
    var shareCanvas = document.getElementById('share-canvas');
    var shareBackBtn = document.getElementById('share-back-btn');
    var btnNativeShare = document.getElementById('btn-native-share');
    var btnDownload = document.getElementById('btn-download-share');
    var currentShareAch = null;
    var currentRatio = '1:1';

    var RATIOS = {
        '1:1': { w: 1080, h: 1080 },
        '9:16': { w: 1080, h: 1920 },
        '3:4': { w: 1080, h: 1440 },
    };

    var SHARE_DESIGN = {
        common: {
            bg: '#0e0b14',
            glow: 'rgba(160,160,160,0.12)',
            cardBg: 'linear-gradient(180deg, rgba(120,180,120,0.08) 0%, rgba(20,10,35,0.96) 100%)',
            cardBorder: '1.5px solid rgba(160,160,160,0.15)',
            cardGlow: 'rgba(160,160,160,0.08)',
            accent: '#9CA3AF',
            accentRgb: '156,163,175',
            pillBg: 'rgba(160,160,160,0.15)',
            pillColor: '#aaa',
        },
        rare: {
            bg: '#080e1e',
            glow: 'rgba(59,130,246,0.35)',
            cardBg: 'linear-gradient(180deg, rgba(59,130,246,0.1) 0%, rgba(10,12,35,0.96) 100%)',
            cardBorder: '1.5px solid rgba(59,130,246,0.25)',
            cardGlow: 'rgba(59,130,246,0.12)',
            accent: '#3B82F6',
            accentRgb: '59,130,246',
            pillBg: 'rgba(91,170,255,0.12)',
            pillColor: '#7CC4FF',
        },
        epic: {
            bg: '#0c0616',
            glow: 'rgba(139,92,246,0.4)',
            cardBg: 'linear-gradient(180deg, rgba(139,92,246,0.12) 0%, rgba(15,8,35,0.96) 100%)',
            cardBorder: '1.5px solid rgba(179,136,255,0.3)',
            cardGlow: 'rgba(139,92,246,0.15)',
            accent: '#8B5CF6',
            accentRgb: '139,92,246',
            pillBg: 'rgba(185,110,255,0.12)',
            pillColor: '#D0A0FF',
        },
        legendary: {
            bg: '#110d02',
            glow: 'rgba(255,200,50,0.4)',
            cardBg: 'linear-gradient(180deg, rgba(232,163,8,0.14) 0%, rgba(25,18,10,0.96) 100%)',
            cardBorder: '1.5px solid rgba(255,200,50,0.35)',
            cardGlow: 'rgba(232,163,8,0.15)',
            accent: '#E8A308',
            accentRgb: '232,163,8',
            pillBg: 'rgba(245,183,43,0.14)',
            pillColor: '#FFD966',
        },
    };

    // Show native share on mobile
    if (navigator.share && navigator.canShare) {
        btnNativeShare.style.display = '';
    }

    function shareBadge(achievementId) {
        currentShareAch = allData.find(function(a) { return a.id === achievementId; });
        if (!currentShareAch) return;
        currentRatio = '1:1';

        // Reset ratio buttons
        shareModal.querySelectorAll('.share-preview__ratio').forEach(function(b) {
            b.classList.toggle('active', b.dataset.ratio === '1:1');
        });

        renderSharePreview();
        shareModal.classList.add('active');

        // Mark as shared on server
        var csrfMeta = document.querySelector('meta[name="csrf-token"]');
        var csrf = csrfMeta ? csrfMeta.content : '';
        fetch('/achievements/api/' + achievementId + '/share', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrf,
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: JSON.stringify({ format: 'post' }),
        }).catch(function() {});
    }

    function renderSharePreview() {
        var a = currentShareAch;
        if (!a) return;
        var r = RATIOS[currentRatio];
        var d = SHARE_DESIGN[a.rarity] || SHARE_DESIGN.common;
        var rarityLabel = RARITY_LABELS[a.rarity] || a.rarity;

        var pad = 100;
        var iconSrc = a.icon_filename
            ? '/static/uploads/achievements/' + a.icon_filename
            : '';
        var iconHtml = iconSrc
            ? '<img src="' + iconSrc + '" style="width:120px;height:120px;object-fit:contain;">'
            : '<span style="font-size:90px;line-height:1;">&#127942;</span>';

        var statHtml = a.stat_percentage > 0
            ? '<div style="font-size:28px;color:rgba(255,255,255,0.4);">Posiada ' + a.stat_percentage + '% użytkowników</div>'
            : '';

        var dateHtml = '';
        if (a.unlocked && a.unlocked_at) {
            var dt = new Date(a.unlocked_at);
            dateHtml = '<div style="font-size:24px;color:rgba(255,255,255,0.35);margin-top:8px;">Zdobyte: ' + dt.toLocaleDateString('pl-PL') + '</div>';
        }

        // Static particles for legendary
        var particlesHtml = '';
        if (a.rarity === 'legendary') {
            for (var i = 0; i < 80; i++) {
                var px = Math.random() * r.w;
                var py = Math.random() * r.h;
                var ps = 1.5 + Math.random() * 3.5;
                var po = 0.15 + Math.random() * 0.55;
                particlesHtml += '<div style="position:absolute;left:' + Math.round(px) + 'px;top:' + Math.round(py) + 'px;width:' + ps.toFixed(1) + 'px;height:' + ps.toFixed(1) + 'px;border-radius:50%;background:rgba(255,210,60,' + po.toFixed(2) + ');box-shadow:0 0 ' + (ps * 2).toFixed(1) + 'px rgba(255,210,60,' + (po * 0.4).toFixed(2) + ');"></div>';
            }
        }

        var glowSize = Math.max(r.w, r.h) * 0.75;

        shareCanvas.style.width = r.w + 'px';
        shareCanvas.style.height = r.h + 'px';
        shareCanvas.innerHTML =
            // Full dark background
            '<div style="width:100%;height:100%;background:' + d.bg + ';position:relative;overflow:hidden;font-family:Arial,sans-serif;">' +

            // Radial glow behind card
            '<div style="position:absolute;width:' + glowSize + 'px;height:' + glowSize + 'px;top:50%;left:50%;transform:translate(-50%,-50%);border-radius:50%;background:radial-gradient(circle,' + d.glow + ' 0%,transparent 70%);"></div>' +

            // Particles (legendary only)
            particlesHtml +

            // Card — fixed size (like 1:1), centered vertically
            '<div style="position:absolute;top:50%;left:' + pad + 'px;right:' + pad + 'px;transform:translateY(-50%);height:' + (r.w - 2 * pad) + 'px;border-radius:28px;background:' + d.cardBg + ';border:' + d.cardBorder + ';box-shadow:0 24px 80px rgba(0,0,0,0.5),0 0 60px ' + d.cardGlow + ';display:flex;flex-direction:column;align-items:center;justify-content:center;overflow:hidden;">' +

            // Logo — top of card
            '<div style="position:absolute;top:30px;"><img src="/static/img/icons/logo-full-white.png" style="height:44px;width:auto;margin-top:20px;"></div>' +

            // Centered content
            '<div style="display:flex;flex-direction:column;align-items:center;">' +

            // Icon with spinning rings (static representation)
            '<div style="position:relative;width:220px;height:220px;margin-bottom:40px;">' +
            // Outer ring
            '<div style="position:absolute;inset:0;border-radius:50%;border:2.5px solid ' + d.accent + ';opacity:0.3;"></div>' +
            // Inner ring
            '<div style="position:absolute;inset:8px;border-radius:50%;border:3px solid ' + d.accent + ';opacity:0.6;"></div>' +
            // Icon circle
            '<div style="position:absolute;inset:16px;border-radius:50%;border:3px solid ' + d.accent + ';background:linear-gradient(160deg,rgba(255,255,255,0.08),rgba(255,255,255,0.02));box-shadow:0 0 40px rgba(' + d.accentRgb + ',0.25);display:flex;align-items:center;justify-content:center;">' +
            iconHtml +
            '</div></div>' +

            // Name
            '<div style="font-size:52px;font-weight:700;color:#f5f5f5;text-align:center;margin-bottom:-10px;letter-spacing:-0.01em;">' + escapeHtml(a.name) + '</div>' +

            // Description
            '<div style="font-size:36px;color:rgba(255,255,255,0.5);text-align:center;line-height:1.55;margin-bottom:28px;max-width:650px;">' + escapeHtml(a.description) + '</div>' +

            // Rarity pill
            '<div style="display:inline-block;padding:12px 32px;border-radius:28px;font-size:28px;font-weight:600;background:' + d.pillBg + ';color:' + d.pillColor + ';letter-spacing:0.02em;margin-bottom:28px;">&#10022; ' + rarityLabel + '</div>' +

            // Stats + Date
            statHtml +
            dateHtml +

            '</div>' + // end content

            // Footer — bottom of card
            '<div style="position:absolute;bottom:30px;font-size:22px;font-weight:600;letter-spacing:2px;color:rgba(255,255,255,0.5);">thunderorders.cloud</div>' +

            '</div>' + // end card
            '</div>'; // end background

        scalePreview();
    }

    function scalePreview() {
        var viewport = document.getElementById('share-viewport');
        var r = RATIOS[currentRatio];
        viewport.style.height = 'auto';
        var maxW = viewport.clientWidth;
        // Calculate max available height: window minus other modal elements
        var card = viewport.closest('.share-preview__card');
        var otherH = 0;
        if (card) {
            Array.prototype.forEach.call(card.children, function(el) {
                if (el !== viewport) otherH += el.offsetHeight;
            });
            var cardStyle = getComputedStyle(card);
            otherH += parseInt(cardStyle.paddingTop) + parseInt(cardStyle.paddingBottom);
        }
        var maxH = window.innerHeight - otherH - 40; // 40px safety margin
        var scale = Math.min(maxW / r.w, maxH / r.h, 1);
        shareCanvas.style.transform = 'scale(' + scale + ')';
        shareCanvas.style.transformOrigin = 'top center';
        viewport.style.height = Math.ceil(r.h * scale) + 'px';
    }

    function fetchShareImage(callback) {
        if (!currentShareAch) return;
        var url = '/achievements/api/' + currentShareAch.id + '/share-image?format=' + encodeURIComponent(currentRatio);
        fetch(url)
            .then(function(r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.blob();
            })
            .then(callback)
            .catch(function() {
                if (window.Toast) window.Toast.show('Błąd generowania obrazka', 'error');
            });
    }

    // Ratio buttons
    shareModal.querySelectorAll('.share-preview__ratio').forEach(function(btn) {
        btn.addEventListener('click', function() {
            shareModal.querySelectorAll('.share-preview__ratio').forEach(function(b) {
                b.classList.remove('active');
            });
            btn.classList.add('active');
            currentRatio = btn.dataset.ratio;
            renderSharePreview();
        });
    });

    // Back button
    shareBackBtn.addEventListener('click', function() {
        shareModal.classList.add('closing');
        setTimeout(function() {
            shareModal.classList.remove('active', 'closing');
        }, 300);
    });

    shareModal.addEventListener('click', function(e) {
        if (e.target === shareModal) {
            shareModal.classList.add('closing');
            setTimeout(function() {
                shareModal.classList.remove('active', 'closing');
            }, 300);
        }
    });

    // Native share (mobile)
    btnNativeShare.addEventListener('click', function() {
        fetchShareImage(function(blob) {
            var file = new File([blob], 'thunderorders-achievement.png', { type: 'image/png' });
            if (navigator.canShare && navigator.canShare({ files: [file] })) {
                navigator.share({
                    files: [file],
                    title: 'Moje osiągnięcie — ThunderOrders',
                });
            } else {
                if (window.Toast) window.Toast.show('Udostępnianie plików nie jest obsługiwane', 'error');
            }
        });
    });

    // Download
    btnDownload.addEventListener('click', function() {
        fetchShareImage(function(blob) {
            var url = URL.createObjectURL(blob);
            var link = document.createElement('a');
            link.href = url;
            var slug = currentShareAch ? currentShareAch.slug : 'achievement';
            link.download = slug + '-' + currentRatio.replace(':', 'x') + '.png';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
            if (window.Toast) window.Toast.show('Pobrano!', 'success');
        });
    });

    // Resize handler for preview scaling
    window.addEventListener('resize', function() {
        if (shareModal.classList.contains('active')) scalePreview();
    });

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // Handle ?share= URL param (from unlock animation redirect)
    var urlParams = new URLSearchParams(window.location.search);
    var shareId = urlParams.get('share');
    if (shareId) {
        var shareInterval = setInterval(function() {
            if (allData.length > 0) {
                clearInterval(shareInterval);
                var ach = allData.find(function(a) { return a.id === parseInt(shareId); });
                if (ach && ach.unlocked) {
                    openBadgeModal(ach);
                }
            }
        }, 200);
        setTimeout(function() { clearInterval(shareInterval); }, 5000);
    }
});
