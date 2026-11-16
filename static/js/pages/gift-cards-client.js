/**
 * ThunderOrders - Gratisowe karty (strona klienta)
 * Siatka rankingu (jedna odpowiedź w wierszu i w kolumnie) oraz wyścig „Zgłaszam się".
 */
(function () {
  'use strict';

  function getCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  function toast(msg, type) {
    if (typeof window.showToast === 'function') window.showToast(msg, type);
  }

  /* ----- Siatka rankingu ----- */
  var form = document.getElementById('gcRankingForm');
  if (form) {
    var saveBtn = document.getElementById('gcRankingSave');
    var rows = Array.prototype.slice.call(form.querySelectorAll('tbody tr'));

    var refresh = function () {
      if (!saveBtn) return;
      var done = rows.every(function (row) {
        return row.querySelector('input[type="radio"]:checked');
      });
      saveBtn.disabled = !done;
    };

    form.addEventListener('change', function (e) {
      var input = e.target;
      if (!input || input.type !== 'radio') return;
      // To samo miejsce w innych wierszach zostaje odznaczone.
      form.querySelectorAll('input[type="radio"][value="' + input.value + '"]').forEach(function (other) {
        if (other !== input && other.checked) other.checked = false;
      });
      refresh();
    });
    refresh();
  }

  /* ----- Wyścig ----- */
  var race = document.getElementById('gcRace');
  if (race) {
    var btn = document.getElementById('gcRaceBtn');
    var countdown = document.getElementById('gcCountdown');
    var posBox = document.getElementById('gcPosition');
    var posNum = document.getElementById('gcPositionNum');
    var raceAt = race.dataset.raceAt ? new Date(race.dataset.raceAt).getTime() : null;
    var registered = !!race.dataset.position;
    var timer = null;

    var pad = function (n) { return (n < 10 ? '0' : '') + n; };

    var tick = function () {
      if (registered) {
        btn.disabled = true;
        countdown.textContent = '';
        return;
      }
      if (raceAt === null) {
        btn.disabled = true;
        countdown.textContent = 'Godzina zgłoszeń nie jest jeszcze ustalona.';
        return;
      }
      var left = raceAt - Date.now();
      if (left <= 0) {
        btn.disabled = false;
        countdown.textContent = 'Zgłoszenia trwają!';
        if (timer) { clearInterval(timer); timer = null; }
        return;
      }
      btn.disabled = true;
      var s = Math.floor(left / 1000);
      var h = Math.floor(s / 3600);
      countdown.textContent = 'Do startu: ' + pad(h) + ':' + pad(Math.floor((s % 3600) / 60)) + ':' + pad(s % 60);
    };

    btn.addEventListener('click', function () {
      btn.disabled = true;
      fetch(race.dataset.raceUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCsrfToken(), 'Accept': 'application/json' },
        credentials: 'same-origin'
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data && data.success) {
            registered = true;
            posNum.textContent = data.position;
            posBox.hidden = false;
            tick();
          } else {
            toast((data && data.error) || 'Nie udało się zgłosić.', 'error');
            btn.disabled = false;
          }
        })
        .catch(function () {
          toast('Błąd połączenia — spróbuj jeszcze raz.', 'error');
          btn.disabled = false;
        });
    });

    tick();
    if (!registered && raceAt !== null) timer = setInterval(tick, 1000);
  }
})();
