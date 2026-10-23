(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const viewport = $('viewport'), image = $('sheet-image'), selector = $('sheet-select');
  const data = window.ULVA_SCHEMATIC_PAGES;
  const sidebar = $('page-sidebar'), thumbnails = $('page-thumbnails');
  const mobile = matchMedia('(max-width:650px)'), thumbnailButtons = [];
  function revealThumbnail() {
    const current = thumbnailButtons.find(button => button.getAttribute('aria-current') === 'page');
    if (!current || sidebar.hidden || !thumbnails.clientHeight) return;
    const item = current.getBoundingClientRect(), area = thumbnails.getBoundingClientRect();
    if (item.top < area.top + 8) thumbnails.scrollTop += item.top - area.top - 8;
    else if (item.bottom > area.bottom - 8) thumbnails.scrollTop += item.bottom - area.bottom + 8;
  }
  let thumbnailRevealFrame = 0;
  function scheduleThumbnailReveal() {
    if (thumbnailRevealFrame) return;
    thumbnailRevealFrame = requestAnimationFrame(() => {
      thumbnailRevealFrame = 0; revealThumbnail();
    });
  }
  const thumbnailLayout = new ResizeObserver(scheduleThumbnailReveal);
  thumbnailLayout.observe(thumbnails);
  function showPages(open) {
    document.body.dataset.pagesOpen = String(open); sidebar.hidden = !open;
    $('toggle-pages').setAttribute('aria-expanded', String(open));
    if (open) revealThumbnail();
  }
  $('toggle-pages').onclick = () => showPages(sidebar.hidden);
  $('close-pages').onclick = () => { showPages(false); $('toggle-pages').focus(); };
  mobile.addEventListener('change', () => showPages(!mobile.matches));
  showPages(!mobile.matches);
  if (document.body.classList.contains('embedded')) document.querySelector('nav').append($('pdf-link'));
  if (!data || data.schema !== 1 || !Array.isArray(data.sheets) || !data.sheets.length ||
      data.sheets.some(row => !Number.isInteger(row.page) || typeof row.title !== 'string' || !/^page-\d+\.svg$/.test(row.file))) {
    $('message').textContent = 'Pages are unavailable. Keep pages.js and the SVG files beside this viewer.';
    viewport.setAttribute('aria-busy', 'false'); return;
  }
  let index = 0, scale = 1, fitScale = 1, x = 0, y = 0, width = 0, height = 0, ready = false;
  let lastWidth = 0, lastHeight = 0;
  const pointers = new Map();
  for (const [i, sheet] of data.sheets.entries()) {
    const option = document.createElement('option'); option.value = i;
    const title = sheet.title.replace(/^Ulva\s*\/\s*/, '');
    option.textContent = `${sheet.page}. ${title}`; selector.append(option);
    const item = document.createElement('li'), button = document.createElement('button');
    button.type = 'button'; button.className = 'sheet-thumbnail'; button.dataset.sheetIndex = i;
    button.setAttribute('aria-label', `Sheet ${sheet.page}: ${title}`); button.title = title;
    const previewBox = document.createElement('span'); previewBox.className = 'thumbnail-preview';
    const preview = document.createElement('img'); preview.src = sheet.file; preview.alt = '';
    preview.width = 297; preview.height = 210; previewBox.append(preview);
    preview.loading = 'lazy'; preview.draggable = false; preview.setAttribute('aria-hidden', 'true');
    const caption = document.createElement('span'); caption.className = 'thumbnail-caption';
    const number = document.createElement('span'); number.className = 'thumbnail-number'; number.textContent = `${sheet.page} · `;
    caption.append(number, document.createTextNode(title)); button.append(previewBox, caption);
    button.onclick = () => { openSheet(i); if (mobile.matches) { showPages(false); viewport.focus({preventScroll:true}); } };
    item.append(button); thumbnails.append(item); thumbnailButtons.push(button);
    thumbnailLayout.observe(button);
  }
  selector.disabled = false; $('toggle-pages').disabled = false;
  function draw() {
    image.style.transform = `translate(${x}px,${y}px) scale(${scale})`;
    $('zoom-level').textContent = `${Math.round(scale / fitScale * 100)}%`;
  }
  function fit() {
    if (!ready || viewport.clientWidth < 20 || viewport.clientHeight < 20) return;
    lastWidth = viewport.clientWidth; lastHeight = viewport.clientHeight;
    fitScale = Math.min((viewport.clientWidth - 16) / width, (viewport.clientHeight - 16) / height);
    scale = fitScale; x = (viewport.clientWidth - width * scale) / 2; y = (viewport.clientHeight - height * scale) / 2; draw();
  }
  function zoom(factor, px = viewport.clientWidth / 2, py = viewport.clientHeight / 2) {
    if (!ready) return;
    const next = Math.min(fitScale * 24, Math.max(fitScale / 2, scale * factor));
    x = px - (px - x) * next / scale; y = py - (py - y) * next / scale; scale = next; draw();
  }
  function openSheet(next) {
    next = Math.max(0, Math.min(data.sheets.length - 1, next));
    if (next === index && ready) return;
    index = next; ready = false; pointers.clear();
    viewport.classList.remove('dragging'); image.hidden = true; $('message').hidden = false;
    $('message').textContent = 'Opening sheet…'; viewport.setAttribute('aria-busy', 'true');
    const sheet = data.sheets[index]; selector.value = index;
    for (const [i, button] of thumbnailButtons.entries()) {
      if (i === index) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    }
    revealThumbnail();
    $('previous').disabled = index === 0; $('next').disabled = index === data.sheets.length - 1;
    for (const id of ['zoom-out', 'zoom-in', 'fit']) $(id).disabled = true;
    $('page-status').textContent = `Sheet ${index + 1} / ${data.sheets.length} · ${data.revision || 'Ulva'}`;
    image.alt = `Sheet ${sheet.page}: ${sheet.title}`; image.src = sheet.file;
  }
  image.onload = () => {
    width = image.naturalWidth; height = image.naturalHeight;
    if (!(width > 0 && height > 0)) return image.onerror();
    image.style.width = `${width}px`; image.style.height = `${height}px`; ready = true;
    image.hidden = false; $('message').hidden = true; viewport.setAttribute('aria-busy', 'false');
    for (const id of ['zoom-out', 'zoom-in', 'fit']) $(id).disabled = false;
    fit();
  };
  image.onerror = () => {
    ready = false; image.hidden = true; $('message').hidden = false;
    $('message').textContent = 'This sheet could not be opened. Keep all page SVG files beside index.html.';
    viewport.setAttribute('aria-busy', 'false');
  };
  selector.onchange = () => openSheet(Number(selector.value));
  $('previous').onclick = () => openSheet(index - 1); $('next').onclick = () => openSheet(index + 1);
  $('zoom-out').onclick = () => zoom(1 / 1.3); $('zoom-in').onclick = () => zoom(1.3); $('fit').onclick = fit;
  viewport.addEventListener('wheel', event => {
    event.preventDefault(); const rect = viewport.getBoundingClientRect();
    zoom(Math.exp(-Math.max(-200, Math.min(200, event.deltaY)) * .002), event.clientX - rect.left, event.clientY - rect.top);
  }, {passive:false});
  const point = event => { const rect = viewport.getBoundingClientRect(); return {x:event.clientX-rect.left,y:event.clientY-rect.top}; };
  viewport.addEventListener('pointerdown', event => {
    if (!ready || (event.pointerType === 'mouse' && event.button !== 0)) return;
    event.preventDefault(); viewport.focus({preventScroll:true}); viewport.setPointerCapture(event.pointerId);
    pointers.set(event.pointerId, point(event)); viewport.classList.add('dragging');
  });
  viewport.addEventListener('pointermove', event => {
    if (!pointers.has(event.pointerId)) return;
    const old = [...pointers.values()]; pointers.set(event.pointerId, point(event)); const next = [...pointers.values()];
    if (next.length === 1) { x += next[0].x-old[0].x; y += next[0].y-old[0].y; draw(); }
    else {
      const center = points => ({x:(points[0].x+points[1].x)/2,y:(points[0].y+points[1].y)/2});
      const a=center(old), b=center(next), distance=points=>Math.hypot(points[0].x-points[1].x,points[0].y-points[1].y);
      const before=distance(old); if (before>0) zoom(distance(next)/before,a.x,a.y);
      x+=b.x-a.x;y+=b.y-a.y;draw();
    }
  });
  const release = event => {pointers.delete(event.pointerId);if (!pointers.size) viewport.classList.remove('dragging');};
  for (const name of ['pointerup','pointercancel','lostpointercapture']) viewport.addEventListener(name,release);
  viewport.addEventListener('dblclick',fit);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && mobile.matches && !sidebar.hidden) { showPages(false); $('toggle-pages').focus(); return; }
    if (event.target.closest('input,select,textarea,[contenteditable=true]')) return;
    const actions={ArrowLeft:()=>openSheet(index-1),ArrowRight:()=>openSheet(index+1),'+':()=>zoom(1.3),'=':()=>zoom(1.3),'-':()=>zoom(1/1.3),'0':fit};
    if (actions[event.key]) {event.preventDefault();actions[event.key]();}
  });
  new ResizeObserver(() => {
    const w = viewport.clientWidth, h = viewport.clientHeight;
    if (!ready || w < 20 || h < 20 || (w === lastWidth && h === lastHeight)) return;
    if (!lastWidth || !lastHeight) { fit(); return; }
    const centerX = (lastWidth / 2 - x) / scale, centerY = (lastHeight / 2 - y) / scale;
    const relativeZoom = scale / fitScale;
    fitScale = Math.min((w - 16) / width, (h - 16) / height); scale = fitScale * relativeZoom;
    x = w / 2 - centerX * scale; y = h / 2 - centerY * scale; lastWidth = w; lastHeight = h; draw();
  }).observe(viewport);
  openSheet(0);
})();
