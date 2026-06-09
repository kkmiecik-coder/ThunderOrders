/**
 * ThunderOrders - Contest Widget & Spinner
 * Handles the spin button, the vertical carousel modal, and the cooldown countdown.
 * Vanilla JS, no inline scripts required in HTML.
 */
// TODO: reel/carousel physics (val/renderReel/targetSlot/frame) jest zduplikowany z static/js/pages/admin/contest-draw.js — do wyciągnięcia do static/js/components/contest-reel.js w osobnym follow-upie. Zmiany trzymać zsynchronizowane.
(function () {
  'use strict';

  /* ----- CSRF helper ----- */
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

  /* ----- Toast / error helper ----- */
  function showError(msg) {
    if (window.Toast && typeof window.Toast.show === 'function') {
      window.Toast.show(msg, 'error');
    } else {
      alert(msg);
    }
  }

  /* ----- Time helpers ----- */
  function pad(n) { return n < 10 ? '0' + n : '' + n; }

  function formatTime(totalSecs) {
    if (totalSecs <= 0) return '00:00:00';
    var h = Math.floor(totalSecs / 3600);
    var m = Math.floor((totalSecs % 3600) / 60);
    var s = totalSecs % 60;
    return pad(h) + ':' + pad(m) + ':' + pad(s);
  }

  /**
   * Start a countdown to the given ISO date string.
   * Updates clockEl every second, calls onExpire when time runs out.
   */
  function startCountdown(isoDate, clockEl, onExpire) {
    var target = new Date(isoDate).getTime();

    function tick() {
      var diff = Math.ceil((target - Date.now()) / 1000);
      if (diff <= 0) {
        if (clockEl) clockEl.textContent = '00:00:00';
        if (typeof onExpire === 'function') onExpire();
        return;
      }
      if (clockEl) clockEl.textContent = formatTime(diff);
      setTimeout(tick, 1000);
    }
    tick();
  }

  /* ----- Reel carousel engine ----- */
  var ITEM_H = 84;         // px height of one slot
  var CENTER_Y = 126;      // px — centre of the marker window (126 = 252/2, reel window is 3×84)
  var POOL_SIZE = 5;       // visible DOM nodes in the reel

  /**
   * Deterministic pseudo-random value for reel slot k.
   * Returns integer in [1, 50] — same slot always shows same number.
   * Exception: if S.targetK is set and k equals it, returns S.drawn directly
   * (forces the drawn value onto that slot regardless of its range).
   */
  function val(k) {
    if (S.targetK !== null && k === S.targetK) return S.drawn;
    var x = Math.sin(k * 127.1 + 311.7) * 43758.5453;
    x = x - Math.floor(x);
    return 1 + Math.floor(x * 50);
  }

  /* Shared spinner state — only one modal can be open at a time */
  var S = {
    overlay: null,
    pool: [],
    btnEl: null,
    resEl: null,
    p: 0,           // current reel position (in slot units), decreases = reel moves down
    speed: 0,       // px/frame equivalent
    maxSpeed: 30,
    accel: 0.6,
    state: 'idle',  // idle | spinning | braking | done
    drawn: null,    // server result (tickets_won)
    targetK: null,  // slot index forced to show S.drawn; set on brake, reset on next spin
    brake: null,    // { from, to, dur, t0 }
    last: null,     // last rAF timestamp
    serverData: null,  // full JSON response from /konkurs/spin
  };

  function renderReel() {
    var base = Math.round(S.p);
    var center = base;
    for (var n = 0; n < POOL_SIZE; n++) {
      var k = base + (n - 2);
      // p decreases → (k - p) grows → y increases → reel moves DOWN
      var y = CENTER_Y + (k - S.p) * ITEM_H;
      var el = S.pool[n];
      el.style.transform = 'translateY(' + (y - ITEM_H / 2) + 'px)';
      el.textContent = val(k);
      if (k === center) {
        el.classList.add('contest-num--hot');
      } else {
        el.classList.remove('contest-num--hot');
      }
    }
  }

  /**
   * Pick a fixed-overshoot slot as the brake target.
   * S.targetK will be set to this value before val() is called, so val(S.targetK)
   * returns S.drawn regardless of range — no searching, no infinite loop.
   */
  function targetSlot() {
    return Math.floor(S.p) - 46; // minimalny overshoot w slotach przed hamowaniem
  }

  function frame(ts) {
    if (S.last === null) S.last = ts;
    var dt = (ts - S.last) / 16.67;
    S.last = ts;

    if (S.state === 'spinning') {
      if (S.speed < S.maxSpeed) {
        S.speed = Math.min(S.maxSpeed, S.speed + S.accel * dt);
      }
      S.p -= (S.speed / ITEM_H) * dt;
      renderReel();
    } else if (S.state === 'braking') {
      var pr = Math.min(1, (ts - S.brake.t0) / S.brake.dur);
      var ease = 1 - Math.pow(1 - pr, 4);  // easeOutQuart — long slow tail
      S.p = S.brake.from + (S.brake.to - S.brake.from) * ease;
      renderReel();
      if (pr >= 1) {
        S.state = 'done';
        finishSpin();
        return; // stop rAF
      }
    }

    if (S.state === 'spinning' || S.state === 'braking') {
      requestAnimationFrame(frame);
    }
  }

  function finishSpin() {
    var drawn = S.drawn;
    // Show result text
    S.resEl.innerHTML = 'Zdobywasz <b>' + drawn + ' los' + pluralLosow(drawn) + '</b>! 🎉';
    S.resEl.classList.add('contest-spin-result--show');
    // Update button to ZAMKNIJ
    S.btnEl.textContent = 'ZAMKNIJ';
    S.btnEl.disabled = false;
    S.btnEl.className = 'contest-spin-btn';
    // Update UI outside the modal immediately
    if (S.serverData) {
      afterSpinDone(S.serverData);
    }
  }

  function pluralLosow(n) {
    if (n === 1) return '';
    if (n >= 2 && n <= 4) return 'y';
    return 'ów';
  }

  /* ----- Modal lifecycle ----- */

  function destroyModal() {
    if (!S.overlay) return;
    var el = S.overlay;
    el.classList.remove('contest-spin-overlay--active');
    el.classList.add('contest-spin-overlay--closing');
    setTimeout(function () {
      if (el.parentNode) el.parentNode.removeChild(el);
    }, 350);
    S.overlay = null;
    S.state = 'idle';
  }

  function openSpinModal(spinUrl) {
    if (S.overlay) return; // already open

    /* Reset state */
    S.p = 0; S.speed = 0; S.last = null;
    S.drawn = null; S.targetK = null; S.brake = null; S.serverData = null;
    S.state = 'idle';

    /* Build overlay */
    var overlay = document.createElement('div');
    overlay.className = 'contest-spin-overlay';
    overlay.id = 'contestSpinOverlay';

    /* Build modal card */
    var modal = document.createElement('div');
    modal.className = 'contest-spin-modal';
    modal.innerHTML =
      '<h3>🎲 Twoje losowanie</h3>' +
      '<div class="contest-spin-sub">Naciśnij START, a potem STOP, gdy zechcesz</div>' +
      '<div class="contest-reel-wrap">' +
        '<div class="contest-marker"></div>' +
        '<div class="contest-reel" id="contestReelInner"></div>' +
      '</div>' +
      '<div class="contest-spin-ctrl">' +
        '<button class="contest-spin-btn" id="contestModalBtn">START</button>' +
      '</div>' +
      '<div class="contest-spin-result" id="contestModalResult"></div>' +
      '<div class="contest-spin-hint">START kręci bębnem, STOP zatrzymuje go i przyznaje Twoje losy.</div>';

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    /* Activate with transition */
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        overlay.classList.add('contest-spin-overlay--active');
      });
    });

    S.overlay = overlay;
    S.btnEl = modal.querySelector('#contestModalBtn');
    S.resEl = modal.querySelector('#contestModalResult');

    /* Build reel pool */
    var reelInner = modal.querySelector('#contestReelInner');
    S.pool = [];
    for (var n = 0; n < POOL_SIZE; n++) {
      var d = document.createElement('div');
      d.className = 'contest-num';
      reelInner.appendChild(d);
      S.pool.push(d);
    }
    renderReel();

    /* Button: START -> STOP -> ZAMKNIJ */
    S.btnEl.addEventListener('click', function () {
      if (S.state === 'idle') {
        /* START — wolny rozruch karuzeli, bez losowania */
        S.state = 'spinning';
        S.speed = 2;
        S.last = null;
        S.btnEl.textContent = 'STOP';
        S.btnEl.className = 'contest-spin-btn contest-stop-btn';
        requestAnimationFrame(frame);
      } else if (S.state === 'spinning') {
        /* STOP — dopiero teraz serwer losuje liczbę; karuzela kręci się dalej
           dopóki czekamy na odpowiedź, potem hamuje do wylosowanej liczby. */
        S.btnEl.disabled = true;
        S.btnEl.textContent = 'Losowanie…';
        fetch(spinUrl, {
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
              destroyModal();
              showError(data.error || 'Błąd losowania.');
              return;
            }
            S.serverData = data;
            S.drawn = data.tickets_won;
            /* Ustaw cel — val(S.targetK) zwróci S.drawn dla dowolnej liczby */
            S.targetK = targetSlot();
            S.brake = { from: S.p, to: S.targetK, dur: 7600, t0: performance.now() };
            S.state = 'braking';
            S.last = null;
            /* pętla rAF wciąż działa (była 'spinning') — przejdzie w 'braking' */
          })
          .catch(function () {
            destroyModal();
            showError('Błąd połączenia z serwerem.');
          });
      } else if (S.state === 'done') {
        destroyModal();
      }
    });

    /* Click outside (only when done) */
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay && S.state === 'done') {
        destroyModal();
      }
    });
  }

  /* ----- After-spin UI update ----- */

  function afterSpinDone(data) {
    /* Update ticket counters */
    var wTickets = document.getElementById('widgetTickets');
    var pTickets = document.getElementById('myTickets');
    if (wTickets && data.my_total !== undefined) wTickets.textContent = data.my_total;
    if (pTickets && data.my_total !== undefined) pTickets.textContent = data.my_total;

    /* Toggle spin buttons / cooldowns */
    var widgetSpinBtn = document.getElementById('widgetSpinBtn');
    var pageSpinBtn = document.getElementById('pageSpinBtn');
    var widgetCooldown = document.getElementById('widgetCooldown');
    var pageCooldown = document.getElementById('pageCooldown');

    if (widgetSpinBtn) widgetSpinBtn.hidden = true;
    if (pageSpinBtn) pageSpinBtn.hidden = true;
    if (widgetCooldown) widgetCooldown.hidden = false;
    if (pageCooldown) pageCooldown.hidden = false;

    /* Start countdowns */
    if (data.next_spin_at) {
      var onExpire = function () {
        if (widgetSpinBtn) widgetSpinBtn.hidden = false;
        if (pageSpinBtn) pageSpinBtn.hidden = false;
        if (widgetCooldown) widgetCooldown.hidden = true;
        if (pageCooldown) pageCooldown.hidden = true;
      };

      var widgetClock = document.getElementById('widgetClock');
      var pageClock = document.getElementById('pageClock');

      if (widgetClock) startCountdown(data.next_spin_at, widgetClock, onExpire);
      if (pageClock) startCountdown(data.next_spin_at, pageClock, pageClock === widgetClock ? function () {} : onExpire);
    }
  }

  /* ----- Initialisation ----- */

  document.addEventListener('DOMContentLoaded', function () {
    var widget = document.getElementById('contestWidget');
    var page = document.getElementById('contestPage');

    /* No contest elements on this page — graceful no-op */
    if (!widget && !page) return;

    var spinUrl = (widget || page).dataset.spinUrl;

    /* Initial cooldown countdown if spin not yet available */
    function initCountdown(root, clockId, spinBtnId, cooldownId) {
      if (!root) return;
      if (root.dataset.canSpin === '1') return; // can spin now, nothing to count
      var nextSpin = root.dataset.nextSpin;
      if (!nextSpin) return;

      var clockEl = document.getElementById(clockId);
      var spinBtnEl = document.getElementById(spinBtnId);
      var coolEl = document.getElementById(cooldownId);

      startCountdown(nextSpin, clockEl, function () {
        if (spinBtnEl) spinBtnEl.hidden = false;
        if (coolEl) coolEl.hidden = true;
      });
    }

    initCountdown(widget, 'widgetClock', 'widgetSpinBtn', 'widgetCooldown');
    initCountdown(page, 'pageClock', 'pageSpinBtn', 'pageCooldown');

    /* Attach spin button handlers */
    ['widgetSpinBtn', 'pageSpinBtn'].forEach(function (id) {
      var btn = document.getElementById(id);
      if (!btn) return;
      btn.addEventListener('click', function () {
        openSpinModal(spinUrl);
      });
    });
  });

}());
