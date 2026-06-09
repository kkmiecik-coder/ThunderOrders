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
  /* Reel carousel engine (adapted from client/contest.js)                   */
  /* No infinite loops: targetK forces val(targetK) to return DR.drawn.      */
  /* ---------------------------------------------------------------------- */

  var ITEM_H = 84;
  var CENTER_Y = 126;
  var POOL_SIZE = 5;

  var DR = {
    pool: [],
    p: 0,
    speed: 0,
    maxSpeed: 25,
    accel: 0.5,
    state: 'idle',   // idle | spinning | braking | done
    drawn: null,     // ticket number to land on (or winner index)
    targetK: null,   // forced slot; val(targetK) returns DR.drawn
    brake: null,     // { from, to, dur, t0 }
    last: null,
    _onDone: null,
  };

  /**
   * Deterministic pseudo-random for slot k.
   * If targetK is set and k === targetK, returns DR.drawn directly.
   * This guarantees the reel lands on the correct value without any search loop.
   */
  function val(k) {
    if (DR.targetK !== null && k === DR.targetK) return DR.drawn;
    var x = Math.sin(k * 127.1 + 311.7) * 43758.5453;
    x = x - Math.floor(x);
    return 1 + Math.floor(x * 99);
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
    renderReel();
    requestAnimationFrame(reelFrame);

    setTimeout(function () {
      if (DR.state !== 'spinning') return;
      DR.targetK = targetSlot();
      DR.brake = { from: DR.p, to: DR.targetK, dur: 2800, t0: performance.now() };
      DR.state = 'braking';
      DR.last = null;
      DR._onDone = onDone;
      // rAF already running via the spinning branch; it will pick up 'braking' state
    }, spinMs);
  }

  /* ---------------------------------------------------------------------- */
  /* Winner card rendering                                                    */
  /* ---------------------------------------------------------------------- */

  function addWinnerCard(winner) {
    var area = document.getElementById('winnersArea');
    if (!area) return;
    var card = document.createElement('div');
    card.className = 'ca-winner-card';

    var place = document.createElement('div');
    place.className = 'ca-winner-place';
    place.textContent = 'Miejsce #' + winner.place;

    var who = document.createElement('div');
    who.className = 'ca-winner-who';
    who.textContent = '🏆 ' + (winner.name || 'Uczestnik ' + winner.user_id);

    var meta = document.createElement('div');
    meta.className = 'ca-winner-meta';
    meta.textContent = winner.tickets + ' losów • ' + winner.pct.toFixed(1) + '% szansy';

    card.appendChild(place);
    card.appendChild(who);
    card.appendChild(meta);
    area.appendChild(card);
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
      name.textContent = entry.name + (isWinner ? ' 🏆' : '');

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

    startReel(w.tickets, spinMs, function () {
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
