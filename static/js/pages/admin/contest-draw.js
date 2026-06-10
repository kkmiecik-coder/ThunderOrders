/**
 * contest-draw.js — Admin live draw screen
 * Uses the same vertical reel carousel as the client contest spinner.
 * Reel uses val(k)/targetK approach — NO infinite loops.
 * Sequential winner reveals for N winners.
 */
// TODO: reel/carousel physics (val/renderReel/targetSlot/frame) jest zduplikowany z static/js/pages/client/contest.js — do wyciągnięcia do static/js/components/contest-reel.js w osobnym follow-upie. Zmiany trzymać zsynchronizowane.
(function () {
  'use strict';

  /* ---------------------------------------------------------------------- */
  /* CSRF helper                                                              */
  /* ---------------------------------------------------------------------- */

  function getCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');
    var cookies = document.cookie.split(';');
    for (var i = 0; i < cookies.length; i++) {
      var parts = cookies[i].trim().split('=');
      if (parts[0] === 'csrf_token') return decodeURIComponent(parts[1] || '');
    }
    return '';
  }

  /* ---------------------------------------------------------------------- */
  /* Error helper                                                             */
  /* ---------------------------------------------------------------------- */

  function showError(msg) {
    if (window.Toast && typeof window.Toast.show === 'function') {
      window.Toast.show(msg, 'error');
    } else {
      alert(msg);
    }
  }

  /* ---------------------------------------------------------------------- */
  /* Konfetti — lekki canvas bez zależności (kolory brandowe)                */
  /* ---------------------------------------------------------------------- */

  var REDUCED_MOTION = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  var CONFETTI_COLORS = ['#f093fb', '#f5576c', '#ff8500', '#ffd166', '#a78bfa', '#34d399'];
  var confettiCanvas = null;
  var confettiCtx = null;
  var confettiParts = [];
  var confettiRaf = null;

  function confettiBurst() {
    if (REDUCED_MOTION) return;
    var stage = document.querySelector('.ca-stage');
    if (!stage) return;
    if (!confettiCanvas) {
      confettiCanvas = document.createElement('canvas');
      confettiCanvas.className = 'ca-confetti';
      stage.appendChild(confettiCanvas);
      confettiCtx = confettiCanvas.getContext('2d');
    }
    var w = confettiCanvas.width = stage.clientWidth;
    var h = confettiCanvas.height = stage.clientHeight;
    // Wybuch ze środka okna bębna
    var reel = stage.querySelector('.ca-reel-wrap');
    var cx = w / 2;
    var cy = h * 0.4;
    if (reel) {
      var sr = stage.getBoundingClientRect();
      var rr = reel.getBoundingClientRect();
      cx = rr.left - sr.left + rr.width / 2;
      cy = rr.top - sr.top + rr.height / 2;
    }
    for (var i = 0; i < 140; i++) {
      var ang = Math.random() * Math.PI * 2;
      var spd = 4 + Math.random() * 9;
      confettiParts.push({
        x: cx, y: cy,
        vx: Math.cos(ang) * spd,
        vy: Math.sin(ang) * spd - 3,
        g: 0.16 + Math.random() * 0.1,
        size: 4 + Math.random() * 5,
        rot: Math.random() * Math.PI,
        vr: (Math.random() - 0.5) * 0.3,
        color: CONFETTI_COLORS[(Math.random() * CONFETTI_COLORS.length) | 0],
        life: 80 + Math.random() * 60,
      });
    }
    if (!confettiRaf) confettiRaf = requestAnimationFrame(confettiFrame);
  }

  function confettiFrame() {
    var w = confettiCanvas.width;
    var h = confettiCanvas.height;
    confettiCtx.clearRect(0, 0, w, h);
    var alive = [];
    for (var i = 0; i < confettiParts.length; i++) {
      var p = confettiParts[i];
      p.vx *= 0.985;
      p.vy = p.vy * 0.985 + p.g;
      p.x += p.vx;
      p.y += p.vy;
      p.rot += p.vr;
      p.life -= 1;
      if (p.life > 0 && p.y < h + 20) {
        confettiCtx.save();
        confettiCtx.translate(p.x, p.y);
        confettiCtx.rotate(p.rot);
        confettiCtx.globalAlpha = Math.min(1, p.life / 30);
        confettiCtx.fillStyle = p.color;
        confettiCtx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
        confettiCtx.restore();
        alive.push(p);
      }
    }
    confettiParts = alive;
    if (confettiParts.length) {
      confettiRaf = requestAnimationFrame(confettiFrame);
    } else {
      confettiRaf = null;
      confettiCtx.clearRect(0, 0, w, h);
    }
  }

  /* ---------------------------------------------------------------------- */
  /* Reel carousel engine (adapted from client/contest.js)                   */
  /* No infinite loops: targetK forces val(targetK) to return DR.drawn.      */
  /* ---------------------------------------------------------------------- */

  var ITEM_H = 84;
  var CENTER_Y = 126;
  var POOL_SIZE = 5;

  var DR = {
    pool: [],
    names: [],       // nazwy uczestników do przewijania w bębnie
    p: 0,
    speed: 0,
    maxSpeed: 25,
    accel: 0.5,
    state: 'idle',   // idle | spinning | braking | done
    drawn: null,     // nazwa zwycięzcy, na której bęben ma wyhamować
    targetK: null,   // forced slot; val(targetK) returns DR.drawn
    brake: null,     // { from, to, dur, t0 }
    last: null,
    _onDone: null,
  };

  // Klasy stanu na oknie bębna — sterują efektami CSS (blur, puls, błysk)
  function setReelState(state) {
    var wrap = document.querySelector('.ca-reel-wrap');
    if (!wrap) return;
    wrap.classList.remove('ca-reel-wrap--spinning', 'ca-reel-wrap--braking', 'ca-reel-wrap--landed');
    if (state) wrap.classList.add('ca-reel-wrap--' + state);
  }

  /**
   * Wartość slotu k — NAZWA uczestnika (pseudo-losowo z DR.names).
   * Jeśli targetK ustawione i k === targetK, zwraca DR.drawn (nazwę zwycięzcy)
   * — gwarantuje wyhamowanie na właściwej osobie bez pętli szukającej.
   */
  function val(k) {
    if (DR.targetK !== null && k === DR.targetK) return DR.drawn;
    if (!DR.names.length) return '—';
    var x = Math.sin(k * 127.1 + 311.7) * 43758.5453;
    x = x - Math.floor(x);
    return DR.names[Math.floor(x * DR.names.length) % DR.names.length];
  }

  function renderReel() {
    var base = Math.round(DR.p);
    var center = base;
    for (var n = 0; n < POOL_SIZE; n++) {
      var k = base + (n - 2);
      var y = CENTER_Y + (k - DR.p) * ITEM_H;
      var el = DR.pool[n];
      el.style.transform = 'translateY(' + (y - ITEM_H / 2) + 'px)';
      el.textContent = val(k);
      if (k === center) {
        el.classList.add('ca-reel-num--hot');
      } else {
        el.classList.remove('ca-reel-num--hot');
      }
    }
  }

  /**
   * Pick brake target using fixed overshoot (no search loop).
   * S.targetK is set to this value; val(targetK) returns DR.drawn.
   */
  function targetSlot() {
    return Math.floor(DR.p) - 46;
  }

  function reelFrame(ts) {
    if (DR.last === null) DR.last = ts;
    var dt = (ts - DR.last) / 16.67;
    DR.last = ts;

    if (DR.state === 'spinning') {
      if (DR.speed < DR.maxSpeed) {
        DR.speed = Math.min(DR.maxSpeed, DR.speed + DR.accel * dt);
      }
      DR.p -= (DR.speed / ITEM_H) * dt;
      renderReel();
    } else if (DR.state === 'braking') {
      var pr = Math.min(1, (ts - DR.brake.t0) / DR.brake.dur);
      var ease = 1 - Math.pow(1 - pr, 4); // easeOutQuart
      DR.p = DR.brake.from + (DR.brake.to - DR.brake.from) * ease;
      renderReel();
      if (pr >= 1) {
        DR.state = 'done';
        setReelState('landed');
        setTimeout(function () { setReelState(null); }, 900);
        var cb = DR._onDone;
        DR._onDone = null;
        if (typeof cb === 'function') cb();
        return; // stop rAF
      }
    }

    if (DR.state === 'spinning' || DR.state === 'braking') {
      requestAnimationFrame(reelFrame);
    }
  }

  /**
   * Start reel spinning and auto-brake after spinMs to land on drawnValue.
   * Calls onDone when brake animation finishes.
   */
  function startReel(drawnValue, spinMs, onDone) {
    DR.p = 0;
    DR.speed = 2;
    DR.state = 'spinning';
    DR.last = null;
    DR.drawn = drawnValue;
    DR.targetK = null;
    DR.brake = null;
    DR._onDone = null;
    setReelState('spinning');
    renderReel();
    requestAnimationFrame(reelFrame);

    setTimeout(function () {
      if (DR.state !== 'spinning') return;
      DR.targetK = targetSlot();
      DR.brake = { from: DR.p, to: DR.targetK, dur: 2800, t0: performance.now() };
      DR.state = 'braking';
      DR.last = null;
      DR._onDone = onDone;
      setReelState('braking');
      // rAF already running via the spinning branch; it will pick up 'braking' state
    }, spinMs);
  }

  /* ---------------------------------------------------------------------- */
  /* Winner card rendering                                                    */
  /* ---------------------------------------------------------------------- */

  // Ikona trofeum (bootstrap trophy) — zamiast emoji
  var TROPHY_SVG = '<svg width="__PX__" height="__PX__" viewBox="0 0 16 16" fill="currentColor">' +
    '<path d="M2.5.5A.5.5 0 0 1 3 0h10a.5.5 0 0 1 .5.5q0 .807-.034 1.536a3 3 0 1 1-1.133 5.89c-.79 1.865-1.878 2.777-2.833 3.011v2.173l1.425.356c.194.048.377.135.537.255L13.3 15.1a.5.5 0 0 1-.3.9H3a.5.5 0 0 1-.3-.9l1.838-1.379c.16-.12.343-.207.537-.255L6.5 13.11v-2.173c-.955-.234-2.043-1.146-2.833-3.012a3 3 0 1 1-1.132-5.89A33 33 0 0 1 2.5.5m.099 2.54a2 2 0 0 0 .72 3.935c-.333-1.05-.588-2.346-.72-3.935m10.083 3.935a2 2 0 0 0 .72-3.935c-.133 1.59-.388 2.885-.72 3.935"/>' +
    '</svg>';

  function trophySvg(px) {
    return TROPHY_SVG.replace(/__PX__/g, String(px));
  }

  function addWinnerCard(winner) {
    var area = document.getElementById('winnersArea');
    if (!area) return;
    var card = document.createElement('div');
    card.className = 'ca-winner-card';

    var icon = document.createElement('div');
    icon.className = 'ca-winner-icon';
    icon.innerHTML = trophySvg(20);

    var place = document.createElement('div');
    place.className = 'ca-winner-place';
    place.textContent = 'Miejsce #' + winner.place;

    var who = document.createElement('div');
    who.className = 'ca-winner-who';
    who.textContent = winner.name || 'Uczestnik ' + winner.user_id;

    var meta = document.createElement('div');
    meta.className = 'ca-winner-meta';
    meta.textContent = winner.tickets + ' losów • ' + winner.pct.toFixed(1) + '% szansy';

    card.appendChild(icon);
    card.appendChild(place);
    card.appendChild(who);
    card.appendChild(meta);
    area.appendChild(card);

    confettiBurst();
  }

  /* ---------------------------------------------------------------------- */
  /* Pool breakdown bars                                                      */
  /* ---------------------------------------------------------------------- */

  function renderBreakdown(breakdown, winners) {
    var container = document.getElementById('breakdownBars');
    var section = document.getElementById('poolBreakdown');
    if (!container || !section) return;

    // Build set of winner user_ids for highlight
    var winnerIds = {};
    for (var i = 0; i < winners.length; i++) {
      winnerIds[winners[i].user_id] = true;
    }

    var maxTickets = 0;
    for (var j = 0; j < breakdown.length; j++) {
      if (breakdown[j].tickets > maxTickets) maxTickets = breakdown[j].tickets;
    }

    container.innerHTML = '';
    for (var k = 0; k < breakdown.length; k++) {
      var entry = breakdown[k];
      var isWinner = !!winnerIds[entry.user_id];
      var barPct = maxTickets > 0 ? Math.round((entry.tickets / maxTickets) * 100) : 0;

      var bar = document.createElement('div');
      bar.className = 'ca-bar' + (isWinner ? ' ca-bar--winner' : '');

      var name = document.createElement('div');
      name.className = 'ca-bar-name';
      name.title = entry.name;
      name.textContent = entry.name;
      if (isWinner) {
        name.insertAdjacentHTML('beforeend', trophySvg(12));
      }

      var track = document.createElement('div');
      track.className = 'ca-bar-track';
      var fill = document.createElement('div');
      fill.className = 'ca-bar-fill';
      fill.style.width = '0%';
      track.appendChild(fill);

      var pct = document.createElement('div');
      pct.className = 'ca-bar-pct';
      pct.textContent = entry.tickets + ' los. • ' + entry.pct.toFixed(1) + '%';

      bar.appendChild(name);
      bar.appendChild(track);
      bar.appendChild(pct);
      container.appendChild(bar);

      // Animate fill after paint
      (function (fillEl, targetPct) {
        requestAnimationFrame(function () {
          requestAnimationFrame(function () {
            fillEl.style.width = targetPct + '%';
          });
        });
      }(fill, barPct));
    }

    section.style.display = '';
  }

  /* ---------------------------------------------------------------------- */
  /* Sequential winner reveals                                                */
  /* ---------------------------------------------------------------------- */

  function revealWinners(winners, idx, allDone) {
    if (idx >= winners.length) {
      allDone();
      return;
    }
    var w = winners[idx];
    var spinMs = 1400 + Math.random() * 400; // 1.4–1.8s spinning

    startReel(w.name, spinMs, function () {
      // Reel landed — show winner card
      addWinnerCard(w);

      if (idx + 1 < winners.length) {
        // Pause, then reveal next winner
        setTimeout(function () {
          revealWinners(winners, idx + 1, allDone);
        }, 1200);
      } else {
        // All winners revealed
        setTimeout(allDone, 800);
      }
    });
  }

  /* ---------------------------------------------------------------------- */
  /* Main init                                                                */
  /* ---------------------------------------------------------------------- */

  document.addEventListener('DOMContentLoaded', function () {
    var root = document.getElementById('drawRoot');
    if (!root) return;

    var drawUrl = root.dataset.drawUrl;
    var btnDraw = document.getElementById('btnDraw');
    var reelEl = document.getElementById('drawReel');

    if (!btnDraw || !reelEl) return;

    // Nazwy uczestników przekazane z serwera — bęben pokazuje je od razu
    try {
      DR.names = JSON.parse(root.dataset.participants || '[]');
    } catch (e) {
      DR.names = [];
    }

    // Build reel DOM pool
    for (var n = 0; n < POOL_SIZE; n++) {
      var d = document.createElement('div');
      d.className = 'ca-reel-num';
      reelEl.appendChild(d);
      DR.pool.push(d);
    }
    renderReel();

    btnDraw.addEventListener('click', function () {
      btnDraw.disabled = true;

      fetch(drawUrl, {
        method: 'POST',
        headers: {
          'X-CSRFToken': getCsrfToken(),
          'X-Requested-With': 'XMLHttpRequest',
          'Content-Type': 'application/json',
        },
        body: '{}',
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data.success) {
            btnDraw.disabled = false;
            showError(data.error || 'Błąd losowania.');
            return;
          }

          // Update stats from response
          var statPool = document.getElementById('statPool');
          var statParticipants = document.getElementById('statParticipants');
          if (statPool) statPool.textContent = data.pool;
          if (statParticipants) {
            statParticipants.textContent = data.breakdown ? data.breakdown.length : '—';
          }

          // Clear previous winners area
          var area = document.getElementById('winnersArea');
          if (area) area.innerHTML = '';

          // Nazwy uczestników do przewijania w bębnie
          DR.names = (data.breakdown || []).map(function (b) { return b.name; });

          // Reveal winners sequentially, then show breakdown
          revealWinners(data.winners || [], 0, function () {
            renderBreakdown(data.breakdown || [], data.winners || []);
          });
        })
        .catch(function () {
          btnDraw.disabled = false;
          showError('Błąd połączenia z serwerem.');
        });
    });
  });

}());
