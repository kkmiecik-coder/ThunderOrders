/**
 * contest-form.js — Admin contest form
 * - Debounced product search (multi-picker: dodaj do zestawu)
 * - Quantity steppers + remove for selected prizes
 * - Image dropzone (drag-drop + click to select, preview)
 * - Criteria checkbox toggles (zachowane bez zmian)
 * Vanilla JS, no inline scripts.
 */
(function () {
  'use strict';

  /* ---------------------------------------------------------------------- */
  /* Multi-product prize picker                                               */
  /* ---------------------------------------------------------------------- */

  var prizeSearch = document.getElementById('prizeSearch');
  var prizeResults = document.getElementById('prizeResults');
  var prizeSelected = document.getElementById('prizeSelected');

  if (prizeSearch && prizeResults && prizeSelected) {
    var debounceTimer = null;

    function debounce(fn, delay) {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(fn, delay);
    }

    /** Sprawdza czy produkt o danym id jest już wybrany. */
    function isAlreadySelected(id) {
      return !!prizeSelected.querySelector('[data-id="' + id + '"]');
    }

    /** Buduje wiersz wybranego produktu i dodaje do #prizeSelected. */
    function addPrize(id, name, imageUrl) {
      if (isAlreadySelected(id)) {
        var existing = prizeSelected.querySelector('[data-id="' + id + '"] .ca-stepper-inp');
        if (existing) { existing.focus(); }
        return;
      }

      var item = document.createElement('div');
      item.className = 'ca-prize-item';
      item.setAttribute('data-id', id);

      // Thumbnail
      if (imageUrl) {
        var thumb = document.createElement('img');
        thumb.className = 'ca-prize-thumb';
        thumb.src = imageUrl;
        thumb.alt = '';
        item.appendChild(thumb);
      } else {
        var placeholder = document.createElement('div');
        placeholder.className = 'ca-prize-thumb-placeholder';
        placeholder.textContent = '📦';
        item.appendChild(placeholder);
      }

      // Nazwa
      var nameEl = document.createElement('span');
      nameEl.className = 'ca-prize-name';
      nameEl.textContent = name;
      item.appendChild(nameEl);

      // Stepper
      var stepper = document.createElement('div');
      stepper.className = 'ca-prize-stepper';

      var btnMinus = document.createElement('button');
      btnMinus.type = 'button';
      btnMinus.className = 'ca-stepper-btn ca-stepper-minus';
      btnMinus.textContent = '−';

      var inp = document.createElement('input');
      inp.type = 'number';
      inp.className = 'ca-stepper-inp';
      inp.value = 1;
      inp.min = 1;

      var btnPlus = document.createElement('button');
      btnPlus.type = 'button';
      btnPlus.className = 'ca-stepper-btn ca-stepper-plus';
      btnPlus.textContent = '+';

      stepper.appendChild(btnMinus);
      stepper.appendChild(inp);
      stepper.appendChild(btnPlus);
      item.appendChild(stepper);

      // Remove
      var removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'ca-prize-remove';
      removeBtn.setAttribute('aria-label', 'Usuń');
      removeBtn.textContent = '×';
      item.appendChild(removeBtn);

      // Hidden inputs
      var hiddenId = document.createElement('input');
      hiddenId.type = 'hidden';
      hiddenId.name = 'prize_product_id[]';
      hiddenId.value = id;
      item.appendChild(hiddenId);

      var hiddenQty = document.createElement('input');
      hiddenQty.type = 'hidden';
      hiddenQty.name = 'prize_quantity[]';
      hiddenQty.value = 1;
      item.appendChild(hiddenQty);

      // Event: stepper
      btnMinus.addEventListener('click', function () {
        var v = parseInt(inp.value, 10) || 1;
        if (v > 1) { inp.value = v - 1; hiddenQty.value = v - 1; }
      });
      btnPlus.addEventListener('click', function () {
        var v = parseInt(inp.value, 10) || 1;
        inp.value = v + 1; hiddenQty.value = v + 1;
      });
      inp.addEventListener('input', function () {
        var v = parseInt(inp.value, 10);
        if (!v || v < 1) { v = 1; inp.value = 1; }
        hiddenQty.value = v;
      });

      // Event: remove
      removeBtn.addEventListener('click', function () {
        item.remove();
      });

      prizeSelected.appendChild(item);
    }

    // Bind steppers/remove for items pre-rendered by Jinja on edit
    (function bindExisting() {
      var items = prizeSelected.querySelectorAll('.ca-prize-item');
      items.forEach(function (item) {
        var inp = item.querySelector('.ca-stepper-inp');
        var hiddenQty = item.querySelector('input[name="prize_quantity[]"]');
        var btnMinus = item.querySelector('.ca-stepper-minus');
        var btnPlus = item.querySelector('.ca-stepper-plus');
        var removeBtn = item.querySelector('.ca-prize-remove');
        if (btnMinus) {
          btnMinus.addEventListener('click', function () {
            var v = parseInt(inp.value, 10) || 1;
            if (v > 1) { inp.value = v - 1; if (hiddenQty) hiddenQty.value = v - 1; }
          });
        }
        if (btnPlus) {
          btnPlus.addEventListener('click', function () {
            var v = parseInt(inp.value, 10) || 1;
            inp.value = v + 1; if (hiddenQty) hiddenQty.value = v + 1;
          });
        }
        if (inp) {
          inp.addEventListener('input', function () {
            var v = parseInt(inp.value, 10);
            if (!v || v < 1) { v = 1; inp.value = 1; }
            if (hiddenQty) hiddenQty.value = v;
          });
        }
        if (removeBtn) {
          removeBtn.addEventListener('click', function () { item.remove(); });
        }
      });
    }());

    function renderPickerResults(products) {
      prizeResults.innerHTML = '';
      if (!products || products.length === 0) {
        var hint = document.createElement('div');
        hint.className = 'ca-picker-hint';
        hint.textContent = 'Brak wyników.';
        prizeResults.appendChild(hint);
        return;
      }
      products.forEach(function (p) {
        var row = document.createElement('div');
        row.className = 'ca-picker-result';
        if (isAlreadySelected(p.id)) {
          row.classList.add('ca-picker-result--selected');
        }
        row.setAttribute('data-id', p.id);
        row.setAttribute('data-name', p.name);

        var thumb;
        if (p.image_url) {
          thumb = document.createElement('img');
          thumb.className = 'ca-picker-thumb';
          thumb.src = p.image_url;
          thumb.alt = '';
        } else {
          thumb = document.createElement('div');
          thumb.className = 'ca-picker-thumb-placeholder';
          thumb.textContent = '📦';
        }

        var meta = document.createElement('div');
        var nameEl = document.createElement('div');
        nameEl.className = 'ca-picker-meta';
        nameEl.textContent = p.name;
        var sub = document.createElement('div');
        sub.className = 'ca-picker-meta-sub';
        var parts = [];
        if (p.sku) parts.push('SKU ' + p.sku);
        if (p.price !== undefined && p.price !== null) parts.push(p.price + ' zł');
        sub.textContent = parts.join(' • ');
        meta.appendChild(nameEl);
        meta.appendChild(sub);
        row.appendChild(thumb);
        row.appendChild(meta);

        row.addEventListener('click', function () {
          addPrize(p.id, p.name, p.image_url || null);
          // Update selected state in results
          prizeResults.querySelectorAll('.ca-picker-result').forEach(function (r) {
            if (r.getAttribute('data-id') == p.id) {
              r.classList.add('ca-picker-result--selected');
            }
          });
        });

        prizeResults.appendChild(row);
      });
    }

    function searchProducts(q) {
      if (q.length < 2) {
        prizeResults.innerHTML = '<div class="ca-picker-hint">Wpisz co najmniej 2 znaki, by wyszukać produkt.</div>';
        return;
      }
      prizeResults.innerHTML = '<div class="ca-picker-loading">Wyszukiwanie…</div>';
      fetch('/api/products/search?q=' + encodeURIComponent(q), {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.success) {
            renderPickerResults(data.products);
          } else {
            prizeResults.innerHTML = '<div class="ca-picker-hint">Błąd wyszukiwania.</div>';
          }
        })
        .catch(function () {
          prizeResults.innerHTML = '<div class="ca-picker-hint">Błąd połączenia.</div>';
        });
    }

    prizeSearch.addEventListener('input', function () {
      var q = prizeSearch.value.trim();
      debounce(function () { searchProducts(q); }, 280);
    });
  }

  /* ---------------------------------------------------------------------- */
  /* Image dropzone                                                           */
  /* ---------------------------------------------------------------------- */

  var imageDrop = document.getElementById('imageDrop');
  var imageFile = document.getElementById('imageFile');
  var imagePreview = document.getElementById('imagePreview');
  var imageDropPrompt = document.getElementById('imageDropPrompt');
  var imageDropError = document.getElementById('imageDropError');

  var ALLOWED_EXTS = ['png', 'jpg', 'jpeg', 'gif', 'webp'];

  function isAllowedFile(filename) {
    var ext = filename.split('.').pop().toLowerCase();
    return ALLOWED_EXTS.indexOf(ext) !== -1;
  }

  function showPreview(file) {
    if (!isAllowedFile(file.name)) {
      imageDropError.textContent = 'Niedozwolony format. Dozwolone: PNG, JPG, GIF, WEBP.';
      return;
    }
    imageDropError.textContent = '';
    var reader = new FileReader();
    reader.onload = function (e) {
      imagePreview.src = e.target.result;
      imagePreview.style.display = '';
      if (imageDropPrompt) imageDropPrompt.classList.add('ca-image-drop-prompt--hidden');
    };
    reader.readAsDataURL(file);
  }

  if (imageDrop && imageFile) {
    // Click on drop area → open file picker
    imageDrop.addEventListener('click', function (e) {
      if (e.target !== imageFile) {
        imageFile.click();
      }
    });

    // File input change
    imageFile.addEventListener('change', function () {
      if (imageFile.files && imageFile.files[0]) {
        showPreview(imageFile.files[0]);
      }
    });

    // Dragover
    imageDrop.addEventListener('dragover', function (e) {
      e.preventDefault();
      imageDrop.classList.add('ca-image-drop--dragover');
    });

    imageDrop.addEventListener('dragleave', function () {
      imageDrop.classList.remove('ca-image-drop--dragover');
    });

    // Drop
    imageDrop.addEventListener('drop', function (e) {
      e.preventDefault();
      imageDrop.classList.remove('ca-image-drop--dragover');
      var files = e.dataTransfer && e.dataTransfer.files;
      if (files && files[0]) {
        // Assign to input via DataTransfer
        try {
          var dt = new DataTransfer();
          dt.items.add(files[0]);
          imageFile.files = dt.files;
        } catch (err) {
          // Fallback — preview only (some browsers may not support reassigning files)
        }
        showPreview(files[0]);
      }
    });
  }

  /* ---------------------------------------------------------------------- */
  /* Criteria toggles                                                         */
  /* ---------------------------------------------------------------------- */

  // Derived from DOM so it always matches the number of [data-crit-row] elements in form.html.
  var critRows = document.querySelectorAll('[data-crit-row]');
  var NUM_CRITS = critRows.length;

  function syncCrit(idx) {
    var box = document.getElementById('critBox' + idx);
    var text = document.getElementById('critText' + idx);
    var inp = document.getElementById('critInp' + idx);
    if (!box || !text || !inp) return;
    var active = inp.value !== '' && inp.value !== null;
    setCritState(idx, active);
  }

  function setCritState(idx, active) {
    var box = document.getElementById('critBox' + idx);
    var text = document.getElementById('critText' + idx);
    var inp = document.getElementById('critInp' + idx);
    if (!box || !text || !inp) return;
    if (active) {
      box.classList.add('ca-cbox--on');
      box.textContent = '✓';
      text.classList.remove('ca-ctext--off');
      inp.classList.remove('ca-cinp--disabled');
      inp.disabled = false;
    } else {
      box.classList.remove('ca-cbox--on');
      box.textContent = '';
      text.classList.add('ca-ctext--off');
      inp.classList.add('ca-cinp--disabled');
      inp.disabled = true;
      inp.value = '';
    }
    // Keep aria-checked in sync on the row element
    var row = box.closest('[data-crit-row]');
    if (row) row.setAttribute('aria-checked', active ? 'true' : 'false');
  }

  function toggleCrit(idx) {
    var inp = document.getElementById('critInp' + idx);
    if (!inp) return;
    var isActive = !inp.classList.contains('ca-cinp--disabled');
    setCritState(idx, !isActive);
    if (!isActive) {
      // Became active — focus input
      setTimeout(function () { inp.focus(); }, 10);
    }
  }

  // Attach click and keyboard handlers to each criteria row
  for (var i = 0; i < critRows.length; i++) {
    (function (idx, row) {
      row.addEventListener('click', function (e) {
        var inp = document.getElementById('critInp' + idx);
        if (!inp) return;
        // If user clicked the input itself, don't toggle
        if (e.target === inp) return;
        toggleCrit(idx);
      });

      // Keyboard accessibility: Enter/Space toggle the criterion
      row.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault(); // prevent page scroll on Space
          toggleCrit(idx);
        }
      });
    }(i, critRows[i]));
  }

  // Sync initial state on load
  for (var j = 0; j < NUM_CRITS; j++) {
    syncCrit(j);
  }

}());
