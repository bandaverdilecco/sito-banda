// Le foto restano nell’HTML. Questo script aggiunge soltanto il visualizzatore.
(() => {
  const photos = [...document.querySelectorAll(".gallery-photo")];
  if (!photos.length) return;

  const viewer = document.createElement("dialog");
  if (typeof viewer.showModal !== "function") return;
  viewer.className = "photo-viewer";
  viewer.setAttribute("aria-label", "Galleria fotografica");
  viewer.innerHTML = `
    <div class="photo-viewer-toolbar">
      <p class="photo-viewer-counter" aria-live="polite"></p>
      <div class="photo-viewer-actions">
        <button type="button" class="photo-viewer-zoom-out" aria-label="Riduci immagine" title="Riduci (−)">−</button>
        <button type="button" class="photo-viewer-zoom-reset" aria-label="Ripristina zoom" title="Ripristina zoom (0)">100%</button>
        <button type="button" class="photo-viewer-zoom-in" aria-label="Ingrandisci immagine" title="Ingrandisci (+)">+</button>
        <a class="photo-viewer-download" aria-label="Scarica immagine originale" title="Scarica immagine originale" target="_blank" rel="noopener noreferrer" download>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12m-5-5 5 5 5-5M5 16v5h14v-5" /></svg>
        </a>
        <button type="button" class="photo-viewer-close" aria-label="Chiudi galleria" autofocus>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
        </button>
      </div>
    </div>
    <div class="photo-viewer-stage">
      <img class="photo-viewer-image" alt="" draggable="false" referrerpolicy="no-referrer" />
      <p class="photo-viewer-status" role="status"></p>
    </div>
    <div class="photo-viewer-caption" id="photo-viewer-caption" aria-live="polite" hidden>
      <p class="photo-viewer-name"></p>
      <p class="photo-viewer-instrument"></p>
    </div>
    <div class="photo-viewer-controls">
      <button type="button" class="photo-viewer-prev" aria-label="Foto precedente">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 5-7 7 7 7" /></svg>
      </button>
      <button type="button" class="photo-viewer-next" aria-label="Foto successiva">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 5 7 7-7 7" /></svg>
      </button>
    </div>`;
  document.body.append(viewer);

  const image = viewer.querySelector(".photo-viewer-image");
  const stage = viewer.querySelector('.photo-viewer-stage');
  const zoomIn = viewer.querySelector('.photo-viewer-zoom-in');
  const zoomOut = viewer.querySelector('.photo-viewer-zoom-out');
  const zoomReset = viewer.querySelector('.photo-viewer-zoom-reset');
  const counter = viewer.querySelector(".photo-viewer-counter");
  const status = viewer.querySelector(".photo-viewer-status");
  const previous = viewer.querySelector(".photo-viewer-prev");
  const next = viewer.querySelector(".photo-viewer-next");
  const download = viewer.querySelector(".photo-viewer-download");
  const caption = viewer.querySelector('.photo-viewer-caption');
  const captionName = viewer.querySelector('.photo-viewer-name');
  const captionInstrument = viewer.querySelector('.photo-viewer-instrument');
  let current = 0;
  let zoom = 1, panX = 0, panY = 0;
  const pointers = new Map();
  let gesture = null, moved = false, suppressClickUntil = 0, lastTap = null;
  previous.disabled = next.disabled = photos.length < 2;

  function geometry() {
    const bounds = stage.getBoundingClientRect();
    const fit = Math.min(bounds.width / image.naturalWidth, bounds.height / image.naturalHeight);
    return { bounds, width: image.naturalWidth * fit, height: image.naturalHeight * fit };
  }
  function applyZoom() {
    if (!image.hidden && image.naturalWidth && viewer.open) {
      const { bounds, width, height } = geometry();
      const limitX = Math.max(0, (width * zoom - bounds.width) / 2);
      const limitY = Math.max(0, (height * zoom - bounds.height) / 2);
      panX = Math.max(-limitX, Math.min(limitX, panX));
      panY = Math.max(-limitY, Math.min(limitY, panY));
    }
    image.style.transform = zoom === 1 ? 'none' : `translate(${panX}px, ${panY}px) scale(${zoom})`;
    viewer.classList.toggle('is-zoomed', zoom > 1);
    zoomReset.textContent = `${Math.round(zoom * 100)}%`;
    zoomIn.disabled = image.hidden || zoom >= 5;
    zoomOut.disabled = zoomReset.disabled = image.hidden || zoom <= 1;
    positionCaption();
  }
  function zoomAt(value, clientX, clientY) {
    if (image.hidden || !image.naturalWidth) return;
    const { bounds } = geometry();
    const x = (clientX ?? bounds.left + bounds.width / 2) - bounds.left - bounds.width / 2;
    const y = (clientY ?? bounds.top + bounds.height / 2) - bounds.top - bounds.height / 2;
    const nextZoom = Math.max(1, Math.min(5, value));
    panX = x - (x - panX) * nextZoom / zoom;
    panY = y - (y - panY) * nextZoom / zoom;
    zoom = nextZoom;
    applyZoom();
  }
  function resetZoom() {
    zoom = 1; panX = panY = 0;
    pointers.clear(); gesture = null; lastTap = null;
    suppressClickUntil = 0; moved = false;
    stage.classList.remove('is-panning');
    applyZoom();
  }
  function insidePhoto(x, y) {
    if (image.hidden || !image.naturalWidth) return false;
    const { bounds, width, height } = geometry();
    const left = bounds.left + (bounds.width - width * zoom) / 2 + panX;
    const top = bounds.top + (bounds.height - height * zoom) / 2 + panY;
    return x >= left && x <= left + width * zoom && y >= top && y <= top + height * zoom;
  }
  function startGesture() {
    const points = [...pointers.values()];
    if (!points.length) { gesture = null; return; }
    const a = points[0], b = points[1] || a;
    gesture = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2,
      distance: Math.max(1, Math.hypot(a.x - b.x, a.y - b.y)), zoom, panX, panY };
  }
  stage.addEventListener('pointerdown', event => {
    if (event.button !== 0 || image.hidden || !insidePhoto(event.clientX, event.clientY)) return;
    event.preventDefault();
    if (!pointers.size) moved = false;
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    stage.setPointerCapture(event.pointerId);
    if (pointers.size > 1) { moved = true; lastTap = null; }
    startGesture();
  });
  stage.addEventListener('pointermove', event => {
    if (!pointers.has(event.pointerId) || !gesture) return;
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    const points = [...pointers.values()];
    const a = points[0], b = points[1] || a;
    const x = (a.x + b.x) / 2, y = (a.y + b.y) / 2;
    if (points.length > 1) {
      const { bounds } = geometry();
      zoom = Math.max(1, Math.min(5, gesture.zoom * Math.hypot(a.x - b.x, a.y - b.y) / gesture.distance));
      const gx = gesture.x - bounds.left - bounds.width / 2;
      const gy = gesture.y - bounds.top - bounds.height / 2;
      panX = x - bounds.left - bounds.width / 2 - (gx - gesture.panX) * zoom / gesture.zoom;
      panY = y - bounds.top - bounds.height / 2 - (gy - gesture.panY) * zoom / gesture.zoom;
      moved = true;
    } else {
      if (Math.hypot(x - gesture.x, y - gesture.y) > 5) moved = true;
      if (!moved || zoom === 1) return;
      panX = gesture.panX + x - gesture.x;
      panY = gesture.panY + y - gesture.y;
      stage.classList.add('is-panning');
    }
    applyZoom();
  });
  function endPointer(event) {
    if (!pointers.has(event.pointerId)) return;
    if (moved || event.type !== 'pointerup') suppressClickUntil = performance.now() + 500;
    if (event.pointerType === 'touch' && event.type === 'pointerup' && !moved) {
      const now = performance.now();
      if (lastTap && now - lastTap.time < 350 && Math.hypot(event.clientX - lastTap.x, event.clientY - lastTap.y) < 30) {
        zoomAt(zoom > 1 ? 1 : 3, event.clientX, event.clientY);
        lastTap = null;
      } else lastTap = { time: now, x: event.clientX, y: event.clientY };
      suppressClickUntil = now + 500;
    }
    pointers.delete(event.pointerId);
    startGesture();
    if (!pointers.size) stage.classList.remove('is-panning');
  }
  for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) stage.addEventListener(type, endPointer);
  stage.addEventListener('wheel', event => {
    if (image.hidden) return;
    event.preventDefault();
    const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? stage.clientHeight : 1);
    zoomAt(zoom * Math.exp(-Math.max(-500, Math.min(500, delta)) * 0.002), event.clientX, event.clientY);
  }, { passive: false });
  zoomIn.addEventListener('click', () => zoomAt(zoom * 1.5));
  zoomOut.addEventListener('click', () => zoomAt(zoom / 1.5));
  zoomReset.addEventListener('click', resetZoom);

  function positionCaption() {
    if (caption.hidden || image.hidden || !image.naturalWidth || !viewer.open) return;
    const bounds = image.getBoundingClientRect();
    const dialog = viewer.getBoundingClientRect();
    const scale = Math.min(bounds.width / image.naturalWidth, bounds.height / image.naturalHeight);
    const width = image.naturalWidth * scale;
    const height = image.naturalHeight * scale;
    const left = Math.max(dialog.left, bounds.left + (bounds.width - width) / 2);
    const right = Math.min(dialog.right, bounds.left + (bounds.width + width) / 2);
    caption.style.width = `${Math.max(0, right - left)}px`;
    caption.style.maxHeight = `${height * 0.45}px`;
    caption.style.left = `${left - dialog.left}px`;
    // Anchor the lower edge directly: mobile text resizing must not move the band.
    caption.style.bottom = `${Math.max(0, dialog.bottom - bounds.top - (bounds.height + height) / 2)}px`;
    caption.style.visibility = 'visible';
  }
  const captionObserver = new ResizeObserver(applyZoom);
  captionObserver.observe(viewer);
  captionObserver.observe(image);
  window.addEventListener('resize', applyZoom);
  window.visualViewport?.addEventListener('resize', applyZoom);

  function showPhoto(index) {
    current = (index + photos.length) % photos.length;
    image.hidden = true;
    resetZoom();
    status.hidden = false;
    status.textContent = "Caricamento della foto…";
    counter.textContent = `Foto ${current + 1} di ${photos.length}`;
    captionName.textContent = photos[current].dataset.captionName || '';
    captionInstrument.textContent = photos[current].dataset.captionInstrument || '';
    caption.hidden = !captionName.textContent && !captionInstrument.textContent;
    caption.style.visibility = 'hidden';
    if (caption.hidden) viewer.removeAttribute('aria-describedby');
    else viewer.setAttribute('aria-describedby', caption.id);
    image.alt = photos[current].querySelector("img").alt;
    image.src = photos[current].href;
    const url = new URL(photos[current].href);
    const driveId = /^lh\d+\.googleusercontent\.com$/.test(url.hostname)
      ? url.pathname.match(/^\/d\/([\w-]+)/)?.[1]
      : null;
    // Il download usa il file originale su Drive, non l’anteprima ridimensionata.
    download.href = photos[current].dataset.original || (driveId
      ? `https://drive.google.com/uc?export=download&id=${encodeURIComponent(driveId)}`
      : photos[current].href);
  }

  image.addEventListener("load", () => {
    image.hidden = false;
    status.hidden = true;
    applyZoom();
  });
  image.addEventListener("error", () => {
    image.hidden = true;
    caption.style.visibility = 'hidden';
    resetZoom();
    status.hidden = false;
    status.textContent = "Questa foto non è disponibile. Puoi passare alla successiva.";
  });

  photos.forEach((photo, index) => {
    photo.addEventListener("click", (event) => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      showPhoto(index);
      viewer.showModal();
      document.body.classList.add("gallery-open");
    });
  });

  previous.addEventListener("click", () => showPhoto(current - 1));
  next.addEventListener("click", () => showPhoto(current + 1));
  viewer.querySelector(".photo-viewer-close").addEventListener("click", () => viewer.close());
  document.addEventListener("keydown", (event) => {
    if (!viewer.open) return;
    if (!event.ctrlKey && !event.metaKey && ['+', '=', '-', '0'].includes(event.key)) {
      event.preventDefault();
      if (event.key === '0') resetZoom();
      else zoomAt(zoom * (event.key === '-' ? 1 / 1.5 : 1.5));
      return;
    }
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    showPhoto(current + (event.key === "ArrowRight" ? 1 : -1));
  });
  viewer.addEventListener("click", (event) => {
    if (event.target.closest("button, a, .photo-viewer-caption")) return;
    if (performance.now() < suppressClickUntil) return;
    if (insidePhoto(event.clientX, event.clientY)) {
      if (event.pointerType !== 'touch') zoomAt(zoom > 1 ? 1 : 3, event.clientX, event.clientY);
      return;
    }
    viewer.close();
  });
  viewer.addEventListener("close", () => {
    document.body.classList.remove("gallery-open");
    resetZoom();
  });
})();
