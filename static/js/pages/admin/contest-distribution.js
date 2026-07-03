/* Modal „Rozkład punktów" na liście konkursów (/admin/konkursy). */
(function () {
  'use strict';

  var modal = document.getElementById('distModal');
  if (!modal) return;

  var elName = document.getElementById('distName');
  var elChart = document.getElementById('distChart');
  var elMin = document.getElementById('distMin');
  var elMax = document.getElementById('distMax');
  var elBars = document.getElementById('distBars');
  var elEmpty = document.getElementById('distEmpty');
  var elTotal = document.getElementById('distTotal');

  function toast(msg, type) {
    if (typeof window.showToast === 'function') window.showToast(msg, type || 'error');
  }

  function openModal() { modal.classList.add('active'); modal.setAttribute('aria-hidden', 'false'); }
  function closeModal() { modal.classList.remove('active'); modal.setAttribute('aria-hidden', 'true'); }

  function renderChart(buckets, config) {
    elChart.innerHTML = '';
    var maxPct = 0;
    buckets.forEach(function (b) { if (b.pct > maxPct) maxPct = b.pct; });
    buckets.forEach(function (b) {
      var h = maxPct > 0 ? Math.round((b.pct / maxPct) * 100) : 0;
      var col = document.createElement('div');
      col.className = 'ca-dist-bar';
      col.title = b.label + ' losów • ' + b.pct.toFixed(1) + '%';
      var fill = document.createElement('div');
      fill.className = 'ca-dist-bar-fill';
      fill.style.height = '0%';
      col.appendChild(fill);
      elChart.appendChild(col);
      (function (f, target) {
        requestAnimationFrame(function () {
          requestAnimationFrame(function () { f.style.height = target + '%'; });
        });
      }(fill, h));
    });
    elMin.textContent = config.ticket_min + ' los.';
    elMax.textContent = config.ticket_max + ' los.';
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
    elName.textContent = name || '';
    elChart.innerHTML = '';
    elBars.innerHTML = '';
    openModal();
    fetch('/admin/konkursy/' + cid + '/rozklad', { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data || !data.success) { toast('Nie udało się pobrać rozkładu.', 'error'); closeModal(); return; }
        renderChart(data.spin_buckets, data.config);
        renderPool(data.participants, data.pool);
      })
      .catch(function () { toast('Błąd sieci — spróbuj ponownie.', 'error'); closeModal(); });
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.ca-action--dist');
    if (btn) { loadAndOpen(btn.getAttribute('data-cid'), btn.getAttribute('data-name')); return; }
    if (e.target === modal || e.target.closest('#distClose')) { closeModal(); }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && modal.classList.contains('active')) closeModal();
  });
}());
