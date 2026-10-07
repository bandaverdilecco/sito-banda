(() => {
  const index = document.querySelector(".section-index");
  if (!index) return;
  const targets = [...index.querySelectorAll('a[href^="#"]')].map(link => {
    try { return document.getElementById(decodeURIComponent(link.hash.slice(1))); }
    catch { return null; }
  }).filter(Boolean);

  function updateOffsets() {
    document.documentElement.style.setProperty("--section-index-height", `${index.getBoundingClientRect().height}px`);
    for (const target of targets) {
      const heading = target.querySelector(".eyebrow, h2");
      const inset = heading
        ? heading.getBoundingClientRect().top - target.getBoundingClientRect().top
        : parseFloat(getComputedStyle(target).paddingTop);
      target.style.setProperty("--section-inset", `${inset}px`);
    }
  }
  updateOffsets();
  const observer = new ResizeObserver(updateOffsets);
  observer.observe(index);
  targets.forEach(target => observer.observe(target));
  window.addEventListener("resize", updateOffsets, { passive: true });
  index.addEventListener("click", updateOffsets);

  // Allinea anche i collegamenti diretti a una sezione all’apertura della pagina.
  let interacted = false;
  for (const type of ["pointerdown", "touchstart", "wheel", "keydown"]) {
    window.addEventListener(type, () => { interacted = true; }, { once: true, passive: true });
  }
  function alignInitialTarget() {
    updateOffsets();
    if (interacted) return;
    let id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    targets.find(target => target.id === id)?.scrollIntoView({ behavior: "instant" });
  }
  requestAnimationFrame(alignInitialTarget);
  // Immagini e caratteri possono cambiare la posizione dopo il primo rendering.
  const loaded = document.readyState === "complete"
    ? Promise.resolve()
    : new Promise(resolve => window.addEventListener("load", resolve, { once: true }));
  Promise.all([loaded, document.fonts.ready]).then(alignInitialTarget);
})();
