// Legge soltanto cartelle pubbliche. La chiave API, se usata, resta sul computer di build.
export function folderDetails(value) {
  const url = new URL(value);
  const match = url.pathname.match(/^\/drive\/(?:u\/\d+\/)?folders\/([\w-]+)\/?$/);
  if (url.protocol !== "https:" || url.hostname !== "drive.google.com" || !match) {
    throw new Error("folder deve essere un link https://drive.google.com/drive/folders/…");
  }
  return { id: match[1], resourceKey: url.searchParams.get("resourcekey") || "" };
}

// Decodifica una stringa JavaScript senza eseguirne il contenuto.
function decodeString(value) {
  return value.replace(/\\(?:x([\da-f]{2})|u([\da-f]{4})|([\s\S]))/gi, (_, hex, unicode, char) => {
    if (hex || unicode) return String.fromCharCode(parseInt(hex || unicode, 16));
    return ({ n: "\n", r: "\r", t: "\t", b: "\b", f: "\f" })[char] ?? char;
  });
}

function parsePublicEntries(html, folderId) {
  const match = html.match(/window\['_DRIVE_ivd'\]\s*=\s*'((?:\\.|[^'])*)'/);
  if (!match) throw new Error("Cartella non leggibile: verifica che sia pubblica, oppure configura GOOGLE_DRIVE_API_KEY.");
  const data = JSON.parse(decodeString(match[1]));
  const rows = data[0];
  if (!Array.isArray(rows)) throw new Error("Elenco Drive non riconosciuto. Configura GOOGLE_DRIVE_API_KEY.");
  // La vista pubblica può troncare gli album grandi. Non pubblicare elenchi incompleti.
  if (rows.length >= 50 || data[1]) {
    throw new Error("Per elencare questa cartella completa configura GOOGLE_DRIVE_API_KEY e ripeti la build.");
  }
  return rows.filter(row => row[1]?.includes(folderId))
    .map(row => ({ id: row[0], name: row[2], mimeType: row[3] }));
}

export function parsePublicFolder(html, folderId) {
  return parsePublicEntries(html, folderId).filter(file => file.mimeType.startsWith("image/"))
    .map(({ id, name }) => ({ id, name }));
}

function decodeHtml(value) {
  return value.replace(/&(#x[\da-f]+|#\d+|amp|quot|apos|lt|gt);/gi, (entity, key) => {
    if (key.startsWith("#")) return String.fromCodePoint(parseInt(key.slice(key[1].toLowerCase() === "x" ? 2 : 1), key[1].toLowerCase() === "x" ? 16 : 10));
    return ({ amp: "&", quot: '"', apos: "'", lt: "<", gt: ">" })[key.toLowerCase()] ?? entity;
  });
}

// La vista incorporabile pubblica include anche gli elementi oltre i primi 50.
export function parseEmbeddedFolder(html) {
  if (!html.includes('id="entries"') && !html.includes('class="flip-entries"')) {
    throw new Error("Elenco completo Drive non leggibile. Configura GOOGLE_DRIVE_API_KEY.");
  }
  const entries = [];
  for (const match of html.matchAll(/<div class="flip-entry" id="entry-([\w-]+)"([\s\S]*?)(?=<div class="flip-entry" id="entry-|$)/g)) {
    const body = match[2];
    const name = body.match(/<div class="flip-entry-title">([\s\S]*?)<\/div>/)?.[1];
    const href = body.match(/<a href="([^"]+)"/)?.[1];
    const mimeType = /\/folders\//.test(href || "") ? "application/vnd.google-apps.folder"
      : body.match(/\/type\/([^"?]+)/)?.[1];
    if (name === undefined || !href || !mimeType) throw new Error("Elemento Drive non riconosciuto nell’elenco completo.");
    const url = new URL(decodeHtml(href));
    entries.push({ id: match[1], name: decodeHtml(name), mimeType, resourceKey: url.searchParams.get("resourcekey") || "" });
  }
  return entries;
}

async function get(url, headers = {}) {
  const response = await fetch(url, { headers, signal: AbortSignal.timeout(30000) });
  if (!response.ok) throw new Error(`Google Drive ha risposto con HTTP ${response.status}. Verifica condivisione e chiave API.`);
  return response;
}

async function readEntries(link, apiKey) {
  const { id, resourceKey } = folderDetails(link);
  let photos = [];
  if (apiKey) {
    let pageToken = "";
    const seen = new Set();
    do {
      const url = new URL("https://www.googleapis.com/drive/v3/files");
      url.search = new URLSearchParams({
        key: apiKey, q: `'${id}' in parents and trashed = false`,
        fields: "nextPageToken,files(id,name,mimeType,resourceKey)", pageSize: "1000",
        ...(pageToken ? { pageToken } : {}),
      });
      const headers = resourceKey ? { "X-Goog-Drive-Resource-Keys": `${id}/${resourceKey}` } : {};
      const data = await (await get(url, headers)).json();
      if (!Array.isArray(data.files)) throw new Error("Risposta Drive priva dell’elenco file.");
      photos.push(...data.files);
      pageToken = data.nextPageToken || "";
      if (pageToken && seen.has(pageToken)) throw new Error("Paginazione Drive non valida.");
      seen.add(pageToken);
    } while (pageToken);
  } else {
    const url = new URL(`https://drive.google.com/drive/folders/${id}`);
    if (resourceKey) url.searchParams.set("resourcekey", resourceKey);
    const html = await (await get(url)).text();
    try {
      photos = parsePublicEntries(html, id);
    } catch {
      const embedded = new URL("https://drive.google.com/embeddedfolderview");
      embedded.searchParams.set("id", id);
      if (resourceKey) embedded.searchParams.set("resourcekey", resourceKey);
      photos = parseEmbeddedFolder(await (await get(embedded)).text());
      if (!photos.length) throw new Error("Impossibile verificare l’elenco completo della cartella Drive.");
    }
  }
  for (const photo of photos) {
    if (!/^[\w-]+$/.test(photo.id) || typeof photo.name !== "string") throw new Error("File Drive non valido.");
  }
  return photos.sort((a, b) => a.name.localeCompare(b.name, "it", { numeric: true }));
}

export async function readDriveFolder(link, { apiKey = process.env.GOOGLE_DRIVE_API_KEY } = {}) {
  const visited = new Set();
  const photos = new Map();
  async function visit(folder) {
    const { id } = folderDetails(folder);
    if (visited.has(id)) return;
    visited.add(id);
    for (const file of await readEntries(folder, apiKey)) {
      if (file.mimeType?.startsWith("image/")) photos.set(file.id, file);
      else if (file.mimeType === "application/vnd.google-apps.folder") {
        const child = new URL(`https://drive.google.com/drive/folders/${file.id}`);
        if (file.resourceKey) child.searchParams.set("resourcekey", file.resourceKey);
        await visit(child.href);
      }
    }
  }
  await visit(link);
  return [...photos.values()].sort((a, b) => a.name.localeCompare(b.name, "it", { numeric: true }));
}
