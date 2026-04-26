// static/js/components/achievement-unlock.js
// Achievement Unlock Overlay — Rarity-differentiated animations
// Pre-builds DOM + CSS before activation for jank-free rendering
window.AchievementUnlock = (function() {
    'use strict';

    var prepared = [];   // { achievement, overlay, rarity, cfg } — pre-built, in DOM, hidden
    var isShowing = false;
    var autoDismissTimer = null;
    var cssReady = false;

    var R = {
        common: {
            color: '#9CA3AF', label: 'Pospolite',
            rays: 0, particles: 0, confetti: 0, sparks: 0,
            shockwaves: 0, orbitDots: 0, dustMotes: 0,
            shake: false, flash: false, beam: false, godray: false,
            autoDismiss: 0
        },
        rare: {
            color: '#60B0FF', label: 'Rzadkie',
            rays: 6, particles: 10, confetti: 0, sparks: 0,
            shockwaves: 0, orbitDots: 0, dustMotes: 0,
            shake: false, flash: true, beam: false, godray: false,
            autoDismiss: 0
        },
        epic: {
            color: '#C080FF', label: 'Epickie',
            rays: 12, particles: 24, confetti: 20, sparks: 8,
            shockwaves: 1, orbitDots: 0, dustMotes: 0,
            shake: false, flash: false, beam: false, godray: false,
            autoDismiss: 0
        },
        legendary: {
            color: '#FFCC44', label: 'Legendarne',
            rays: 12, particles: 40, confetti: 0, sparks: 0,
            shockwaves: 3, orbitDots: 24, dustMotes: 16,
            shake: false, flash: false, beam: true, godray: true,
            supernova: false, nebulae: 0, shootingStars: 0,
            autoDismiss: 0
        },
        cosmic: {
            color: '#C084FC', label: 'Kosmiczne',
            rays: 16, particles: 60, confetti: 0, sparks: 0,
            shockwaves: 4, orbitDots: 32, dustMotes: 24,
            shake: false, flash: false, beam: true, godray: true,
            supernova: true, nebulae: 3, shootingStars: 5,
            autoDismiss: 0
        }
    };

    /* ═══════════════════════════════════════════
       PUBLIC API
       ═══════════════════════════════════════════ */
    function show(achievements) {
        // Step 1: Inject CSS once (idempotent)
        injectCSS();

        // Step 2: Pre-build all overlays and append hidden to DOM
        for (var i = 0; i < achievements.length; i++) {
            var a = achievements[i];
            var rarity = a.rarity || 'common';
            var cfg = R[rarity] || R.common;
            var overlay = buildOverlay(a, rarity, cfg);
            document.body.appendChild(overlay);
            prepared.push({ achievement: a, overlay: overlay, rarity: rarity, cfg: cfg });
        }

        // Step 3: If not already showing, warm up GPU layers then activate
        if (!isShowing) {
            warmup(function() {
                activateNext();
            });
        }
    }

    /* ═══════════════════════════════════════════
       WARMUP — give browser time to settle
       ═══════════════════════════════════════════ */
    function warmup(callback) {
        // Double rAF: frame 1 = browser parses/layouts new DOM,
        // frame 2 = GPU layers created, compositing ready
        requestAnimationFrame(function() {
            requestAnimationFrame(function() {
                callback();
            });
        });
    }

    /* ═══════════════════════════════════════════
       ACTIVATE — start animation on prepared overlay
       ═══════════════════════════════════════════ */
    function activateNext() {
        if (!prepared.length) { isShowing = false; return; }
        isShowing = true;
        if (autoDismissTimer) { clearTimeout(autoDismissTimer); autoDismissTimer = null; }

        var item = prepared[0]; // don't shift yet — close will shift
        bindEvents(item.overlay, item.achievement, item.cfg);
        startSequence(item.overlay, item.achievement, item.rarity, item.cfg);
    }

    /* ═══════════════════════════════════════════
       BUILD OVERLAY — creates DOM, appends nothing, returns element
       ═══════════════════════════════════════════ */
    function buildOverlay(a, rarity, cfg) {
        var overlay = document.createElement('div');
        overlay.className = 'auo auo--' + rarity;

        var iconSrc = a.has_icon
            ? '/static/uploads/achievements/' + a.slug + '@256.png'
            : null;
        var iconHTML = iconSrc
            ? '<img src="' + iconSrc + '" alt="' + a.name + '">'
            : '<span class="auo__icon-emoji">\uD83C\uDFC6</span>';

        var percentText = (a.stat_percentage !== undefined)
            ? 'Posiada ' + a.stat_percentage + '% użytkowników' : '';

        var html = '';

        // Effects layer
        if (cfg.flash) html += '<div class="auo__flash"></div>';
        if (cfg.beam) html += '<div class="auo__beam"></div>';
        if (cfg.godray) html += '<div class="auo__godray"></div>';

        // Cosmic-only: supernova flash + nebulae + shooting stars
        if (cfg.supernova) html += '<div class="auo__supernova"></div>';
        if (cfg.nebulae > 0) {
            html += '<div class="auo__nebulae">';
            html += '<div class="auo__nebula auo__nebula--purple"></div>';
            html += '<div class="auo__nebula auo__nebula--blue"></div>';
            html += '<div class="auo__nebula auo__nebula--pink"></div>';
            html += '</div>';
        }
        if (cfg.shootingStars > 0) {
            html += '<div class="auo__shooting-stars">';
            for (var ss = 0; ss < cfg.shootingStars; ss++) {
                html += '<div class="auo__shooting-star" style="top:' + (5 + Math.random() * 70) + '%;animation-delay:' + (1.5 + ss * 0.4 + Math.random() * 0.3) + 's;"></div>';
            }
            html += '</div>';
        }

        for (var sw = 0; sw < cfg.shockwaves; sw++) {
            html += '<div class="auo__shockwave" style="--sw-delay:' + (sw * 0.15) + 's;"></div>';
        }

        if (cfg.rays > 0) {
            html += '<div class="auo__rays">';
            for (var r = 0; r < cfg.rays; r++) {
                html += '<div class="auo__ray" style="transform:rotate(' + ((360 / cfg.rays) * r) + 'deg);animation-delay:' + (r * 0.08) + 's;"></div>';
            }
            html += '</div>';
        }

        if (cfg.particles > 0) {
            var pc = pColors(rarity);
            var groups = (rarity === 'legendary' || rarity === 'cosmic') ? 3 : 1;
            var groupSize = Math.ceil(cfg.particles / groups);
            for (var g = 0; g < groups; g++) {
                var groupClass = groups > 1 ? ' auo__particles--g' + (g + 1) : '';
                html += '<div class="auo__particles' + groupClass + '">';
                var start = g * groupSize;
                var end = Math.min(start + groupSize, cfg.particles);
                for (var p = start; p < end; p++) {
                    html += '<div class="auo__particle" style="left:' + (10 + Math.random() * 80) + '%;bottom:' + (15 + Math.random() * 35) + '%;width:' + (2 + Math.random() * 4) + 'px;height:' + (2 + Math.random() * 4) + 'px;background:' + pc[p % pc.length] + ';animation-duration:' + (2.5 + Math.random() * 2.5) + 's;animation-delay:' + (Math.random() * 1.5) + 's;"></div>';
                }
                html += '</div>';
            }
        }

        if (cfg.confetti > 0) {
            html += '<div class="auo__confetti">';
            var cc = cColors(rarity);
            for (var c = 0; c < cfg.confetti; c++) {
                html += '<div class="auo__confetti-piece" style="left:' + (2 + Math.random() * 96) + '%;background:' + cc[c % cc.length] + ';width:' + (5 + Math.random() * 5) + 'px;height:' + (5 + Math.random() * 5) + 'px;animation-duration:' + (2 + Math.random() * 2) + 's;animation-delay:' + (Math.random() * 0.8) + 's;border-radius:' + (c % 3 === 0 ? '50%' : (c % 3 === 1 ? '2px' : '1px')) + ';"></div>';
            }
            html += '</div>';
        }

        if (cfg.sparks > 0) {
            html += '<div class="auo__sparks">';
            for (var s = 0; s < cfg.sparks; s++) {
                html += '<div class="auo__spark" style="--spark-angle:' + ((360 / cfg.sparks) * s + (Math.random() * 20 - 10)) + 'deg;--spark-dist:' + (120 + Math.random() * 80) + 'px;animation-delay:' + (Math.random() * 2) + 's;animation-duration:' + (0.4 + Math.random() * 0.6) + 's;"></div>';
            }
            html += '</div>';
        }

        if (cfg.orbitDots > 0) {
            html += '<div class="auo__orbit">';
            for (var o = 0; o < cfg.orbitDots; o++) {
                var od = 4 + Math.random() * 4;
                html += '<div class="auo__orbit-wrap" style="animation-duration:' + od + 's;animation-delay:' + (-(Math.random() * od)) + 's;">';
                html += '<div class="auo__orbit-dot" style="transform:translateX(' + (130 + Math.random() * 80) + 'px);width:' + (2 + Math.random() * 3) + 'px;height:' + (2 + Math.random() * 3) + 'px;opacity:' + (0.4 + Math.random() * 0.5) + ';"></div>';
                html += '</div>';
            }
            html += '</div>';
        }

        if (cfg.dustMotes > 0) {
            html += '<div class="auo__dust">';
            for (var d = 0; d < cfg.dustMotes; d++) {
                html += '<div class="auo__dust-mote" style="left:' + (5 + Math.random() * 90) + '%;top:' + (5 + Math.random() * 90) + '%;width:' + (1 + Math.random() * 2.5) + 'px;height:' + (1 + Math.random() * 2.5) + 'px;animation-duration:' + (4 + Math.random() * 6) + 's;animation-delay:' + (Math.random() * 3) + 's;"></div>';
            }
            html += '</div>';
        }

        // Card
        html += '<div class="auo__card">';
        if (rarity !== 'common') html += '<div class="auo__shimmer"></div>';
        if (rarity === 'legendary' || rarity === 'cosmic') html += '<div class="auo__rotating-border"></div>';

        var labelText = rarity === 'cosmic' ? 'KOSMICZNE WYR\u00D3\u017BNIENIE!' : rarity === 'legendary' ? '\u26A1 LEGENDARNE OSI\u0104GNI\u0118CIE!'
            : rarity === 'epic' ? '\uD83D\uDD2E Epickie osi\u0105gni\u0119cie!'
            : '\u2728 Nowe osi\u0105gni\u0119cie!';
        html += '<div class="auo__label">' + labelText + '</div>';

        html += '<div class="auo__icon-wrap">';
        if (rarity === 'rare') html += '<div class="auo__ring auo__ring--1"></div>';
        if (rarity === 'epic' || rarity === 'legendary' || rarity === 'cosmic') {
            html += '<div class="auo__ring auo__ring--1"></div><div class="auo__ring auo__ring--2"></div>';
        }
        if (rarity === 'legendary' || rarity === 'cosmic') html += '<div class="auo__ring auo__ring--3"></div>';
        if (rarity === 'cosmic') html += '<div class="auo__ring auo__ring--4"></div>';
        if (iconSrc && (rarity === 'legendary' || rarity === 'cosmic')) {
            // 3D coin with fake thickness
            html += '<div class="auo__coin">';
            html += '<div class="auo__coin-front"><img src="' + iconSrc + '" alt="' + a.name + '"><div class="auo__coin-shine"></div><div class="auo__coin-shine auo__coin-shine--2"></div></div>';
            for (var ci = 1; ci <= 6; ci++) {
                html += '<div class="auo__coin-edge" style="transform:translateZ(' + (-ci) + 'px)"></div>';
            }
            html += '<div class="auo__coin-back"><img src="' + iconSrc + '" alt=""></div>';
            html += '</div>';
        } else {
            var iconClass = iconSrc ? 'auo__icon auo__icon--has-image' : 'auo__icon';
            html += '<div class="' + iconClass + '">' + iconHTML + '</div>';
        }
        html += '</div>';

        html += '<div class="auo__name">' + a.name + '</div>';
        html += '<div class="auo__desc">' + a.description + '</div>';
        html += '<div class="auo__rarity">' + (rarity === 'legendary' ? '\u2605' : '\u2726') + ' ' + cfg.label + '</div>';
        if (percentText) html += '<div class="auo__percent">' + percentText + '</div>';

        html += '<div class="auo__actions">';
        html += '<button class="auo__btn auo__btn--share">\uD83D\uDCE4 Udost\u0119pnij</button>';
        html += '<button class="auo__btn auo__btn--close">Zamknij</button>';
        html += '</div></div>';

        overlay.innerHTML = html;
        return overlay;
    }

    /* ═══════════════════════════════════════════
       ANIMATION SEQUENCES
       ═══════════════════════════════════════════ */
    function startSequence(overlay, a, rarity, cfg) {
        switch (rarity) {
            case 'cosmic':
                // Cosmic — 4 phases, dłuższe i intensywniejsze niż legendary (~2400ms)
                requestAnimationFrame(function() { overlay.classList.add('auo--active'); });
                setTimeout(function() { overlay.classList.add('auo--phase1'); }, 600);   // beam grow + supernova rise
                setTimeout(function() { overlay.classList.add('auo--phase2'); }, 1200);  // supernova flash + beam expand + multi shockwaves
                setTimeout(function() { overlay.classList.add('auo--phase3'); }, 1800);  // godray + particles + orbit + dust + shooting stars
                setTimeout(function() { overlay.classList.add('auo--phase4'); }, 2400);  // rotating border + card materialize
                break;

            case 'legendary':
                requestAnimationFrame(function() { overlay.classList.add('auo--active'); });
                setTimeout(function() { overlay.classList.add('auo--phase1'); }, 800);
                setTimeout(function() { overlay.classList.add('auo--phase2'); }, 1600);
                setTimeout(function() { overlay.classList.add('auo--phase3'); }, 1900);
                break;

            case 'epic':
                requestAnimationFrame(function() { overlay.classList.add('auo--active'); });
                setTimeout(function() { overlay.classList.add('auo--reveal'); }, 400);
                break;

            case 'rare':
                requestAnimationFrame(function() { overlay.classList.add('auo--active'); });
                setTimeout(function() { overlay.classList.add('auo--flash-fire'); }, 100);
                setTimeout(function() { overlay.classList.add('auo--reveal'); }, 250);
                break;

            default:
                requestAnimationFrame(function() {
                    overlay.classList.add('auo--active');
                    overlay.classList.add('auo--reveal');
                });
                break;
        }
    }

    /* ═══════════════════════════════════════════
       EVENTS + CLOSE
       ═══════════════════════════════════════════ */
    function bindEvents(overlay, a, cfg) {
        overlay.querySelector('.auo__btn--close').addEventListener('click', function() {
            closeOverlay(overlay, [a.id]);
        });
        var shareBtn = overlay.querySelector('.auo__btn--share');
        if (shareBtn) {
            shareBtn.addEventListener('click', function() {
                closeOverlay(overlay, [a.id]);
                window.location.href = '/achievements?share=' + a.id;
            });
        }
        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) closeOverlay(overlay, [a.id]);
        });
    }

    function closeOverlay(overlay, ids) {
        if (autoDismissTimer) { clearTimeout(autoDismissTimer); autoDismissTimer = null; }
        overlay.classList.add('auo--closing');

        fetch('/achievements/api/mark-seen', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ achievement_ids: ids })
        }).catch(function() {});

        sessionStorage.removeItem('achievements_last_check');

        setTimeout(function() {
            overlay.remove();
            prepared.shift(); // remove the one we just closed
            if (prepared.length) {
                // Next overlay is already in DOM and warmed up — activate immediately
                requestAnimationFrame(function() {
                    activateNext();
                });
            } else {
                isShowing = false;
            }
        }, 500);
    }

    function getCSRFToken() {
        var m = document.querySelector('meta[name="csrf-token"]');
        return m ? m.getAttribute('content') : '';
    }

    /* ═══════════════════════════════════════════
       HELPERS
       ═══════════════════════════════════════════ */
    function pColors(r) {
        return {
            cosmic: ['#C084FC','#A855F7','#8B5CF6','#FFFFFF','#FFD700','#00D4FF','#FF80FF'],
            legendary: ['#FFD700','#FFCC44','#FFA500','#FFF4CC','#FFE066'],
            epic: ['#C080FF','#A855F7','#8B5CF6','#f093fb','#D8B4FE'],
            rare: ['#60B0FF','#93C5FD','#3B82F6','#BFDBFE','#2563EB'],
            common: ['#9CA3AF','#D1D5DB','#6B7280']
        }[r] || ['#9CA3AF'];
    }

    function cColors(r) {
        return {
            cosmic: ['#C084FC','#A855F7','#FFFFFF','#FFD700','#00D4FF','#FF80FF'],
            legendary: ['#FFD700','#FFCC44','#FFF','#FFA500','#FFE066','#FFFAF0'],
            epic: ['#C080FF','#f093fb','#f5576c','#FFD700','#60B0FF'],
            rare: ['#60B0FF','#93C5FD','#3B82F6']
        }[r] || ['#ccc'];
    }

    /* ═══════════════════════════════════════════
       CSS INJECTION
       ═══════════════════════════════════════════ */
    function injectCSS() {
        if (cssReady) return;
        cssReady = true;
        var s = document.createElement('style');
        s.id = 'auo-css';
        s.textContent = getCSS();
        document.head.appendChild(s);
    }

    function getCSS() { return [

    /* ============ BASE OVERLAY ============ */
    '.auo{position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;opacity:0;backdrop-filter:blur(0px);-webkit-backdrop-filter:blur(0px);transition:opacity 0.5s ease,backdrop-filter 0.5s ease,-webkit-backdrop-filter 0.5s ease;pointer-events:none;overflow:hidden}',
    '.auo--common.auo--active{opacity:1;pointer-events:auto;backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px)}',
    '.auo--rare.auo--active{opacity:1;pointer-events:auto;backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px)}',
    '.auo--epic.auo--active{opacity:1;pointer-events:auto;backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}',
    '.auo--legendary.auo--active{opacity:1;pointer-events:auto;backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px)}',
    '.auo.auo--closing{opacity:0;backdrop-filter:blur(0px);-webkit-backdrop-filter:blur(0px);transition:opacity 0.5s ease,backdrop-filter 0.5s ease,-webkit-backdrop-filter 0.5s ease;pointer-events:none}',

    /* Dark tint per rarity (no blur here — blur is on .auo itself) */
    '.auo--common::before{content:"";position:absolute;inset:0;background:rgba(10,10,15,0.45)}',
    '.auo--rare::before{content:"";position:absolute;inset:0;background:rgba(5,10,25,0.6)}',
    '.auo--epic::before{content:"";position:absolute;inset:0;background:rgba(10,5,20,0.7)}',
    '.auo--legendary::before{content:"";position:absolute;inset:0;background:rgba(12,8,0,0.75)}',

    /* Ambient glow */
    '.auo::after{content:"";position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);border-radius:50%;pointer-events:none;z-index:1}',
    '.auo--common::after{width:400px;height:400px;background:radial-gradient(circle,rgba(160,160,160,0.15) 0%,transparent 70%);animation:auo-gpulse 3s ease-in-out infinite}',
    '.auo--rare::after{width:550px;height:550px;background:radial-gradient(circle,rgba(80,160,255,0.25) 0%,rgba(80,160,255,0.1) 30%,transparent 70%);animation:auo-gpulse 3s ease-in-out infinite}',
    '.auo--epic::after{width:650px;height:650px;background:radial-gradient(circle,rgba(140,60,255,0.35) 0%,rgba(240,147,251,0.15) 25%,rgba(245,87,108,0.08) 45%,transparent 70%);animation:auo-gpulse 4s ease-in-out infinite}',
    '.auo--legendary::after{width:800px;height:800px;background:radial-gradient(circle,rgba(255,200,50,0.45) 0%,rgba(255,180,50,0.2) 25%,rgba(255,150,50,0.08) 45%,transparent 70%);opacity:0;transform:translate(-50%,-50%) scale(0.1)}',
    '.auo--legendary.auo--phase1::after,.auo--legendary.auo--phase2::after,.auo--legendary.auo--phase3::after{animation:auo-glow-leg-in 0.4s ease-out forwards,auo-gpulse 3s ease-in-out 0.4s infinite}',
    '@keyframes auo-glow-leg-in{0%{opacity:0;transform:translate(-50%,-50%) scale(0.1)}100%{opacity:1;transform:translate(-50%,-50%) scale(1)}}',
    '@keyframes auo-gpulse{0%,100%{transform:translate(-50%,-50%) scale(1);opacity:0.8}50%{transform:translate(-50%,-50%) scale(1.12);opacity:1}}',

    /* GPU layer hints for key animated elements */
    '.auo__card{will-change:transform,opacity,filter}',
    '.auo__shockwave{will-change:transform,opacity}',
    '.auo__flash{will-change:transform,opacity}',
    '.auo__beam{will-change:width,opacity,filter}',

    /* ============ FLASH (Rare) ============ */
    '.auo__flash{position:absolute;inset:0;background:radial-gradient(circle at 50% 50%,rgba(255,255,255,0.9) 0%,rgba(100,180,255,0.4) 40%,transparent 70%);opacity:0;z-index:5;pointer-events:none}',
    '.auo--flash-fire .auo__flash{animation:auo-flash 1s ease-out forwards}',
    '@keyframes auo-flash{0%{opacity:0;transform:scale(0.3)}30%{opacity:1;transform:scale(1.2)}100%{opacity:0;transform:scale(2.2)}}',

    /* ============ BEAM (Legendary) ============ */
    '.auo__beam{position:absolute;top:50%;left:50%;width:4px;height:0;transform:translate(-50%,-50%);background:linear-gradient(to bottom,rgba(255,215,0,0) 0%,rgba(255,215,0,0.8) 30%,rgba(255,200,50,1) 50%,rgba(255,215,0,0.8) 70%,rgba(255,215,0,0) 100%);opacity:0;z-index:3;pointer-events:none;filter:blur(2px);box-shadow:0 0 30px rgba(255,215,0,0.6),0 0 60px rgba(255,200,50,0.3)}',
    '.auo--phase1 .auo__beam{animation:auo-beam-grow 0.8s ease-in-out 0.15s forwards}',
    '.auo--phase2 .auo__beam{height:120%;opacity:1;animation:auo-beam-expand 0.6s ease-out forwards}',
    '@keyframes auo-beam-grow{0%{opacity:0;height:0}15%{opacity:1;height:5%}100%{opacity:1;height:120%;filter:blur(3px);box-shadow:0 0 40px rgba(255,215,0,0.8),0 0 80px rgba(255,200,50,0.5)}}',
    '@keyframes auo-beam-expand{0%{width:6px;opacity:1}100%{width:200px;opacity:0;filter:blur(30px)}}',

    /* ============ GOD RAY (Legendary) ============ */
    '.auo__godray{position:absolute;top:0;left:50%;transform:translateX(-50%);width:300px;height:60%;background:linear-gradient(to bottom,rgba(255,215,0,0.15) 0%,rgba(255,215,0,0.05) 50%,transparent 100%);clip-path:polygon(40% 0%,60% 0%,75% 100%,25% 100%);opacity:0;z-index:2;pointer-events:none}',
    '.auo--phase3 .auo__godray{animation:auo-godray-in 1s ease-out forwards}',
    '@keyframes auo-godray-in{0%{opacity:0}100%{opacity:1}}',

    /* ============ SHOCKWAVE ============ */
    '.auo__shockwave{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%) scale(0);width:400px;height:400px;border-radius:50%;border:2px solid;opacity:0;z-index:4;pointer-events:none}',
    '.auo--epic .auo__shockwave{border-color:rgba(180,80,255,0.6);box-shadow:0 0 20px rgba(180,80,255,0.3),inset 0 0 20px rgba(180,80,255,0.1)}',
    '.auo--legendary .auo__shockwave{border-color:rgba(255,200,50,0.7);box-shadow:0 0 30px rgba(255,200,50,0.4),inset 0 0 30px rgba(255,200,50,0.15)}',
    '.auo--epic.auo--reveal .auo__shockwave{animation:auo-shockwave 1s ease-out forwards;animation-delay:var(--sw-delay,0s)}',
    '.auo--legendary.auo--phase2 .auo__shockwave{animation:auo-shockwave 1s ease-out forwards;animation-delay:var(--sw-delay,0s)}',
    '@keyframes auo-shockwave{0%{transform:translate(-50%,-50%) scale(0);opacity:0.9}100%{transform:translate(-50%,-50%) scale(2.5);opacity:0}}',

    /* ============ LIGHT RAYS ============ */
    '.auo__rays{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:600px;height:600px;pointer-events:none;z-index:2;opacity:0;transition:opacity 0.5s ease}',
    '.auo--rare.auo--reveal .auo__rays,.auo--epic.auo--reveal .auo__rays{opacity:1}',
    '.auo--legendary.auo--phase3 .auo__rays{opacity:1}',
    '.auo__ray{position:absolute;top:50%;left:50%;width:2px;height:250px;transform-origin:top center;animation:auo-ray-fade 3s ease-in-out infinite;opacity:0.3}',
    '.auo--rare .auo__ray{background:linear-gradient(to bottom,rgba(80,160,255,0.25),transparent);height:200px}',
    '.auo--epic .auo__ray{background:linear-gradient(to bottom,rgba(180,80,255,0.3),rgba(240,147,251,0.1),transparent)}',
    '.auo--legendary .auo__ray{background:linear-gradient(to bottom,rgba(255,200,50,0.35),rgba(255,180,50,0.1),transparent)}',
    '@keyframes auo-ray-fade{0%,100%{opacity:0.3}50%{opacity:0.9}}',

    /* ============ PARTICLES ============ */
    '.auo__particles{position:absolute;inset:0;pointer-events:none;z-index:3;opacity:0;transition:opacity 0.7s ease}',
    '.auo--rare.auo--reveal .auo__particles,.auo--epic.auo--reveal .auo__particles{opacity:1}',
    '.auo--legendary.auo--phase2 .auo__particles--g1,.auo--legendary.auo--phase3 .auo__particles--g1{opacity:1}',
    '.auo--legendary.auo--phase2 .auo__particles--g2,.auo--legendary.auo--phase3 .auo__particles--g2{opacity:1;transition-delay:0.3s}',
    '.auo--legendary.auo--phase2 .auo__particles--g3,.auo--legendary.auo--phase3 .auo__particles--g3{opacity:1;transition-delay:0.6s}',
    '.auo__particle{position:absolute;border-radius:50%;animation:auo-float-up linear infinite}',
    '@keyframes auo-float-up{0%{opacity:0;transform:translateY(0) scale(0)}10%{opacity:1;transform:translateY(-15px) scale(1)}85%{opacity:0.6}100%{opacity:0;transform:translateY(-350px) scale(0.2)}}',

    /* ============ CONFETTI ============ */
    '.auo__confetti{position:absolute;inset:0;pointer-events:none;z-index:3;overflow:hidden;opacity:0;transition:opacity 0.3s ease}',
    '.auo--epic.auo--reveal .auo__confetti{opacity:1}',
    '.auo__confetti-piece{position:absolute;top:-10px;animation:auo-confetti-drop linear forwards}',
    '@keyframes auo-confetti-drop{0%{opacity:1;transform:translateY(0) rotate(0deg)}80%{opacity:0.8}100%{opacity:0;transform:translateY(105vh) rotate(720deg) scale(0.3)}}',

    /* ============ ELECTRIC SPARKS (Epic) ============ */
    '.auo__sparks{position:absolute;top:50%;left:50%;width:0;height:0;z-index:4;pointer-events:none;opacity:0;transition:opacity 0.3s ease}',
    '.auo--epic.auo--reveal .auo__sparks{opacity:1}',
    '.auo__spark{position:absolute;width:30px;height:2px;background:linear-gradient(90deg,rgba(180,80,255,0.9),rgba(240,147,251,0.6),transparent);transform-origin:left center;transform:rotate(var(--spark-angle,0deg));animation:auo-spark ease-out infinite;border-radius:1px;box-shadow:0 0 8px rgba(180,80,255,0.5)}',
    '@keyframes auo-spark{0%{opacity:0;width:0}20%{opacity:1;width:30px}60%{opacity:0.8;width:20px;transform:rotate(var(--spark-angle)) translateX(var(--spark-dist))}100%{opacity:0;width:0;transform:rotate(var(--spark-angle)) translateX(calc(var(--spark-dist) * 1.5))}}',

    /* ============ ORBITING DOTS (Legendary) ============ */
    '.auo__orbit{position:absolute;top:50%;left:50%;width:0;height:0;z-index:5;pointer-events:none;opacity:0;transition:opacity 0.8s ease}',
    '.auo--legendary.auo--phase3 .auo__orbit{opacity:1}',
    '.auo__orbit-wrap{position:absolute;top:0;left:0;width:0;height:0;animation:auo-spin linear infinite}',
    '@keyframes auo-spin{to{transform:rotate(360deg)}}',
    '.auo__orbit-dot{position:absolute;top:-1.5px;left:0;border-radius:50%;background:rgba(255,200,50,0.7);box-shadow:0 0 8px rgba(255,200,50,0.5),0 0 2px rgba(255,255,255,0.3)}',

    /* ============ FLOATING DUST (Legendary) ============ */
    '.auo__dust{position:absolute;inset:0;z-index:2;pointer-events:none;opacity:0;transition:opacity 1s ease}',
    '.auo--legendary.auo--phase3 .auo__dust{opacity:1}',
    '.auo__dust-mote{position:absolute;border-radius:50%;background:rgba(255,215,0,0.5);box-shadow:0 0 4px rgba(255,215,0,0.3);animation:auo-dust-float ease-in-out infinite}',
    '@keyframes auo-dust-float{0%,100%{transform:translate(0,0);opacity:0}25%{opacity:0.8;transform:translate(10px,-15px)}50%{opacity:0.5;transform:translate(-5px,-30px)}75%{opacity:0.7;transform:translate(8px,-20px)}}',

    /* ============ CARD ============ */
    '.auo__card{position:relative;z-index:10;max-width:380px;width:90%;border-radius:24px;padding:44px 32px 32px;text-align:center;opacity:0;transform:scale(0.8) translateY(30px)}',

    /* Common card */
    '.auo--common .auo__card{background:rgba(20,14,30,0.88);border:1px solid rgba(160,160,160,0.2);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);box-shadow:0 0 40px rgba(0,0,0,0.3)}',
    '.auo--common.auo--reveal .auo__card{animation:auo-card-pop 0.6s cubic-bezier(0.34,1.56,0.64,1) forwards}',
    '@keyframes auo-card-pop{0%{opacity:0;transform:scale(0.85) translateY(40px)}100%{opacity:1;transform:scale(1) translateY(0)}}',

    /* Rare card */
    '.auo--rare .auo__card{background:rgba(10,18,40,0.9);border:1px solid rgba(80,160,255,0.25);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);box-shadow:0 0 60px rgba(80,160,255,0.15),0 0 120px rgba(80,160,255,0.05)}',
    '.auo--rare.auo--reveal .auo__card{animation:auo-card-crystal 0.7s cubic-bezier(0.16,1,0.3,1) forwards}',
    '@keyframes auo-card-crystal{0%{opacity:0;transform:scale(0.6);filter:blur(10px) brightness(2)}40%{filter:blur(2px) brightness(1.3)}100%{opacity:1;transform:scale(1);filter:blur(0) brightness(1)}}',

    /* Epic card */
    '.auo--epic .auo__card{background:rgba(15,8,30,0.92);border:1px solid rgba(180,80,255,0.3);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);box-shadow:0 0 80px rgba(140,60,255,0.2),0 0 160px rgba(240,147,251,0.08)}',
    '.auo--epic.auo--reveal .auo__card{animation:auo-card-explode 0.8s cubic-bezier(0.16,1,0.3,1) 0.3s forwards}',
    '@keyframes auo-card-explode{0%{opacity:0;transform:scale(0.3) rotate(-3deg);filter:brightness(3) blur(4px)}30%{opacity:1;filter:brightness(1.5) blur(0)}100%{opacity:1;transform:scale(1) rotate(0deg);filter:brightness(1) blur(0)}}',

    /* Legendary card */
    '.auo--legendary .auo__card{background:rgba(20,15,5,0.93);border:none;backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);box-shadow:0 0 100px rgba(255,200,50,0.2),0 0 200px rgba(255,180,50,0.08)}',
    '.auo--legendary.auo--phase3 .auo__card{animation:auo-card-materialize 1s ease-out forwards}',
    '@keyframes auo-card-materialize{0%{opacity:0;transform:scale(0.7) translateY(20px);filter:brightness(3) blur(6px)}30%{opacity:1;filter:brightness(1.8) blur(2px)}60%{filter:brightness(1.2) blur(0)}100%{opacity:1;transform:scale(1) translateY(0);filter:brightness(1) blur(0)}}',

    /* Card exit */
    '.auo--closing .auo__card{animation:auo-card-out 0.4s ease-in forwards !important}',
    '@keyframes auo-card-out{0%{opacity:1;transform:scale(1)}100%{opacity:0;transform:scale(0.9) translateY(15px)}}',

    /* ============ SHIMMER ============ */
    '.auo__shimmer{position:absolute;inset:0;border-radius:24px;overflow:hidden;pointer-events:none;z-index:1}',
    '.auo__shimmer::after{content:"";position:absolute;top:-50%;left:-100%;width:60%;height:200%;pointer-events:none}',
    '.auo--rare .auo__shimmer::after{background:linear-gradient(105deg,transparent 40%,rgba(100,180,255,0.12) 45%,rgba(100,180,255,0.2) 50%,rgba(100,180,255,0.12) 55%,transparent 60%);animation:auo-shimmer 4s ease-in-out 1.5s infinite}',
    '.auo--epic .auo__shimmer::after{background:linear-gradient(105deg,transparent 40%,rgba(180,100,255,0.12) 45%,rgba(180,100,255,0.22) 50%,rgba(180,100,255,0.12) 55%,transparent 60%);animation:auo-shimmer 3s ease-in-out 1.5s infinite}',
    '.auo--legendary .auo__shimmer::after{background:linear-gradient(105deg,transparent 38%,rgba(255,215,0,0.1) 43%,rgba(255,215,0,0.22) 50%,rgba(255,215,0,0.1) 57%,transparent 62%);animation:auo-shimmer 3.5s ease-in-out 2.5s infinite}',
    '@keyframes auo-shimmer{0%,100%{left:-100%;opacity:0}10%{opacity:1}50%{left:150%;opacity:1}60%,100%{left:150%;opacity:0}}',

    /* ============ ROTATING BORDER (Legendary) ============ */
    '@property --auo-ba{syntax:"<angle>";initial-value:0deg;inherits:false}',
    '.auo__rotating-border{position:absolute;inset:-2px;border-radius:26px;padding:2px;background:conic-gradient(from var(--auo-ba),transparent 0%,rgba(255,200,50,0.9) 8%,rgba(255,215,0,0.6) 12%,transparent 20%,transparent 50%,rgba(255,180,50,0.9) 58%,rgba(255,215,0,0.6) 62%,transparent 70%);-webkit-mask:linear-gradient(#fff 0 0) content-box,linear-gradient(#fff 0 0);-webkit-mask-composite:xor;mask:linear-gradient(#fff 0 0) content-box,linear-gradient(#fff 0 0);mask-composite:exclude;pointer-events:none;z-index:0;opacity:0;transition:opacity 0.5s ease}',
    '.auo--legendary.auo--phase3 .auo__rotating-border{opacity:1;animation:auo-brot 3s linear infinite}',
    '@keyframes auo-brot{to{--auo-ba:360deg}}',

    /* ============ CARD CONTENT ============ */
    '.auo__label{font-size:11px;text-transform:uppercase;letter-spacing:3px;margin-bottom:24px;opacity:0;font-weight:600;position:relative;z-index:2}',
    '.auo--common .auo__label{color:rgba(160,160,160,0.7);letter-spacing:2px}',
    '.auo--rare .auo__label{color:rgba(100,180,255,0.7)}',
    '.auo--epic .auo__label{color:rgba(200,130,255,0.8)}',
    '.auo--legendary .auo__label{color:rgba(255,215,0,0.9);letter-spacing:4px;font-size:12px}',

    '.auo--common.auo--reveal .auo__label{animation:auo-tin 0.5s ease 0.4s both}',
    '.auo--rare.auo--reveal .auo__label{animation:auo-tin 0.5s ease 0.3s both}',
    '.auo--epic.auo--reveal .auo__label{animation:auo-tin 0.5s ease 0.6s both}',
    '.auo--legendary.auo--phase3 .auo__label{animation:auo-tin 0.5s ease 0.3s both}',

    /* Icon wrapper */
    '.auo__icon-wrap{position:relative;width:120px;height:120px;margin:0 auto 20px;opacity:0}',
    '.auo--common.auo--reveal .auo__icon-wrap{animation:auo-ipop 0.7s cubic-bezier(0.34,1.56,0.64,1) 0.2s both}',
    '.auo--rare.auo--reveal .auo__icon-wrap{animation:auo-icrystal 0.8s cubic-bezier(0.16,1,0.3,1) 0.1s both}',
    '.auo--epic.auo--reveal .auo__icon-wrap{animation:auo-iexplode 0.8s cubic-bezier(0.16,1,0.3,1) 0.5s both}',
    '.auo--legendary.auo--phase3 .auo__icon-wrap{animation:auo-iburst 1s cubic-bezier(0.16,1,0.3,1) 0.2s both}',

    '@keyframes auo-ipop{0%{opacity:0;transform:scale(0)}100%{opacity:1;transform:scale(1)}}',
    '@keyframes auo-icrystal{0%{opacity:0;transform:scale(0.3) rotate(-15deg);filter:blur(8px)}50%{filter:blur(2px)}100%{opacity:1;transform:scale(1) rotate(0deg);filter:blur(0)}}',
    '@keyframes auo-iexplode{0%{opacity:0;transform:scale(0.1) rotate(180deg);filter:brightness(4) blur(4px)}40%{opacity:1;filter:brightness(1.5) blur(0)}100%{opacity:1;transform:scale(1) rotate(0deg);filter:brightness(1)}}',
    '@keyframes auo-iburst{0%{opacity:0;transform:scale(0.2);filter:brightness(5) blur(8px)}30%{opacity:1;transform:scale(1.15);filter:brightness(2) blur(2px)}50%{transform:scale(0.95)}100%{opacity:1;transform:scale(1);filter:brightness(1) blur(0)}}',

    /* Icon circle */
    '.auo__icon{width:100%;height:100%;border-radius:50%;display:flex;align-items:center;justify-content:center;position:relative;z-index:2}',
    '.auo--common .auo__icon{background:linear-gradient(160deg,rgba(160,160,160,0.12),rgba(160,160,160,0.04));border:3px solid rgba(160,160,160,0.3);box-shadow:0 0 30px rgba(160,160,160,0.1)}',
    '.auo--rare .auo__icon{background:linear-gradient(160deg,rgba(80,160,255,0.15),rgba(80,160,255,0.05));border:3px solid rgba(80,160,255,0.35);box-shadow:0 0 40px rgba(80,160,255,0.2);animation:auo-iglow-rare 3s ease-in-out infinite}',
    '.auo--epic .auo__icon{background:linear-gradient(160deg,rgba(180,80,255,0.15),rgba(240,147,251,0.05));border:3px solid rgba(180,80,255,0.4);box-shadow:0 0 50px rgba(180,80,255,0.25);animation:auo-iglow-epic 2.5s ease-in-out infinite}',
    '.auo--legendary .auo__icon{background:linear-gradient(160deg,rgba(255,200,50,0.2),rgba(255,180,50,0.05));border:3px solid rgba(255,200,50,0.5);box-shadow:0 0 60px rgba(255,200,50,0.3),0 0 120px rgba(255,200,50,0.1);animation:auo-iglow-leg 2s ease-in-out infinite}',

    '@keyframes auo-iglow-rare{0%,100%{box-shadow:0 0 40px rgba(80,160,255,0.2)}50%{box-shadow:0 0 60px rgba(80,160,255,0.35)}}',
    '@keyframes auo-iglow-epic{0%,100%{box-shadow:0 0 50px rgba(180,80,255,0.25)}50%{box-shadow:0 0 70px rgba(180,80,255,0.4),0 0 120px rgba(240,147,251,0.15)}}',
    '@keyframes auo-iglow-leg{0%,100%{box-shadow:0 0 60px rgba(255,200,50,0.3),0 0 120px rgba(255,200,50,0.1)}50%{box-shadow:0 0 80px rgba(255,200,50,0.5),0 0 150px rgba(255,200,50,0.2)}}',

    '.auo__icon img{width:64px;height:64px;object-fit:contain}',
    '.auo__icon--has-image{border:none;background:transparent;box-shadow:none}',
    '.auo__icon--has-image img{width:105px;height:105px}',
    '.auo__icon-emoji{font-size:56px;line-height:1}',

    /* 3D Coin */
    '.auo__icon-wrap{perspective:800px}',
    '.auo__coin{width:105px;height:105px;position:absolute;top:50%;left:50%;margin:-52.5px 0 0 -52.5px;transform-style:preserve-3d;z-index:2}',
    '.auo__coin-front,.auo__coin-back{position:absolute;inset:0;border-radius:50%;backface-visibility:hidden;display:flex;align-items:center;justify-content:center;overflow:hidden}',
    '.auo__coin-front img,.auo__coin-back img{width:100%;height:100%;object-fit:contain}',
    '.auo__coin-back{transform:rotateY(180deg)}',
    '.auo__coin-edge{position:absolute;inset:0;border-radius:50%;background:linear-gradient(160deg,#D4A017,#C4922A,#E8B830);backface-visibility:hidden;border:1px solid rgba(180,140,20,0.4)}',
    '.auo__coin-shine{position:absolute;inset:0;border-radius:50%;background:linear-gradient(105deg,transparent 30%,rgba(255,255,255,0.6) 45%,rgba(255,255,255,0) 55%);opacity:0;pointer-events:none;animation:auo-coin-blast 3s ease-in-out 1s infinite}',
    '.auo__coin-shine--2{animation-delay:1.15s !important;background:linear-gradient(105deg,transparent 40%,rgba(255,255,255,0.35) 52%,rgba(255,255,255,0) 60%)}',
    '@keyframes auo-coin-blast{0%{opacity:0;transform:translateX(-80%)}12%{opacity:1}23%{opacity:0;transform:translateX(80%)}100%{opacity:0;transform:translateX(80%)}}',
    '.auo--legendary.auo--phase3 .auo__coin{animation:auo-coin-spin 3.5s ease-in-out 0s both}',
    '@keyframes auo-coin-spin{0%{transform:rotateY(0deg) rotateX(6deg)}70%{transform:rotateY(792deg) rotateX(1deg)}100%{transform:rotateY(720deg) rotateX(0deg)}}',

    /* Spinning rings */
    '.auo__ring{position:absolute;border-radius:50%;border:2px solid transparent;pointer-events:none}',
    '.auo__ring--1{inset:-6px;opacity:0.5}',
    '.auo__ring--2{inset:-12px;opacity:0.3}',
    '.auo__ring--3{inset:-18px;opacity:0.2}',
    '.auo--rare .auo__ring--1{border-top-color:rgba(80,160,255,0.5);border-right-color:rgba(80,160,255,0.2);animation:auo-rspin 3s linear infinite}',
    '.auo--epic .auo__ring--1{border-top-color:rgba(180,80,255,0.6);border-right-color:rgba(240,147,251,0.3);animation:auo-rspin 2.5s linear infinite}',
    '.auo--epic .auo__ring--2{border-bottom-color:rgba(180,80,255,0.3);border-left-color:rgba(240,147,251,0.15);animation:auo-rspin 4s linear infinite reverse}',
    '.auo--legendary .auo__ring--1{border-top-color:rgba(255,200,50,0.7);border-right-color:rgba(255,180,50,0.3);animation:auo-rspin 2s linear infinite}',
    '.auo--legendary .auo__ring--2{border-bottom-color:rgba(255,200,50,0.4);border-left-color:rgba(255,180,50,0.2);animation:auo-rspin 3.5s linear infinite reverse}',
    '.auo--legendary .auo__ring--3{border-top-color:rgba(255,215,0,0.25);border-bottom-color:rgba(255,180,50,0.15);animation:auo-rspin 5s linear infinite}',
    '@keyframes auo-rspin{to{transform:rotate(360deg)}}',

    /* Text */
    '.auo__name{font-size:24px;font-weight:800;color:#fff;margin-bottom:8px;opacity:0;position:relative;z-index:2}',
    '.auo--legendary .auo__name{font-size:26px;text-shadow:0 0 30px rgba(255,200,50,0.4)}',
    '.auo--epic .auo__name{text-shadow:0 0 25px rgba(180,80,255,0.3)}',
    '.auo__desc{font-size:14px;color:rgba(255,255,255,0.5);margin-bottom:18px;line-height:1.5;opacity:0;position:relative;z-index:2}',
    '.auo__rarity{display:inline-flex;align-items:center;gap:5px;padding:5px 16px;border-radius:20px;font-size:12px;font-weight:700;margin-bottom:10px;opacity:0;position:relative;z-index:2}',
    '.auo--common .auo__rarity{background:rgba(160,160,160,0.15);color:#9CA3AF;border:1px solid rgba(160,160,160,0.2)}',
    '.auo--rare .auo__rarity{background:rgba(80,160,255,0.12);color:#60B0FF;border:1px solid rgba(80,160,255,0.25)}',
    '.auo--epic .auo__rarity{background:rgba(180,80,255,0.12);color:#C080FF;border:1px solid rgba(180,80,255,0.25)}',
    '.auo--legendary .auo__rarity{background:rgba(255,200,50,0.12);color:#FFCC44;border:1px solid rgba(255,200,50,0.3)}',
    '.auo__percent{font-size:12px;color:rgba(255,255,255,0.3);margin-bottom:24px;opacity:0;position:relative;z-index:2}',
    '.auo__actions{display:flex;gap:12px;justify-content:center;opacity:0;position:relative;z-index:2}',

    /* Stagger — Common */
    '.auo--common.auo--reveal .auo__name{animation:auo-tin 0.5s ease 0.5s both}',
    '.auo--common.auo--reveal .auo__desc{animation:auo-tin 0.5s ease 0.6s both}',
    '.auo--common.auo--reveal .auo__rarity{animation:auo-tin 0.5s ease 0.7s both}',
    '.auo--common.auo--reveal .auo__percent{animation:auo-tin 0.5s ease 0.75s both}',
    '.auo--common.auo--reveal .auo__actions{animation:auo-tin 0.5s ease 0.8s both}',

    /* Stagger — Rare */
    '.auo--rare.auo--reveal .auo__name{animation:auo-tin 0.5s ease 0.5s both}',
    '.auo--rare.auo--reveal .auo__desc{animation:auo-tin 0.5s ease 0.6s both}',
    '.auo--rare.auo--reveal .auo__rarity{animation:auo-tin 0.5s ease 0.7s both}',
    '.auo--rare.auo--reveal .auo__percent{animation:auo-tin 0.5s ease 0.75s both}',
    '.auo--rare.auo--reveal .auo__actions{animation:auo-tin 0.5s ease 0.8s both}',

    /* Stagger — Epic */
    '.auo--epic.auo--reveal .auo__name{animation:auo-tin 0.5s ease 0.9s both}',
    '.auo--epic.auo--reveal .auo__desc{animation:auo-tin 0.5s ease 1.0s both}',
    '.auo--epic.auo--reveal .auo__rarity{animation:auo-tin 0.5s ease 1.1s both}',
    '.auo--epic.auo--reveal .auo__percent{animation:auo-tin 0.5s ease 1.15s both}',
    '.auo--epic.auo--reveal .auo__actions{animation:auo-tin 0.5s ease 1.2s both}',

    /* Stagger — Legendary */
    '.auo--legendary.auo--phase3 .auo__name{animation:auo-tin 0.6s ease 0.6s both}',
    '.auo--legendary.auo--phase3 .auo__desc{animation:auo-tin 0.6s ease 0.75s both}',
    '.auo--legendary.auo--phase3 .auo__rarity{animation:auo-tin 0.6s ease 0.9s both}',
    '.auo--legendary.auo--phase3 .auo__percent{animation:auo-tin 0.6s ease 0.98s both}',
    '.auo--legendary.auo--phase3 .auo__actions{animation:auo-tin 0.6s ease 1.05s both}',

    '@keyframes auo-tin{0%{opacity:0;transform:translateY(12px)}100%{opacity:1;transform:translateY(0)}}',

    /* Buttons */
    '.auo__btn{padding:12px 24px;border-radius:14px;font-size:14px;font-weight:600;border:none;cursor:pointer;transition:all 0.3s ease}',
    '.auo__btn--share{color:#fff;box-shadow:0 4px 20px rgba(240,147,251,0.25)}',
    '.auo--common .auo__btn--share{background:linear-gradient(135deg,#9CA3AF,#6B7280);box-shadow:0 4px 16px rgba(160,160,160,0.2)}',
    '.auo--rare .auo__btn--share{background:linear-gradient(135deg,#60B0FF,#3B82F6);box-shadow:0 4px 20px rgba(80,160,255,0.25)}',
    '.auo--epic .auo__btn--share{background:linear-gradient(135deg,#C080FF,#8B5CF6);box-shadow:0 4px 20px rgba(180,80,255,0.25)}',
    '.auo--legendary .auo__btn--share{background:linear-gradient(135deg,#FFD700,#FF8C00);color:#1a1000;font-weight:800;box-shadow:0 4px 20px rgba(255,200,50,0.3)}',
    '.auo__btn--share:hover{transform:translateY(-2px) scale(1.03);filter:brightness(1.1)}',
    '.auo__btn--close{background:rgba(255,255,255,0.05);color:rgba(255,255,255,0.5);border:1px solid rgba(255,255,255,0.1)}',
    '.auo__btn--close:hover{background:rgba(255,255,255,0.1);border-color:rgba(255,255,255,0.2);color:rgba(255,255,255,0.8)}',

    /* ============ COSMIC RARITY (admin-grantable) ============ */
    /* Backdrop tint - głębsza czerń kosmosu */
    '.auo--cosmic::before{content:"";position:absolute;inset:0;background:radial-gradient(ellipse at 30% 20%,rgba(106,13,173,0.4) 0%,transparent 50%),radial-gradient(ellipse at 70% 80%,rgba(30,58,138,0.4) 0%,transparent 50%),rgba(2,0,15,0.85)}',
    /* Ambient glow - większy i intensywniejszy niż legendary */
    '.auo--cosmic::after{width:1000px;height:1000px;background:radial-gradient(circle,rgba(168,85,247,0.4) 0%,rgba(106,13,173,0.2) 25%,rgba(30,58,138,0.1) 45%,transparent 70%);opacity:0;transform:translate(-50%,-50%) scale(0.1)}',
    '.auo--cosmic.auo--phase1::after,.auo--cosmic.auo--phase2::after,.auo--cosmic.auo--phase3::after,.auo--cosmic.auo--phase4::after{animation:auo-glow-cosmic-in 0.5s ease-out forwards,auo-gpulse 3.5s ease-in-out 0.5s infinite}',
    '@keyframes auo-glow-cosmic-in{0%{opacity:0;transform:translate(-50%,-50%) scale(0.1)}100%{opacity:1;transform:translate(-50%,-50%) scale(1)}}',

    /* Active state - blur backdrop */
    '.auo--cosmic.auo--active{opacity:1;pointer-events:auto;backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px)}',

    /* === SUPERNOVA FLASH (cosmic exclusive) === */
    '.auo__supernova{position:absolute;top:50%;left:50%;width:8px;height:8px;border-radius:50%;background:white;transform:translate(-50%,-50%) scale(0);opacity:0;z-index:6;pointer-events:none;will-change:transform,opacity,box-shadow}',
    '.auo--cosmic.auo--phase2 .auo__supernova{animation:auo-supernova-burst 1.6s cubic-bezier(0.22,1,0.36,1) forwards}',
    '@keyframes auo-supernova-burst{0%{transform:translate(-50%,-50%) scale(0);opacity:0;box-shadow:0 0 0 0 rgba(255,255,255,1)}10%{transform:translate(-50%,-50%) scale(1);opacity:1;box-shadow:0 0 60px 30px rgba(255,255,255,0.9),0 0 120px 60px rgba(168,85,247,0.7),0 0 200px 100px rgba(30,58,138,0.5)}40%{opacity:0.9;box-shadow:0 0 200px 120px rgba(255,255,255,0.4),0 0 350px 200px rgba(168,85,247,0.3),0 0 500px 300px rgba(30,58,138,0.15)}100%{transform:translate(-50%,-50%) scale(1.5);opacity:0;box-shadow:0 0 0 0 transparent}}',

    /* === NEBULAE (cosmic exclusive) - 3 dryfujące mgławice w tle === */
    '.auo__nebulae{position:absolute;inset:0;z-index:1;pointer-events:none;opacity:0;transition:opacity 1s ease}',
    '.auo--cosmic.auo--active .auo__nebulae{opacity:1}',
    '.auo__nebula{position:absolute;border-radius:50%;filter:blur(60px);will-change:transform}',
    '.auo__nebula--purple{width:50%;height:50%;left:10%;top:10%;background:radial-gradient(circle,rgba(168,85,247,0.5),transparent 60%);animation:auo-nebula-drift-1 14s ease-in-out infinite alternate}',
    '.auo__nebula--blue{width:45%;height:45%;right:5%;bottom:5%;background:radial-gradient(circle,rgba(30,58,138,0.55),transparent 60%);animation:auo-nebula-drift-2 16s ease-in-out infinite alternate}',
    '.auo__nebula--pink{width:40%;height:40%;right:30%;top:50%;background:radial-gradient(circle,rgba(255,128,255,0.3),transparent 60%);animation:auo-nebula-drift-3 12s ease-in-out infinite alternate}',
    '@keyframes auo-nebula-drift-1{0%{transform:translate(0,0) scale(1)}100%{transform:translate(40px,30px) scale(1.25)}}',
    '@keyframes auo-nebula-drift-2{0%{transform:translate(0,0) scale(1)}100%{transform:translate(-50px,-30px) scale(1.2)}}',
    '@keyframes auo-nebula-drift-3{0%{transform:translate(0,0) scale(1)}100%{transform:translate(30px,-40px) scale(1.35)}}',

    /* === SHOOTING STARS (cosmic exclusive) === */
    '.auo__shooting-stars{position:absolute;inset:0;z-index:4;pointer-events:none;overflow:hidden}',
    '.auo__shooting-star{position:absolute;left:-150px;width:120px;height:2px;background:linear-gradient(90deg,transparent,white 60%,#c084fc);box-shadow:0 0 10px rgba(255,255,255,0.9),0 0 20px rgba(168,85,247,0.7);transform-origin:left center;transform:rotate(20deg);opacity:0;will-change:transform,opacity}',
    '.auo--cosmic.auo--phase3 .auo__shooting-star{animation:auo-shooting-cosmic 1.8s ease-out forwards}',
    '@keyframes auo-shooting-cosmic{0%{opacity:0;transform:translateX(0) translateY(0) rotate(20deg)}10%{opacity:1}90%{opacity:0.8}100%{opacity:0;transform:translateX(120vw) translateY(40vh) rotate(20deg)}}',

    /* === COSMIC BEAM === */
    '.auo--cosmic .auo__beam{background:linear-gradient(to bottom,rgba(168,85,247,0) 0%,rgba(168,85,247,0.85) 30%,rgba(255,255,255,1) 50%,rgba(168,85,247,0.85) 70%,rgba(168,85,247,0) 100%);box-shadow:0 0 30px rgba(168,85,247,0.6),0 0 60px rgba(106,13,173,0.4)}',
    '.auo--cosmic.auo--phase1 .auo__beam{animation:auo-beam-grow-cosmic 0.6s ease-in-out 0s forwards}',
    '.auo--cosmic.auo--phase2 .auo__beam{animation:auo-beam-expand-cosmic 0.8s ease-out forwards}',
    '@keyframes auo-beam-grow-cosmic{0%{opacity:0;height:0}15%{opacity:1;height:5%}100%{opacity:1;height:130%;filter:blur(3px);box-shadow:0 0 50px rgba(168,85,247,0.9),0 0 100px rgba(106,13,173,0.6)}}',
    '@keyframes auo-beam-expand-cosmic{0%{width:6px;opacity:1}100%{width:280px;opacity:0;filter:blur(40px)}}',

    /* === COSMIC GODRAY === */
    '.auo--cosmic .auo__godray{width:380px;background:linear-gradient(to bottom,rgba(168,85,247,0.2) 0%,rgba(168,85,247,0.08) 50%,transparent 100%)}',
    '.auo--cosmic.auo--phase3 .auo__godray{animation:auo-godray-in 1s ease-out forwards}',

    /* === COSMIC SHOCKWAVES === */
    '.auo--cosmic .auo__shockwave{border-color:rgba(168,85,247,0.7);box-shadow:0 0 30px rgba(168,85,247,0.5),inset 0 0 30px rgba(168,85,247,0.2)}',
    '.auo--cosmic.auo--phase2 .auo__shockwave{animation:auo-shockwave 1.2s ease-out forwards;animation-delay:var(--sw-delay,0s)}',

    /* === COSMIC RAYS === */
    '.auo--cosmic .auo__ray{background:linear-gradient(to bottom,rgba(168,85,247,0.45),rgba(106,13,173,0.15),transparent);height:280px}',
    '.auo--cosmic.auo--phase3 .auo__rays{opacity:1}',

    /* === COSMIC PARTICLES (3 grupy, staggered z phase2/3/4) === */
    '.auo--cosmic.auo--phase2 .auo__particles--g1,.auo--cosmic.auo--phase3 .auo__particles--g1,.auo--cosmic.auo--phase4 .auo__particles--g1{opacity:1}',
    '.auo--cosmic.auo--phase3 .auo__particles--g2,.auo--cosmic.auo--phase4 .auo__particles--g2{opacity:1;transition-delay:0.3s}',
    '.auo--cosmic.auo--phase4 .auo__particles--g3{opacity:1;transition-delay:0.6s}',

    /* === COSMIC ORBIT DOTS === */
    '.auo--cosmic.auo--phase3 .auo__orbit{opacity:1}',
    '.auo--cosmic .auo__orbit-dot{background:rgba(168,85,247,0.75);box-shadow:0 0 8px rgba(168,85,247,0.6),0 0 2px rgba(255,255,255,0.4)}',

    /* === COSMIC DUST === */
    '.auo--cosmic.auo--phase3 .auo__dust{opacity:1}',
    '.auo--cosmic .auo__dust-mote{background:rgba(192,132,252,0.6);box-shadow:0 0 4px rgba(168,85,247,0.4)}',

    /* === COSMIC CARD === */
    '.auo--cosmic .auo__card{background:linear-gradient(135deg,rgba(15,5,30,0.95) 0%,rgba(8,3,20,0.97) 100%);border:none;backdrop-filter:blur(28px);-webkit-backdrop-filter:blur(28px);box-shadow:0 0 120px rgba(168,85,247,0.3),0 0 240px rgba(106,13,173,0.15),inset 0 0 40px rgba(168,85,247,0.08)}',
    '.auo--cosmic.auo--phase4 .auo__card{animation:auo-card-cosmic-materialize 1.2s cubic-bezier(0.22,1,0.36,1) forwards}',
    '@keyframes auo-card-cosmic-materialize{0%{opacity:0;transform:scale(0.5) translateY(30px) rotateY(20deg);filter:brightness(4) blur(10px)}30%{opacity:1;transform:scale(1.18) translateY(-5px) rotateY(0deg);filter:brightness(2) blur(2px)}55%{transform:scale(0.95)}80%{transform:scale(1.04)}100%{opacity:1;transform:scale(1) translateY(0);filter:brightness(1) blur(0)}}',

    /* === COSMIC SHIMMER === */
    '.auo--cosmic .auo__shimmer::after{background:linear-gradient(105deg,transparent 35%,rgba(168,85,247,0.18) 42%,rgba(255,255,255,0.35) 50%,rgba(168,85,247,0.18) 58%,transparent 65%);animation:auo-shimmer 3s ease-in-out 2.8s infinite}',

    /* === COSMIC ROTATING BORDER === */
    '.auo--cosmic .auo__rotating-border{background:conic-gradient(from var(--auo-ba),transparent 0%,rgba(168,85,247,0.95) 6%,rgba(255,255,255,0.7) 10%,rgba(168,85,247,0.6) 14%,transparent 22%,transparent 50%,rgba(106,13,173,0.95) 56%,rgba(255,255,255,0.7) 60%,rgba(168,85,247,0.6) 64%,transparent 72%)}',
    '.auo--cosmic.auo--phase4 .auo__rotating-border{opacity:1;animation:auo-brot 2.5s linear infinite}',

    /* === COSMIC LABEL === */
    '.auo--cosmic .auo__label{color:rgba(192,132,252,0.95);letter-spacing:5px;font-size:13px;font-weight:700;text-shadow:0 0 20px rgba(168,85,247,0.6)}',
    '.auo--cosmic.auo--phase4 .auo__label{animation:auo-tin 0.6s ease 0.4s both}',

    /* === COSMIC ICON === */
    '.auo--cosmic .auo__icon{background:linear-gradient(160deg,rgba(168,85,247,0.25),rgba(30,58,138,0.1));border:3px solid rgba(168,85,247,0.6);box-shadow:0 0 70px rgba(168,85,247,0.4),0 0 140px rgba(106,13,173,0.2);animation:auo-iglow-cosmic 2.2s ease-in-out infinite}',
    '@keyframes auo-iglow-cosmic{0%,100%{box-shadow:0 0 70px rgba(168,85,247,0.4),0 0 140px rgba(106,13,173,0.2)}50%{box-shadow:0 0 100px rgba(168,85,247,0.7),0 0 200px rgba(168,85,247,0.3),0 0 300px rgba(255,128,255,0.15)}}',
    '.auo--cosmic.auo--phase4 .auo__icon-wrap{animation:auo-iburst-cosmic 1.2s cubic-bezier(0.16,1,0.3,1) 0.3s both}',
    '@keyframes auo-iburst-cosmic{0%{opacity:0;transform:scale(0.15) rotateY(180deg);filter:brightness(6) blur(12px)}25%{opacity:1;transform:scale(1.25) rotateY(20deg);filter:brightness(2.5) blur(3px)}50%{transform:scale(0.92)}75%{transform:scale(1.05)}100%{opacity:1;transform:scale(1) rotateY(0deg);filter:brightness(1) blur(0)}}',

    /* === COSMIC RINGS (4 rings) === */
    '.auo--cosmic .auo__ring--1{border-top-color:rgba(168,85,247,0.8);border-right-color:rgba(192,132,252,0.4);animation:auo-rspin 2s linear infinite}',
    '.auo--cosmic .auo__ring--2{border-bottom-color:rgba(106,13,173,0.5);border-left-color:rgba(255,128,255,0.3);animation:auo-rspin 3s linear infinite reverse}',
    '.auo--cosmic .auo__ring--3{border-top-color:rgba(255,255,255,0.35);border-bottom-color:rgba(168,85,247,0.2);animation:auo-rspin 4.5s linear infinite}',
    '.auo--cosmic .auo__ring--4{inset:-24px;opacity:0.15;border-right-color:rgba(0,212,255,0.4);border-left-color:rgba(255,128,255,0.25);animation:auo-rspin 6s linear infinite reverse}',

    /* === COSMIC NAME / RARITY / PERCENT / ACTIONS === */
    '.auo--cosmic .auo__name{font-size:28px;text-shadow:0 0 30px rgba(168,85,247,0.6),0 0 60px rgba(106,13,173,0.3)}',
    '.auo--cosmic .auo__rarity{background:linear-gradient(135deg,rgba(168,85,247,0.2),rgba(30,58,138,0.2));color:#C084FC;border:1px solid rgba(168,85,247,0.5);box-shadow:0 0 12px rgba(168,85,247,0.3)}',
    '.auo--cosmic.auo--phase4 .auo__name{animation:auo-tin 0.7s ease 0.7s both}',
    '.auo--cosmic.auo--phase4 .auo__desc{animation:auo-tin 0.7s ease 0.85s both}',
    '.auo--cosmic.auo--phase4 .auo__rarity{animation:auo-tin 0.7s ease 1s both}',
    '.auo--cosmic.auo--phase4 .auo__percent{animation:auo-tin 0.7s ease 1.1s both}',
    '.auo--cosmic.auo--phase4 .auo__actions{animation:auo-tin 0.7s ease 1.2s both}',

    /* === COSMIC SHARE BUTTON === */
    '.auo--cosmic .auo__btn--share{background:linear-gradient(135deg,#C084FC,#6A0DAD,#1E3A8A);color:#fff;font-weight:800;box-shadow:0 4px 24px rgba(168,85,247,0.4)}',

    /* A11y: prefers-reduced-motion */
    '@media(prefers-reduced-motion:reduce){.auo--cosmic .auo__nebula,.auo--cosmic .auo__supernova,.auo--cosmic .auo__shooting-star,.auo--cosmic .auo__icon{animation:none !important}}',

    /* ============ RESPONSIVE ============ */
    '@media(max-width:480px){.auo__card{padding:36px 20px 28px;max-width:320px;border-radius:20px}.auo__icon-wrap{width:100px;height:100px}.auo__icon img{width:52px;height:52px}.auo__icon--has-image img{width:85px;height:85px}.auo__coin{width:85px;height:85px}.auo__icon-emoji{font-size:44px}.auo__name{font-size:20px}.auo--legendary .auo__name,.auo--cosmic .auo__name{font-size:22px}.auo__desc{font-size:13px}.auo__label{font-size:10px;letter-spacing:2px}}'

    ].join('\n'); }

    return { show: show };
})();
