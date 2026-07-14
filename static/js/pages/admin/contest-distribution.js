/* Modal „Rozkład punktów" na liście konkursów (/admin/konkursy). */
(function () {
  'use strict';

  var modal = document.getElementById('distModal');
  if (!modal) return;

  var elName = document.getElementById('distName');
  var elChart = document.getElementById('distChart');
  var elAxis = document.getElementById('distAxis');
  var elYAxis = document.getElementById('distYAxis');
  var elGrid = document.getElementById('distGrid');
  var elBars = document.getElementById('distBars');
  var elEmpty = document.getElementById('distEmpty');
  var elTotal = document.getElementById('distTotal');

  // Pływający tooltip nad kursorem (współdzielony, tworzony raz)
  var elTip = document.createElement('div');
  elTip.className = 'ca-dist-tip';
  elTip.style.display = 'none';
  modal.appendChild(elTip);

  function toast(msg, type) {
    if (typeof window.showToast === 'function') window.showToast(msg, type || 'error');
  }

  function openModal() { modal.classList.add('active'); modal.setAttribute('aria-hidden', 'false'); }
  function closeModal() {
    modal.classList.remove('active');
    modal.setAttribute('aria-hidden', 'true');
    elTip.style.display = 'none';
    closeUserSpins();   // zamknij ewentualny otwarty minimodal
  }

  /* -------------------------------------------------------------- */
  /* Minimodal: losowania konkretnego uczestnika (nad #distModal)     */
  /* -------------------------------------------------------------- */
  var currentCid = null;   // ustawiany przy otwarciu rozkładu
  var uspinsModal = document.getElementById('userSpinsModal');
  var uspinsName = document.getElementById('uspinsName');
  var uspinsSummary = document.getElementById('uspinsSummary');
  var uspinsList = document.getElementById('uspinsList');
  var uspinsEmpty = document.getElementById('uspinsEmpty');

  function plLosowania(n) {
    var n10 = n % 10, n100 = n % 100;
    if (n === 1) return 'losowanie';
    if (n10 >= 2 && n10 <= 4 && !(n100 >= 12 && n100 <= 14)) return 'losowania';
    return 'losowań';
  }

  function fmtWhen(iso) {
    try {
      return new Date(iso).toLocaleString('pl-PL', {
        day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
      });
    } catch (e) { return iso || ''; }
  }

  function closeUserSpins() {
    if (!uspinsModal) return;
    uspinsModal.classList.remove('active');
    uspinsModal.setAttribute('aria-hidden', 'true');
  }

  function renderSpins(data) {
    uspinsSummary.innerHTML =
      '<span class="ca-uspins-stat"><b>' + data.spin_count + '</b> ' + plLosowania(data.spin_count) + '</span>' +
      '<span class="ca-uspins-stat"><b>' + data.total_tickets + '</b> losów łącznie</span>';
    if (!data.spins || !data.spins.length) {
      uspinsList.innerHTML = '';
      uspinsEmpty.style.display = '';
      return;
    }
    uspinsEmpty.style.display = 'none';
    uspinsList.innerHTML = data.spins.map(function (s) {
      return '<div class="ca-uspins-row">' +
             '<span class="ca-uspins-tickets">' + s.tickets + ' los.</span>' +
             '<span class="ca-uspins-when">' + fmtWhen(s.at) + '</span>' +
             '</div>';
    }).join('');
  }

  function openUserSpins(uid, name) {
    if (!uspinsModal || !currentCid) return;
    uspinsName.textContent = name || '';
    uspinsSummary.innerHTML = '';
    uspinsList.innerHTML = '';
    uspinsEmpty.style.display = 'none';
    uspinsModal.classList.add('active');
    uspinsModal.setAttribute('aria-hidden', 'false');
    fetch('/admin/konkursy/' + currentCid + '/uzytkownik/' + uid + '/losowania',
          { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data || !data.success) { toast('Nie udało się pobrać losowań.', 'error'); closeUserSpins(); return; }
        renderSpins(data);
      })
      .catch(function () { toast('Błąd sieci — spróbuj ponownie.', 'error'); closeUserSpins(); });
  }

  // „Ładne" całkowite wartości osi Y (0 .. niceMax), ~4 przedziały
  function niceIntTicks(maxCount) {
    if (maxCount <= 0) return [0, 1];
    var raw = maxCount / 4;
    var pow = Math.pow(10, Math.floor(Math.log10(raw)));
    var cand = [1, 2, 2.5, 5, 10];
    var step = 10 * pow;
    for (var i = 0; i < cand.length; i++) { if (cand[i] * pow >= raw) { step = cand[i] * pow; break; } }
    step = Math.max(1, Math.round(step));
    var niceMax = Math.ceil(maxCount / step) * step;
    var ticks = [];
    for (var v = 0; v <= niceMax; v += step) ticks.push(v);
    return ticks;
  }

  function renderChart(buckets, config, spinCount) {
    elChart.innerHTML = '';
    elAxis.innerHTML = '';
    elYAxis.innerHTML = '';
    elGrid.innerHTML = '';

    var maxCount = 0;
    buckets.forEach(function (b) { if (b.count > maxCount) maxCount = b.count; });
    var ticks = niceIntTicks(maxCount);
    var niceMax = ticks[ticks.length - 1];

    // Oś Y (od góry: niceMax ... 0) + poziome linie siatki na tych wysokościach
    for (var i = ticks.length - 1; i >= 0; i--) {
      var yl = document.createElement('span');
      yl.textContent = ticks[i];
      elYAxis.appendChild(yl);
      elGrid.appendChild(document.createElement('span'));
    }

    buckets.forEach(function (b) {
      var h = niceMax > 0 ? Math.round((b.count / niceMax) * 100) : 0;
      var pctTxt = spinCount ? ' • ' + (b.count / spinCount * 100).toFixed(1) + '%' : '';

      var col = document.createElement('div');
      col.className = 'ca-dist-bar';
      var fill = document.createElement('div');
      fill.className = 'ca-dist-bar-fill';
      fill.style.height = '0%';
      col.appendChild(fill);
      elChart.appendChild(col);

      var lbl = document.createElement('span');
      lbl.textContent = b.label;
      elAxis.appendChild(lbl);

      col.addEventListener('mousemove', function (e) {
        elTip.innerHTML = '<b>' + b.count + '</b> losowań<span>' + b.label + ' losów' + pctTxt + '</span>';
        elTip.style.display = 'block';
        elTip.style.left = e.clientX + 'px';
        elTip.style.top = e.clientY + 'px';
      });
      col.addEventListener('mouseleave', function () { elTip.style.display = 'none'; });

      (function (f, target) {
        requestAnimationFrame(function () {
          requestAnimationFrame(function () { f.style.height = target + '%'; });
        });
      }(fill, h));
    });
  }

  function renderPool(participants, pool) {
    elBars.innerHTML = '';
    elTotal.textContent = pool ? '(' + pool + ' losów)' : '';
    if (!participants.length) {
      elEmpty.style.display = '';
      elBars.style.display = 'none';
      return;
    }
    elEmpty.style.display = 'none';
    elBars.style.display = '';
    var maxT = 0;
    participants.forEach(function (p) { if (p.tickets > maxT) maxT = p.tickets; });
    participants.forEach(function (p) {
      var barPct = maxT > 0 ? Math.round((p.tickets / maxT) * 100) : 0;
      var bar = document.createElement('div');
      bar.className = 'ca-bar';

      var name = document.createElement('div');
      name.className = 'ca-bar-name';
      name.title = p.name;
      name.textContent = p.name;
      if (p.excluded) {
        name.insertAdjacentHTML('beforeend', '<span class="ca-excl-badge">wykluczony</span>');
      }
      if (p.user_id) {
        name.classList.add('ca-bar-name--clickable');
        name.setAttribute('role', 'button');
        name.setAttribute('tabindex', '0');
        name.title = p.name + ' — pokaż losowania';
        (function (uid, nm) {
          function open() { openUserSpins(uid, nm); }
          name.addEventListener('click', open);
          name.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
          });
        }(p.user_id, p.name));
      }

      var track = document.createElement('div');
      track.className = 'ca-bar-track';
      var fill = document.createElement('div');
      fill.className = 'ca-bar-fill';
      fill.style.width = '0%';
      track.appendChild(fill);

      var pct = document.createElement('div');
      pct.className = 'ca-bar-pct';
      pct.textContent = p.tickets + ' los. • ' + Number(p.chance_pct).toFixed(1) + '%';

      bar.appendChild(name); bar.appendChild(track); bar.appendChild(pct);
      elBars.appendChild(bar);

      (function (f, target) {
        requestAnimationFrame(function () {
          requestAnimationFrame(function () { f.style.width = target + '%'; });
        });
      }(fill, barPct));
    });
  }

  function loadAndOpen(cid, name) {
    currentCid = cid;
    elName.textContent = name || '';
    elChart.innerHTML = '';
    elBars.innerHTML = '';
    openModal();
    fetch('/admin/konkursy/' + cid + '/rozklad', { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data || !data.success) { toast('Nie udało się pobrać rozkładu.', 'error'); closeModal(); return; }
        renderChart(data.spin_buckets, data.config, data.spin_count);
        renderPool(data.participants, data.pool);
      })
      .catch(function () { toast('Błąd sieci — spróbuj ponownie.', 'error'); closeModal(); });
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.ca-action--dist');
    if (btn) { loadAndOpen(btn.getAttribute('data-cid'), btn.getAttribute('data-name')); return; }
    // Minimodal ma pierwszeństwo (leży nad rozkładem)
    if (e.target === uspinsModal || e.target.closest('#uspinsClose')) { closeUserSpins(); return; }
    if (e.target === modal || e.target.closest('#distClose')) { closeModal(); }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    if (uspinsModal && uspinsModal.classList.contains('active')) { closeUserSpins(); return; }
    if (modal.classList.contains('active')) closeModal();
  });
}());
