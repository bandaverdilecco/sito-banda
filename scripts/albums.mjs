import { readFile } from "node:fs/promises";
import { readDriveFolder, folderDetails } from "./drive.mjs";

const root = new URL("../", import.meta.url);
const read = path => readFile(new URL(path, root), "utf8");
export const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[char]);
const fill = (template, values) => template.replace(/\{\{(\w+)\}\}/g, (_, key) => values[key] ?? "");
const dateLabel = date => {
  const label = new Intl.DateTimeFormat("it", { month: "long", year: "numeric", timeZone: "UTC" })
    .format(new Date(`${date}-01T00:00:00Z`));
  return label[0].toUpperCase() + label.slice(1);
};

export function coverSource(value) {
  if (!value) return "";
  if (/^assets\/[\w./-]+$/.test(value) && !value.split("/").includes("..")) return value;
  const url = new URL(value);
  if (url.protocol !== "https:") throw new Error("La copertina deve essere un link HTTPS o un percorso assets/.");
  if (url.hostname === "drive.google.com") {
    const id = url.pathname.match(/^\/file\/d\/([\w-]+)/)?.[1] || url.searchParams.get("id");
    if (!id || !/^[\w-]+$/.test(id)) throw new Error("Link della foto di copertina Drive non valido.");
    return `https://lh3.googleusercontent.com/d/${id}=s800`;
  }
  return url.href;
}

export function validateAlbums(data) {
  if (!Array.isArray(data.albums)) throw new Error("data/albums.json deve contenere un array albums.");
  const slugs = new Set();
  for (const album of data.albums) {
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(album.slug || "") || slugs.has(album.slug)) {
      throw new Error(`Slug non valido o duplicato: ${album.slug}`);
    }
    slugs.add(album.slug);
    for (const key of ["title", "description", "date", "folder"]) {
      if (typeof album[key] !== "string") throw new Error(`${album.slug}: manca il campo ${key}.`);
    }
    if (!album.title.trim() || !/^\d{4}-(0[1-9]|1[0-2])$/.test(album.date)) {
      throw new Error(`${album.slug}: titolo vuoto o data non valida (usa YYYY-MM).`);
    }
    if (album.folder) folderDetails(album.folder);
    if (typeof album.cover !== "string") throw new Error(`${album.slug}: cover deve essere un link o una stringa vuota.`);
    coverSource(album.cover);
    if (album.coverPosition && !/^-?\d+(?:\.\d+)?% -?\d+(?:\.\d+)?%$/.test(album.coverPosition)) {
      throw new Error(`${album.slug}: coverPosition deve contenere due percentuali.`);
    }
  }
  return [...data.albums].sort((a, b) => b.date.localeCompare(a.date));
}

export async function loadAlbums() {
  return validateAlbums(JSON.parse(await read("data/albums.json")));
}

export function renderIndex(albums, template) {
  const years = [...new Set(albums.map(album => album.date.slice(0, 4)))];
  const card = album => {
    const cover = coverSource(album.cover);
    const image = cover
      ? `<img src="${escapeHtml(cover)}" alt="${escapeHtml(album.coverAlt || album.title)}" width="800" height="600" loading="lazy" decoding="async" referrerpolicy="no-referrer"${album.coverPosition ? ` style="object-position: ${album.coverPosition};"` : ""} />`
      : '<div class="album-cover-placeholder" aria-hidden="true">Filarmonica Giuseppe Verdi</div>';
    return `<article class="album-card">
      <a class="album-link" href="foto/${album.slug}.html" aria-label="${escapeHtml(album.title)}, ${dateLabel(album.date)}: apri la galleria">
        ${image}
        <div class="album-copy">
          <span class="eyebrow">${dateLabel(album.date)}</span>
          <h3>${escapeHtml(album.title)}</h3>
          ${album.description ? `<p class="album-location">${escapeHtml(album.description)}</p>` : ""}
          <span class="album-open">Apri album <span aria-hidden="true">→</span></span>
        </div>
      </a>
    </article>`;
  };
  return fill(template, {
    yearLinks: years.map(year => `<a href="#foto-${year}">${year}</a>`).join("\n"),
    albumSections: years.map(year => `<section class="album-year" id="foto-${year}" aria-labelledby="titolo-${year}">
      <h2 id="titolo-${year}">${year}</h2>
      <div class="album-grid">${albums.filter(album => album.date.startsWith(year)).map(card).join("\n")}</div>
    </section>`).join("\n"),
  });
}

export function renderAlbum(album, photos, template) {
  const gallery = photos.length ? `<div class="gallery-grid">${photos.map((photo, index) => {
    const id = typeof photo === "string" ? photo : photo.id;
    if (!/^[\w-]+$/.test(id)) throw new Error(`${album.slug}: ID foto non valido.`);
    const original = new URL("https://drive.google.com/uc");
    original.search = new URLSearchParams({ export: "download", id });
    if (photo.resourceKey) original.searchParams.set("resourcekey", photo.resourceKey);
    return `<a class="gallery-photo" href="https://lh3.googleusercontent.com/d/${id}=s1600" data-original="${escapeHtml(original.href)}" aria-label="Ingrandisci foto ${index + 1}">
      <img src="https://lh3.googleusercontent.com/d/${id}=s640" alt="${escapeHtml(album.title)}: foto ${index + 1}" width="640" height="480" loading="lazy" decoding="async" referrerpolicy="no-referrer" />
    </a>`;
  }).join("\n")}</div>` : '<p class="gallery-empty">Le fotografie saranno disponibili a breve.</p>';
  return fill(template, {
    title: escapeHtml(album.title), date: dateLabel(album.date), year: album.date.slice(0, 4),
    metaDescription: escapeHtml(`${album.title}. ${album.description}`),
    description: album.description ? `<p>${escapeHtml(album.description)}</p>` : "", gallery,
  });
}

const folderCache = new Map();
async function photosFor(album) {
  if (!album.folder) return [];
  const cached = folderCache.get(album.folder);
  if (cached && Date.now() - cached.time < 60000) return cached.photos;
  try {
    const photos = await readDriveFolder(album.folder);
    folderCache.set(album.folder, { time: Date.now(), photos });
    return photos;
  } catch (error) {
    throw new Error(`Album ${album.slug}: ${error.message}`);
  }
}

// path omesso: build completa. In anteprima risolve solo la pagina richiesta.
export async function generateAlbumPages(path) {
  const albums = await loadAlbums();
  const pages = new Map();
  if (!path || path === "foto.html") pages.set("foto.html", renderIndex(albums, await read("templates/foto.html")));
  const selected = albums.filter(album => !path || path === `foto/${album.slug}.html`);
  if (selected.length) {
    const template = await read("templates/album.html");
    for (const album of selected) pages.set(`foto/${album.slug}.html`, renderAlbum(album, await photosFor(album), template));
  }
  return pages;
}
