// ImageNinja - metadata.js
// Dropzone + extraccion de metadatos + render del panel + descarga JSON

(function () {
  'use strict';

  // ----- Helpers -----
  function humanSize(n) {
    if (n < 1024) return n + ' B';
    const units = ['KB', 'MB', 'GB'];
    let v = n / 1024;
    let i = 0;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return v.toFixed(2) + ' ' + units[i];
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
        URL.revokeObjectURL(url);
        resolve({ w: img.naturalWidth, h: img.naturalHeight });
      };
      img.onerror = function () {
        URL.revokeObjectURL(url);
        resolve({ w: null, h: null });
      };
      img.src = url;
    });
  }

  // ----- Dropzone (reusado del tools.js, simplificado) -----
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');
  const previewBox = document.getElementById('dropzone-preview');
  const dropContent = dropzone ? dropzone.querySelector('.dropzone-content') : null;

  let selectedFile = null;
  let previewUrl = null;
  let lastMetadata = null;

  function renderPreview() {
    if (!previewBox) return;
    previewBox.innerHTML = '';
    if (!selectedFile) {
      previewBox.hidden = true;
      if (dropContent) dropContent.hidden = false;
      dropzone.classList.remove('has-files');
      return;
    }
    previewBox.hidden = false;
    if (dropContent) dropContent.hidden = true;
    dropzone.classList.add('has-files');

    const card = document.createElement('div');
    card.className = 'preview-card';

    const img = document.createElement('img');
    img.src = previewUrl;
    img.alt = selectedFile.name;
    card.appendChild(img);

    const info = document.createElement('div');
    info.className = 'preview-info';
    const name = document.createElement('strong');
    name.textContent = selectedFile.name;
    const meta = document.createElement('span');
    meta.textContent = humanSize(selectedFile.size);
    info.appendChild(name);
    info.appendChild(meta);
    card.appendChild(info);

    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'preview-remove';
    remove.setAttribute('aria-label', 'Quitar ' + selectedFile.name);
    remove.textContent = '\u00d7';
    remove.addEventListener('click', function (e) {
      e.stopPropagation();
      clearFile();
    });
    card.appendChild(remove);

    previewBox.appendChild(card);
  }

  function clearFile() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    selectedFile = null;
    previewUrl = null;
    if (fileInput) fileInput.value = '';
    renderPreview();
    const resultBox = document.getElementById('result');
    if (resultBox) resultBox.hidden = true;
    const statusBox = document.getElementById('status');
    if (statusBox) statusBox.hidden = true;
  }

  async function setFile(file) {
    if (!file) return;
    const accepted = ['image/png', 'image/jpeg', 'image/webp', 'image/bmp', 'image/tiff'];
    if (file.type && accepted.indexOf(file.type) === -1 && !file.name.match(/\.(png|jpg|jpeg|webp|bmp|tif|tiff)$/i)) {
      alert('Tipo de archivo no soportado.');
      return;
    }
    if (file.size > 100 * 1024 * 1024) {
      alert('La imagen supera 100 MB.');
      return;
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    selectedFile = file;
    previewUrl = URL.createObjectURL(file);
    await readImageDims(file);
    renderPreview();
    // Auto-procesar al subir
    extract();
  }

  if (dropzone && fileInput) {
    dropzone.addEventListener('click', function (e) {
      if (e.target.closest('.preview-remove')) return;
      fileInput.click();
    });
    fileInput.addEventListener('change', function (e) {
      const files = Array.from(e.target.files || []);
      if (files.length) setFile(files[0]);
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
      if (files.length) setFile(files[0]);
    });
  }

  // ----- Status helpers -----
  const statusBox = document.getElementById('status');
  const statusText = document.getElementById('status-text');
  const progressBar = document.getElementById('progress-bar');
  const resultBox = document.getElementById('result');
  const resultList = document.getElementById('result-list');

  function setStatus(percent, text) {
    if (progressBar) {
      const scale = Math.max(0, Math.min(100, percent)) / 100;
      progressBar.style.transform = 'scaleX(' + scale + ')';
    }
    if (statusText) statusText.textContent = text;
  }

  // ----- Submit (auto) -----
  async function extract() {
    if (!selectedFile) return;
    if (statusBox) statusBox.hidden = false;
    if (resultBox) resultBox.hidden = true;
    if (resultList) resultList.innerHTML = '';
    setStatus(20, 'Subiendo imagen...');

    const fd = new FormData();
    fd.append('file', selectedFile, selectedFile.name);

    try {
      setStatus(60, 'Leyendo metadatos EXIF, XMP, ICC...');
      const resp = await fetch('/api/metadata', { method: 'POST', body: fd });
      if (!resp.ok) {
        const data = await resp.json().catch(function () { return {}; });
        throw new Error(data.error || ('HTTP ' + resp.status));
      }
      const data = await resp.json();
      if (!data.ok) throw new Error(data.error || 'Respuesta no OK');
      setStatus(100, 'Listo.');
      lastMetadata = data.metadata;
      renderMetadata(data.metadata);
      if (resultBox) resultBox.hidden = false;
    } catch (err) {
      setStatus(0, 'Error: ' + (err.message || err));
    }
  }

  // ----- Render -----
  function el(tag, opts, children) {
    const e = document.createElement(tag);
    if (opts) {
      if (opts.cls) e.className = opts.cls;
      if (opts.text != null) e.textContent = opts.text;
      if (opts.html != null) e.innerHTML = opts.html;
      if (opts.attrs) for (const k in opts.attrs) e.setAttribute(k, opts.attrs[k]);
    }
    if (children) children.forEach(function (c) { e.appendChild(c); });
    return e;
  }

  function renderSection(title, rows, opts) {
    if (!rows || !rows.length) return null;
    const card = el('article', { cls: 'meta-card ' + (opts && opts.cls || '') });
    const head = el('header', { cls: 'meta-card-head' }, [
      el('h3', { text: title }),
      el('span', { cls: 'meta-count', text: String(rows.length) }),
    ]);
    card.appendChild(head);
    const list = el('dl', { cls: 'meta-list' });
    rows.forEach(function (r) {
      const dt = el('dt', { text: r.key });
      const dd = el('dd', { text: r.value });
      if (r.mono) dd.className = 'meta-mono';
      list.appendChild(dt);
      list.appendChild(dd);
    });
    card.appendChild(list);
    return card;
  }

  function renderFile(file) {
    const card = el('article', { cls: 'meta-card meta-file' });
    const head = el('header', { cls: 'meta-card-head' }, [
      el('h3', { text: 'Archivo' }),
    ]);
    card.appendChild(head);
    const list = el('dl', { cls: 'meta-list' });
    list.appendChild(el('dt', { text: 'Nombre' }));
    list.appendChild(el('dd', { text: file.name, attrs: { title: file.name } }));
    list.appendChild(el('dt', { text: 'Tamano' }));
    list.appendChild(el('dd', { text: file.size_human + ' (' + file.size_bytes.toLocaleString('es-CL') + ' B)' }));
    card.appendChild(list);
    return card;
  }

  function renderImage(img) {
    const rows = [
      { key: 'Dimensiones', value: img.width.toLocaleString('es-CL') + ' x ' + img.height.toLocaleString('es-CL') + ' px' },
      { key: 'Megapixeles', value: img.megapixels + ' MP' },
      { key: 'Aspect ratio', value: img.aspect_ratio },
      { key: 'Formato', value: img.format },
      { key: 'Modo de color', value: img.color_mode },
      { key: 'Modo', value: img.mode },
    ];
    if (img.dpi) {
      rows.push({ key: 'Resolucion', value: img.dpi[0] + ' x ' + img.dpi[1] + ' DPI' });
    }
    return renderSection('Imagen', rows, { cls: 'meta-image' });
  }

  function renderGps(gps) {
    if (!gps || !Object.keys(gps).length) return null;
    const card = el('article', { cls: 'meta-card meta-gps' });
    card.appendChild(el('header', { cls: 'meta-card-head' }, [
      el('h3', { text: 'Ubicacion (GPS)' }),
    ]));
    const list = el('dl', { cls: 'meta-list' });
    if (gps._decimal) {
      list.appendChild(el('dt', { text: 'Coordenadas' }));
      const dd = el('dd');
      dd.appendChild(el('span', { text: gps._decimal, attrs: { class: 'meta-mono' } }));
      if (gps._map_link) {
        const a = el('a', { text: 'Ver en Google Maps', attrs: {
          href: gps._map_link, target: '_blank', rel: 'noopener', class: 'meta-link'
        }});
        dd.appendChild(document.createTextNode(' '));
        dd.appendChild(a);
      }
      list.appendChild(dd);
    }
    if (gps.Latitude) {
      list.appendChild(el('dt', { text: 'Latitud' }));
      list.appendChild(el('dd', { text: gps.LatitudeRef ? gps.LatitudeRef + ' ' : '' + (gps._lat_dms || ''), attrs: { class: 'meta-mono' } }));
    }
    if (gps.Longitude) {
      list.appendChild(el('dt', { text: 'Longitud' }));
      list.appendChild(el('dd', { text: gps.LongitudeRef ? gps.LongitudeRef + ' ' : '' + (gps._lon_dms || ''), attrs: { class: 'meta-mono' } }));
    }
    if (gps.Altitude) {
      list.appendChild(el('dt', { text: 'Altitud' }));
      list.appendChild(el('dd', { text: gps.Altitude }));
    }
    if (gps.DateStamp) {
      list.appendChild(el('dt', { text: 'Fecha GPS' }));
      list.appendChild(el('dd', { text: gps.DateStamp }));
    }
    if (gps.TimeStamp) {
      list.appendChild(el('dt', { text: 'Hora GPS' }));
      list.appendChild(el('dd', { text: gps.TimeStamp }));
    }
    if (gps.ImgDirection) {
      list.appendChild(el('dt', { text: 'Direccion de la imagen' }));
      list.appendChild(el('dd', { text: gps.ImgDirection + (gps.ImgDirectionRef ? ' ' + gps.ImgDirectionRef : '') }));
    }
    if (gps.Speed) {
      list.appendChild(el('dt', { text: 'Velocidad' }));
      list.appendChild(el('dd', { text: gps.Speed + (gps.SpeedRef ? ' ' + gps.SpeedRef : '') }));
    }
    if (gps.GPSVersionID) {
      list.appendChild(el('dt', { text: 'Version GPS' }));
      list.appendChild(el('dd', { text: gps.GPSVersionID, attrs: { class: 'meta-mono' } }));
    }
    if (gps.HPositioningError) {
      list.appendChild(el('dt', { text: 'Error de posicionamiento' }));
      list.appendChild(el('dd', { text: gps.HPositioningError + ' m' }));
    }
    card.appendChild(list);
    return card;
  }

  function renderXmp(xmp) {
    if (!xmp || !xmp.length) return null;
    const rows = xmp.map(function (r) { return { key: r.key, value: r.value, mono: false }; });
    return renderSection('XMP / IPTC', rows, { cls: 'meta-xmp' });
  }

  function renderIcc(icc) {
    if (!icc) return null;
    return renderSection('Perfil de color', [
      { key: 'ICC Profile', value: icc, mono: false }
    ], { cls: 'meta-icc' });
  }

  function renderEmptyState() {
    const card = el('article', { cls: 'meta-card meta-empty' });
    card.appendChild(el('header', { cls: 'meta-card-head' }, [
      el('h3', { text: 'Sin metadatos' }),
    ]));
    const p = el('p', {
      text: 'Esta imagen no contiene tags EXIF, XMP ni perfil ICC. Es normal en PNGs exportados desde editores que limpian los metadatos, o en imagenes pequenas / generadas.'
    });
    card.appendChild(p);
    return card;
  }

  function renderMetadata(meta) {
    if (!resultList) return;
    resultList.innerHTML = '';

    // Header con stats rapidas
    const summary = el('header', { cls: 'meta-summary' });
    const exifCount = (meta.camera || []).length + (meta.settings || []).length
      + (meta.dates || []).length + (meta.author || []).length
      + (meta.description || []).length;
    const totalTags = (meta.exif_count || 0);
    const hasGps = meta.gps && Object.keys(meta.gps).length > 0;
    const hasXmp = meta.xmp && meta.xmp.length > 0;
    const stats = [
      el('span', { cls: 'meta-stat', text: totalTags + ' tags EXIF' }),
      el('span', { cls: 'meta-stat', text: (hasGps ? 'GPS' : 'Sin GPS') }),
      el('span', { cls: 'meta-stat', text: (hasXmp ? meta.xmp.length + ' XMP' : 'Sin XMP') }),
      el('span', { cls: 'meta-stat', text: (meta.icc ? 'ICC profile' : 'Sin ICC') }),
    ];
    stats.forEach(function (s) { summary.appendChild(s); });
    resultList.appendChild(summary);

    // Grid de cards
    const grid = el('div', { cls: 'meta-grid' });
    const cards = [
      renderFile(meta.file),
      renderImage(meta.image),
      renderSection('Camara', meta.camera, { cls: 'meta-camera' }),
      renderSection('Lente', meta.lens, { cls: 'meta-lens' }),
      renderSection('Configuracion', meta.settings, { cls: 'meta-settings' }),
      renderSection('Fechas', meta.dates, { cls: 'meta-dates' }),
      renderSection('Software', meta.software, { cls: 'meta-software' }),
      renderSection('Autor / Copyright', meta.author, { cls: 'meta-author' }),
      renderSection('Descripcion', meta.description, { cls: 'meta-description' }),
      renderGps(meta.gps),
      renderXmp(meta.xmp),
      renderIcc(meta.icc),
    ];
    let anyCard = false;
    cards.forEach(function (c) {
      if (c) { grid.appendChild(c); anyCard = true; }
    });
    if (!anyCard) {
      grid.appendChild(renderEmptyState());
    }
    resultList.appendChild(grid);

    // Acciones
    const actions = el('div', { cls: 'result-actions' });
    const dl = el('button', { cls: 'btn btn-primary', text: 'Descargar .json' });
    dl.type = 'button';
    dl.addEventListener('click', downloadJson);
    const again = el('button', { cls: 'btn btn-ghost', text: 'Otra imagen' });
    again.type = 'button';
    again.addEventListener('click', clearFile);
    actions.appendChild(dl);
    actions.appendChild(again);
    resultList.appendChild(actions);
  }

  function downloadJson() {
    if (!lastMetadata) return;
    const json = JSON.stringify(lastMetadata, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const stem = (lastMetadata.file && lastMetadata.file.name || 'metadata').replace(/\.[^.]+$/, '');
    a.download = stem + '_metadata.json';
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
  }
})();
