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
        <a class="photo-viewer-download" aria-label="Scarica immagine originale" title="Scarica immagine originale" target="_blank" rel="noopener noreferrer" download>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12m-5-5 5 5 5-5M5 16v5h14v-5" /></svg>
        </a>
        <button type="button" class="photo-viewer-close" aria-label="Chiudi galleria" autofocus>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
        </button>
      </div>
    </div>
    <div class="photo-viewer-stage">
      <img class="photo-viewer-image" alt="" referrerpolicy="no-referrer" />
      <p class="photo-viewer-status" role="status"></p>
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
  const counter = viewer.querySelector(".photo-viewer-counter");
  const status = viewer.querySelector(".photo-viewer-status");
  const previous = viewer.querySelector(".photo-viewer-prev");
  const next = viewer.querySelector(".photo-viewer-next");
  const download = viewer.querySelector(".photo-viewer-download");
  let current = 0;
  previous.disabled = next.disabled = photos.length < 2;

  function showPhoto(index) {
    current = (index + photos.length) % photos.length;
    image.hidden = true;
    status.hidden = false;
    status.textContent = "Caricamento della foto…";
    counter.textContent = `Foto ${current + 1} di ${photos.length}`;
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
  });
  image.addEventListener("error", () => {
    image.hidden = true;
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
  viewer.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    showPhoto(current + (event.key === "ArrowRight" ? 1 : -1));
  });
  viewer.addEventListener("click", (event) => {
    if (event.target.closest("button, a")) return;
    if (!image.hidden && image.naturalWidth && image.naturalHeight) {
      // object-fit: contain lascia spazio vuoto dentro il riquadro dell’immagine.
      const rect = image.getBoundingClientRect();
      const scale = Math.min(rect.width / image.naturalWidth, rect.height / image.naturalHeight);
      const width = image.naturalWidth * scale;
      const height = image.naturalHeight * scale;
      const left = rect.left + (rect.width - width) / 2;
      const top = rect.top + (rect.height - height) / 2;
      if (event.clientX >= left && event.clientX <= left + width &&
          event.clientY >= top && event.clientY <= top + height) return;
    }
    viewer.close();
  });
  viewer.addEventListener("close", () => document.body.classList.remove("gallery-open"));
})();
