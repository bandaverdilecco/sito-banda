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
      target.style.setProperty("--section-inset", getComputedStyle(target).paddingTop);
    }
  }
  updateOffsets();
  new ResizeObserver(updateOffsets).observe(index);
  window.addEventListener("resize", updateOffsets, { passive: true });

  // Allinea anche i collegamenti diretti a una sezione all’apertura della pagina.
  requestAnimationFrame(() => {
    updateOffsets();
    let id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    targets.find(target => target.id === id)?.scrollIntoView({ behavior: "instant" });
  });
})();
