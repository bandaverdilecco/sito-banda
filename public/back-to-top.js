(() => {
  const button = document.querySelector(".back-to-top");
  if (!button) return;

  const update = () => { button.hidden = window.scrollY < 500; };
  window.addEventListener("scroll", update, { passive: true });
  window.addEventListener("pageshow", update);
  update();

  button.addEventListener("click", () => {
    document.querySelector(".brand")?.focus({ preventScroll: true });
    window.scrollTo({
      top: 0,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
    });
  });
})();
