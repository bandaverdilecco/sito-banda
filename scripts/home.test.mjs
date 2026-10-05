import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { generateHomePage, renderHomeEvents, renderHomeNews } from "./home.mjs";
import { renderPage } from "./render.mjs";

const event = (id, day, month) => `<article class="event-card" id="${id}">
  <div class="event-date"><span class="date-number">${day}</span><span class="date-month">${month}</span></div>
  <div><h2>${id}</h2><p><strong>Lecco</strong></p></div></article>`;
const news = (title, date, href) => `<article><img src="assets/${title}.jpg" alt="${title}">
  <div class="news-card-copy"><span class="eyebrow">${date}</span><h3>${title}</h3><p>Descrizione.</p>
  <a class="text-link" href="${href}" target="_blank" rel="noopener noreferrer">Leggi</a></div></article>`;

test("homepage shows the next three events by date, including today and uncertain current month", () => {
  const html = [event("last", "04", "Dicembre<br>2026"), event("next", "08", "Novembre 2026"),
    event("old", "04", "Ottobre 2026"), event("today", "05", "Ottobre 2026"), event("month", "Ott", "2026")].join("");
  const result = renderHomeEvents(html, "2026-10-05");
  assert.deepEqual([...result.matchAll(/href="prossimi-eventi.html#([^"]+)"/g)].map(m => m[1]), ["month", "today", "next"]);
  assert.ok(!result.includes("#old"));
  assert.ok(!result.includes("#last"));
});

test("empty calendars and past month-only events show a placeholder", () => {
  assert.match(renderHomeEvents(event("old", "Set", "2026"), "2026-10-05"), /annunciati a breve/);
  assert.match(renderHomeEvents("", "2026-10-05"), /annunciati a breve/);
  assert.throws(() => renderHomeEvents(event("bad", "31", "Febbraio 2026"), "2026-01-01"), /Data non valida/);
});

test("latest news comes from its date and keeps its original image, text and external link", () => {
  const result = renderHomeNews(news("old", "Novembre 2025", "blog/old.html") + news("new", "Maggio 2026", "https://example.com/news"));
  assert.match(result, /assets\/new.jpg/);
  assert.match(result, /<h3>new<\/h3>/);
  assert.match(result, /href="https:\/\/example.com\/news" target="_blank" rel="noopener noreferrer"/);
  assert.ok(!result.includes("old.jpg"));
  assert.match(renderHomeNews(""), /pubblicate qui/);
});

test("build generates the homepage and includes the editable discovery fragment", async () => {
  const root = fileURLToPath(new URL("../public/", import.meta.url));
  const generated = await generateHomePage(root);
  assert.ok(!generated.includes("<!-- include: home-"));
  assert.ok(!generated.includes("<!-- include: scopri-filarmonica -->"));
  const html = await renderPage(generated, resolve(root, "index.html"), root);
  assert.ok(!html.includes("<!-- include:"));
  assert.match(html, /Scopri la Filarmonica/);
  assert.equal((html.match(/class="news-card"/g) || []).length, 1);
  assert.match(html, /assets\/news-pronti-settembre-via.jpg/);
});
