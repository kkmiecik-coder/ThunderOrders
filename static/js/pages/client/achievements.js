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

        // Share button
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

    function shareBadge(achievementId) {
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
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.success && data.image_url) {
                window.open(data.image_url, '_blank');
                if (window.Toast) window.Toast.show('Grafika wygenerowana!', 'success');
            } else if (data.error) {
                if (window.Toast) window.Toast.show(data.error, 'error');
            }
        })
        .catch(function() {
            if (window.Toast) window.Toast.show('Błąd generowania grafiki', 'error');
        });
    }

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
                    shareBadge(ach.id);
                }
            }
        }, 200);
        setTimeout(function() { clearInterval(shareInterval); }, 5000);
    }
});
