// ImageNinja - tools.js
// Dropzone + form submit + model status + auto-download + compare slider

(function () {
  'use strict';

  // ----- Helpers -----
  function humanSize(n) {
    if (n < 1024) return n + ' B';
    const units = ['KB', 'MB', 'GB'];
    let v = n / 1024;
    let i = 0;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return v.toFixed(1) + ' ' + units[i];
  }

  function readImageDims(file) {
    return new Promise(function (resolve) {
      if (!file.type || !file.type.startsWith('image/')) {
        resolve({ w: null, h: null });
        return;
      }
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = function () {
        const w = img.naturalWidth, h = img.naturalHeight;
        URL.revokeObjectURL(url);
        resolve({ w: w, h: h });
      };
      img.onerror = function () {
        URL.revokeObjectURL(url);
        resolve({ w: null, h: null });
      };
      img.src = url;
    });
  }

  // Download via blob URL. WebView2 (pywebview) y algunos browsers
  // ignoran el atributo `download` de <a>, asi que forzamos la descarga
  // trayendo el archivo como blob y disparando un click programatico.
  function downloadViaBlob(url, filename) {
    return fetch(url)
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.blob();
      })
      .then(function (blob) {
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = filename;
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(blobUrl); }, 4000);
      });
  }

  // ----- Dropzone -----
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');
  const previewBox = document.getElementById('dropzone-preview');
  const dropContent = dropzone ? dropzone.querySelector('.dropzone-content') : null;

  let selectedFiles = [];
  let previews = [];

  function renderPreviews() {
    if (!previewBox) return;
    previewBox.innerHTML = '';
    if (selectedFiles.length === 0) {
      previewBox.hidden = true;
      if (dropContent) dropContent.hidden = false;
      dropzone.classList.remove('has-files');
      return;
    }
    previewBox.hidden = false;
    if (dropContent) dropContent.hidden = true;
    dropzone.classList.add('has-files');

    previews.forEach(function (p, idx) {
      const card = document.createElement('div');
      card.className = 'preview-card';

      const img = document.createElement('img');
      img.src = p.url;
      img.alt = p.file.name;
      card.appendChild(img);

      const info = document.createElement('div');
      info.className = 'preview-info';
      const name = document.createElement('strong');
      name.textContent = p.file.name;
      const meta = document.createElement('span');
      if (p.w && p.h) {
        meta.textContent = p.w + 'x' + p.h + ' \u00b7 ' + humanSize(p.file.size);
      } else {
        meta.textContent = humanSize(p.file.size);
      }
      info.appendChild(name);
      info.appendChild(meta);
      card.appendChild(info);

      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'preview-remove';
      remove.setAttribute('aria-label', 'Quitar ' + p.file.name);
      remove.textContent = '\u00d7';
      remove.addEventListener('click', function (e) {
        e.stopPropagation();
        selectedFiles.splice(idx, 1);
        URL.revokeObjectURL(p.url);
        previews.splice(idx, 1);
        renderPreviews();
        if (fileInput) fileInput.value = '';
      });
      card.appendChild(remove);

      previewBox.appendChild(card);
    });
  }

  async function addFiles(files) {
    const accepted = ['image/png', 'image/jpeg', 'image/webp', 'image/bmp', 'image/tiff'];
    for (const file of files) {
      if (selectedFiles.some(function (f) { return f.name === file.name && f.size === file.size; })) {
        continue;
      }
      if (file.type && accepted.indexOf(file.type) === -1 && !file.name.match(/\.(png|jpg|jpeg|webp|bmp|tif|tiff)$/i)) {
        continue;
      }
      if (file.size > 100 * 1024 * 1024) {
        alert('La imagen "' + file.name + '" supera 100 MB. Skipeada.');
        continue;
      }
      const url = URL.createObjectURL(file);
      const dims = await readImageDims(file);
      previews.push({ file: file, url: url, w: dims.w, h: dims.h });
      selectedFiles.push(file);
    }
    renderPreviews();
  }

  if (dropzone && fileInput) {
    dropzone.addEventListener('click', function (e) {
      if (e.target.closest('.preview-remove')) return;
      fileInput.click();
    });
    fileInput.addEventListener('change', function (e) {
      const files = Array.from(e.target.files || []);
      if (files.length) addFiles(files);
    });
    ['dragenter', 'dragover'].forEach(function (ev) {
      dropzone.addEventListener(ev, function (e) {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.add('drag-over');
      });
    });
    ['dragleave', 'drop'].forEach(function (ev) {
      dropzone.addEventListener(ev, function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (ev === 'dragleave' && e.target !== dropzone) return;
        dropzone.classList.remove('drag-over');
      });
    });
    dropzone.addEventListener('drop', function (e) {
      const dt = e.dataTransfer;
      if (!dt) return;
      const files = Array.from(dt.files || []);
      if (files.length) addFiles(files);
    });
  }

  // ----- Custom scale toggle -----
  const scaleSel = document.getElementById('scale');
  const scaleCustom = document.getElementById('scale-custom');
  if (scaleSel && scaleCustom) {
    scaleSel.addEventListener('change', function () {
      if (scaleSel.value === 'custom') {
        scaleCustom.hidden = false;
        scaleCustom.focus();
      } else {
        scaleCustom.hidden = true;
      }
    });
  }

  // ----- Quality field visibility -----
  const fmtSel = document.getElementById('format');
  const qualityField = document.getElementById('quality-field');
  function updateQualityVisibility() {
    if (!fmtSel || !qualityField) return;
    const v = fmtSel.value;
    qualityField.style.display = (v === 'png') ? 'none' : 'flex';
  }
  if (fmtSel) {
    fmtSel.addEventListener('change', updateQualityVisibility);
    updateQualityVisibility();
  }

  // ----- Model status + auto-download -----
  const modelDot = document.getElementById('model-dot');
  const modelText = document.getElementById('model-text');
  const downloadBtn = document.getElementById('download-model-btn');

  function setModelState(state, text) {
    if (!modelDot || !modelText) return;
    modelDot.className = 'model-dot ' + state;
    modelText.innerHTML = text;
  }

  async function checkModel() {
    if (!modelDot) return;
    try {
      setModelState('loading', 'Verificando modelo IA...');
      const r = await fetch('/api/model/status');
      if (!r.ok) throw new Error('status ' + r.status);
      const s = await r.json();
      if (!s.deps_ok) {
        setModelState('error',
          'Dependencias IA no instaladas. <strong>Instalalas con</strong>: <code>pip install basicsr realesrgan torch</code>');
        if (downloadBtn) downloadBtn.hidden = true;
        return;
      }
      if (s.exists) {
        setModelState('ready',
          'IA lista: <strong>' + s.filename + '</strong> (' + s.size_mb + ' MB / esperado ' + s.expected_mb + ' MB)');
        if (downloadBtn) downloadBtn.hidden = true;
      } else {
        setModelState('error',
          'Modelo IA no descargado (~' + s.expected_mb + ' MB). ' +
          '<strong>Click en "Descargar modelo"</strong> para obtener la maxima calidad.');
        if (downloadBtn) downloadBtn.hidden = false;
      }
    } catch (e) {
      setModelState('error', 'No se pudo verificar el modelo: ' + e.message);
    }
  }

  async function downloadModel() {
    if (!downloadBtn) return;
    downloadBtn.disabled = true;
    setModelState('loading', 'Descargando modelo (~64 MB)... Esto puede tardar unos minutos.');
    try {
      const r = await fetch('/api/model/download', { method: 'POST' });
      if (!r.ok) {
        const data = await r.json().catch(function () { return {}; });
        throw new Error(data.error || ('HTTP ' + r.status));
      }
      const data = await r.json();
      if (data.ok) {
        setModelState('ready',
          'IA lista: <strong>' + data.path.split(/[\\\\/]/).pop() + '</strong> (' + data.size_mb + ' MB)');
        if (downloadBtn) downloadBtn.hidden = true;
      } else {
        throw new Error('Descarga sin OK');
      }
    } catch (e) {
      setModelState('error', 'Descarga fallo: ' + e.message);
      downloadBtn.disabled = false;
    }
  }

  if (downloadBtn) downloadBtn.addEventListener('click', downloadModel);
  checkModel();

  // ----- Submit -----
  const form = document.getElementById('upscale-form');
  const submitBtn = document.getElementById('submit-btn');
  const resetBtn = document.getElementById('reset-btn');
  const statusBox = document.getElementById('status');
  const statusText = document.getElementById('status-text');
  const progressBar = document.getElementById('progress-bar');
  const resultBox = document.getElementById('result');
  const resultList = document.getElementById('result-list');

  function setStatus(percent, text) {
    if (progressBar) {
      // Usamos transform: scaleX (no causa reflow, no triggerea layout-transition)
      const scale = Math.max(0, Math.min(100, percent)) / 100;
      progressBar.style.transform = 'scaleX(' + scale + ')';
    }
    if (statusText) statusText.textContent = text;
  }

  function resetUI() {
    selectedFiles = [];
    previews.forEach(function (p) { URL.revokeObjectURL(p.url); });
    previews = [];
    renderPreviews();
    if (fileInput) fileInput.value = '';
    if (statusBox) statusBox.hidden = true;
    if (resultBox) resultBox.hidden = true;
    if (resultList) resultList.innerHTML = '';
    setStatus(0, '');
  }

  if (resetBtn) resetBtn.addEventListener('click', resetUI);

  function getMethod() {
    const preset = document.querySelector('input[name="quality_preset"]:checked');
    return preset ? preset.value : 'best';
  }

  const QUALITY_LABEL = {
    best: 'Maxima calidad (IA + denoise + sharpen)',
    realesrgan: 'IA Real-ESRGAN',
    lanczos: 'Lanczos clasico',
  };

  if (form) {
    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      if (selectedFiles.length === 0) {
        alert('Arrastra al menos una imagen para empezar.');
        return;
      }
      submitBtn.disabled = true;
      if (resetBtn) resetBtn.hidden = false;
      if (statusBox) statusBox.hidden = false;
      if (resultBox) resultBox.hidden = true;
      if (resultList) resultList.innerHTML = '';

      const method = getMethod();
      setStatus(10, 'Subiendo ' + selectedFiles.length + (selectedFiles.length === 1 ? ' imagen' : ' imagenes') + '...');

      const fd = new FormData();
      selectedFiles.forEach(function (f) { fd.append('file', f, f.name); });
      const target = (document.getElementById('target') || {}).value || '';
      const fmt = (document.getElementById('format') || {}).value || 'png';
      const quality = parseInt(((document.querySelector('input[name="quality"]') || {}).value || '95'), 10);
      let scale = parseFloat((document.getElementById('scale') || {}).value || '4');
      if (scaleSel && scaleSel.value === 'custom' && scaleCustom) {
        scale = parseFloat(scaleCustom.value || '2');
      }
      fd.append('method', method);
      fd.append('scale', String(scale));
      fd.append('target', target);
      fd.append('format', fmt);
      fd.append('quality', String(quality));

      try {
        setStatus(30, 'Procesando con ' + (QUALITY_LABEL[method] || method) + '...');
        const resp = await fetch('/api/upscale', { method: 'POST', body: fd });
        setStatus(80, 'Guardando resultado...');

        if (!resp.ok) {
          let msg = 'Error ' + resp.status;
          try {
            const data = await resp.json();
            if (data && data.error) msg = data.error;
          } catch (e) { /* ignore */ }
          throw new Error(msg);
        }

        const ct = resp.headers.get('content-type') || '';
        if (ct.indexOf('application/json') !== -1) {
          const data = await resp.json();
          setStatus(95, 'Generando descarga...');
          if (data.ok && data.files && data.files[0]) {
            const f = data.files[0];
            renderSingleResult(f);
            setStatus(100, 'Listo.');
          } else {
            throw new Error('Respuesta inesperada del servidor');
          }
        } else {
          const blob = await resp.blob();
          const cd = resp.headers.get('content-disposition') || '';
          let name = 'imageninja_batch.zip';
          const m = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
          if (m) name = m[1];
          setStatus(95, 'Generando descarga...');
          renderBatchResult(blob, name, selectedFiles.length);
          setStatus(100, 'Listo.');
        }

        if (resultBox) resultBox.hidden = false;
      } catch (err) {
        setStatus(0, 'Error: ' + (err.message || err));
        submitBtn.disabled = false;
        return;
      }

      submitBtn.disabled = false;
    });
  }

  function getOriginalDataURL(idx) {
    const p = previews[idx];
    return p ? p.url : '';
  }

  function renderSingleResult(file) {
    if (!resultList) return;
    resultList.innerHTML = '';

    // ========== Comparison panel (slider) ==========
    const compare = document.createElement('div');
    compare.className = 'compare';

    // Encabezado
    const compareHead = document.createElement('div');
    compareHead.className = 'compare-head';
    compareHead.innerHTML =
      '<h4>Antes / Despues</h4>' +
      '<div class="compare-meta">' +
        '<span class="compare-pill before">Original ' + (file.width_original || '?') + 'x' + (file.height_original || '?') + '</span>' +
        '<span class="compare-arrow">\u2192</span>' +
        '<span class="compare-pill after">Resultado ' + file.width + 'x' + file.height + '</span>' +
        '<span class="compare-pill method">' + (QUALITY_LABEL[file.method] || file.method) + '</span>' +
        '<span class="compare-pill">factor ' + (file.scale_factor || '?') + 'x</span>' +
      '</div>';
    compare.appendChild(compareHead);

    // Slider container
    const slider = document.createElement('div');
    slider.className = 'compare-slider';
    slider.setAttribute('role', 'group');
    slider.setAttribute('aria-label', 'Comparacion antes y despues. Arrastra el divisor.');

    const imgBefore = document.createElement('img');
    imgBefore.className = 'compare-img before';
    imgBefore.src = getOriginalDataURL(0);
    imgBefore.alt = 'Original';
    imgBefore.draggable = false;

    const imgAfter = document.createElement('img');
    imgAfter.className = 'compare-img after';
    imgAfter.src = '/outputs/' + encodeURIComponent(file.filename);
    imgAfter.alt = 'Resultado';
    imgAfter.draggable = false;
    imgAfter.addEventListener('load', function () {
      // Una vez cargada, podemos usar su URL para el blob download
    });

    // Overlay "Resultado" recortado (clip-path)
    const overlay = document.createElement('div');
    overlay.className = 'compare-overlay';

    const overlayImg = document.createElement('img');
    overlayImg.src = '/outputs/' + encodeURIComponent(file.filename);
    overlayImg.alt = '';
    overlayImg.draggable = false;

    const labelBefore = document.createElement('span');
    labelBefore.className = 'compare-label before';
    labelBefore.textContent = 'Original';

    const labelAfter = document.createElement('span');
    labelAfter.className = 'compare-label after';
    labelAfter.textContent = 'Resultado';

    const handle = document.createElement('button');
    handle.type = 'button';
    handle.className = 'compare-handle';
    handle.setAttribute('aria-label', 'Arrastra para comparar');
    handle.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">' +
      '<path fill="currentColor" d="M8 5l-5 7 5 7v-4h8v4l5-7-5-7v4H8V5z"/>' +
      '</svg>';

    overlay.appendChild(overlayImg);
    // Labels van FUERA del overlay para que el clip-path no las recorte
    slider.appendChild(imgBefore);
    slider.appendChild(overlay);
    slider.appendChild(labelBefore);
    slider.appendChild(labelAfter);
    slider.appendChild(handle);
    compare.appendChild(slider);

    // Compare slider logic
    let pos = 50; // %
    function applyPos() {
      overlay.style.clipPath = 'inset(0 0 0 ' + pos + '%)';
      handle.style.left = pos + '%';
    }
    applyPos();

    function startDrag(clientX) {
      const rect = slider.getBoundingClientRect();
      function onMove(ev) {
        const x = (ev.touches ? ev.touches[0].clientX : ev.clientX) - rect.left;
        pos = Math.max(0, Math.min(100, (x / rect.width) * 100));
        applyPos();
      }
      function onEnd() {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onEnd);
        document.removeEventListener('touchmove', onMove);
        document.removeEventListener('touchend', onEnd);
      }
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onEnd);
      document.addEventListener('touchmove', onMove, { passive: false });
      document.addEventListener('touchend', onEnd);
    }
    handle.addEventListener('mousedown', function (e) { e.preventDefault(); startDrag(e.clientX); });
    handle.addEventListener('touchstart', function (e) { e.preventDefault(); startDrag(e.touches[0].clientX); }, { passive: false });
    slider.addEventListener('click', function (e) {
      if (e.target === handle) return;
      const rect = slider.getBoundingClientRect();
      pos = Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100));
      applyPos();
    });

    resultList.appendChild(compare);

    // ========== Acciones: descargar + procesar otra ==========
    const actions = document.createElement('div');
    actions.className = 'result-actions';

    const dl = document.createElement('button');
    dl.type = 'button';
    dl.className = 'btn btn-primary';
    dl.textContent = 'Descargar ' + file.filename;
    dl.addEventListener('click', function () {
      dl.disabled = true;
      const orig = dl.textContent;
      dl.textContent = 'Descargando...';
      downloadViaBlob('/outputs/' + encodeURIComponent(file.filename), file.filename)
        .catch(function (err) {
          alert('No se pudo descargar: ' + err.message);
        })
        .finally(function () {
          dl.disabled = false;
          dl.textContent = orig;
        });
    });

    const newBtn = document.createElement('button');
    newBtn.type = 'button';
    newBtn.className = 'btn btn-ghost';
    newBtn.textContent = 'Procesar otra';
    newBtn.addEventListener('click', resetUI);

    actions.appendChild(dl);
    actions.appendChild(newBtn);
    resultList.appendChild(actions);
  }

  function renderBatchResult(blob, name, count) {
    if (!resultList) return;
    resultList.innerHTML = '';
    const item = document.createElement('div');
    item.className = 'result-item';

    const thumb = document.createElement('div');
    thumb.className = 'result-thumb';
    thumb.style.display = 'flex';
    thumb.style.alignItems = 'center';
    thumb.style.justifyContent = 'center';
    thumb.style.background = 'var(--accent-cyan-soft)';
    thumb.style.color = 'var(--primary)';
    thumb.style.fontSize = '22px';
    thumb.style.fontWeight = '700';
    thumb.textContent = count + '';
    item.appendChild(thumb);

    const info = document.createElement('div');
    info.className = 'result-info';
    const nameEl = document.createElement('p');
    nameEl.className = 'result-name';
    nameEl.textContent = name;
    const meta = document.createElement('div');
    meta.className = 'result-meta';
    meta.innerHTML = '<strong>' + count + '</strong> imagenes mejoradas &middot; formato .zip';
    info.appendChild(nameEl);
    info.appendChild(meta);
    item.appendChild(info);

    const dl = document.createElement('button');
    dl.type = 'button';
    dl.className = 'btn btn-primary result-download';
    dl.textContent = 'Descargar .zip';
    dl.addEventListener('click', function () {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = name;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
    });
    item.appendChild(dl);

    resultList.appendChild(item);
  }
})();
