import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const months = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"];
const plain = html => html.replace(/<[^>]*>/g, " ").replace(/&nbsp;|&#160;/g, " ").replace(/\s+/g, " ").trim();
function content(html, tag, className) {
  const pattern = new RegExp(`<${tag}\\b[^>]*class=["'][^"']*\\b${className}\\b[^"']*["'][^>]*>([\\s\\S]*?)<\\/${tag}>`, "i");
  return html.match(pattern)?.[1];
}
const articles = html => [...html.replace(/<!--[\s\S]*?-->/g, "").matchAll(/<article\b([^>]*)>([\s\S]*?)<\/article>/gi)];

function dateFromLabel(label, day) {
  const value = plain(label).toLowerCase();
  const year = value.match(/\b(\d{4})\b/)?.[1];
  const monthName = value.match(/[a-zà-ù]+/)?.[0];
  const month = months.findIndex(name => monthName === name || monthName === name.slice(0, 3)) + 1;
  if (!year || !month) throw new Error(`Data non riconosciuta: ${value}. Usa un mese italiano e un anno.`);
  const date = `${year}-${String(month).padStart(2, "0")}`;
  if (day === undefined) return date;
  if (day < 1 || day > 31) throw new Error(`Giorno non valido: ${day}`);
  const exact = `${date}-${String(day).padStart(2, "0")}`;
  if (new Date(`${exact}T12:00:00Z`).toISOString().slice(0, 10) !== exact) throw new Error(`Data non valida: ${exact}`);
  return exact;
}

export function renderHomeEvents(html, today = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Europe/Rome", year: "numeric", month: "2-digit", day: "2-digit",
}).format(new Date())) {
  const events = articles(html).filter(match => /\bclass=["'][^"']*\bevent-card\b/.test(match[1])).map(match => {
    const id = match[1].match(/\bid=["']([\w-]+)["']/)?.[1];
    const block = match[2];
    const number = content(block, "span", "date-number");
    const month = content(block, "span", "date-month");
    const title = block.match(/<h2\b[^>]*>([\s\S]*?)<\/h2>/i)?.[1];
    const place = block.match(/<strong\b[^>]*>([\s\S]*?)<\/strong>/i)?.[1];
    const dateHtml = content(block, "div", "event-date");
    if (!id || !number || !month || !title || !place || !dateHtml) throw new Error("Evento incompleto in prossimi-eventi.html: servono id, data, titolo e luogo.");
    const day = /^\d{1,2}$/.test(plain(number)) ? Number(plain(number)) : undefined;
    const date = dateFromLabel(day !== undefined ? month : `${number} ${month}`, day);
    return { id, title, place, dateHtml, date };
  }).filter(event => event.date.length === 7 ? event.date >= today.slice(0, 7) : event.date >= today)
    .sort((a, b) => a.date.localeCompare(b.date)).slice(0, 3);
  if (!events.length) return '<p>I prossimi appuntamenti saranno annunciati a breve.</p>';
  return `<div class="event-list">${events.map(event => `
    <a class="event-row" href="prossimi-eventi.html#${event.id}">
      <span class="event-date">${event.dateHtml}</span>
      <h3>${event.title}</h3>
      <span class="event-place">${event.place}</span>
    </a>`).join("\n")}</div>`;
}

export function renderHomeNews(html) {
  const news = articles(html).map(match => {
    const block = match[2];
    const date = content(block, "span", "eyebrow");
    const copy = content(block, "div", "news-card-copy");
    const image = block.match(/<img\b[^>]*>/i)?.[0];
    if (!date || !copy || !image || !/<h[23]\b/i.test(copy) || !/<a\b/i.test(copy)) throw new Error("Notizia incompleta in blog.html: servono data, immagine, titolo e collegamento.");
    return { date: dateFromLabel(date), copy, image };
  }).sort((a, b) => b.date.localeCompare(a.date));
  if (!news.length) return '<p>Le novità della Filarmonica saranno pubblicate qui.</p>';
  const newest = news[0];
  return `<article class="news-card">
    ${newest.image}
    <div class="news-card-copy">${newest.copy.replace(/<(\/?)h2\b/g, "<$1h3")}</div>
  </article>`;
}

export async function renderHomeIncludes(html, root) {
  for (const [name, filename, render] of [
    ["home-events", "prossimi-eventi.html", renderHomeEvents],
    ["home-news", "blog.html", renderHomeNews],
  ]) {
    const marker = `<!-- include: ${name} -->`;
    if (html.includes(marker)) {
      const fragment = render(await readFile(resolve(root, filename), "utf8"));
      html = html.replaceAll(marker, () => fragment);
    }
  }
  return html;
}

export async function generateHomePage(root) {
  const template = await readFile(resolve(root, "../templates/index.html"), "utf8");
  const discovery = await readFile(resolve(root, "partials/scopri-filarmonica.html"), "utf8");
  const html = await renderHomeIncludes(template, root);
  return html.replaceAll("<!-- include: scopri-filarmonica -->", () => discovery.trimEnd())
    .replace("<!doctype html>", "<!doctype html>\n<!-- FILE GENERATO: modifica templates/index.html e lancia npm run build. -->");
}
