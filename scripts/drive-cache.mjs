import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, rename, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { folderDetails, readDriveFolder, readEntries } from "./drive.mjs";

// La coda limita le richieste, non la ricorsione: nessun lock trattenuto sui figli.
export function limitConcurrency(maximum) {
  let active = 0;
  const queue = [];
  return async task => {
    await new Promise(resolve => {
      queue.push(resolve);
      if (active < maximum) { active++; queue.shift()(); }
    });
    try { return await task(); }
    finally {
      if (queue.length) queue.shift()();
      else active--;
    }
  };
}

function validEntries(entries) {
  return Array.isArray(entries) && entries.every(file => file &&
    /^[\w-]+$/.test(file.id) && typeof file.name === "string" && typeof file.mimeType === "string" &&
    (file.resourceKey === undefined || typeof file.resourceKey === "string"));
}

const normalize = entries => entries.map(({ id, name, mimeType, resourceKey }) => ({
  id, name, mimeType, ...(resourceKey ? { resourceKey } : {}),
})).sort((a, b) => a.id.localeCompare(b.id));

export function createDriveCache({
  directory = fileURLToPath(new URL("../.cache/drive/", import.meta.url)),
  preferCache = false,
  apiKey = process.env.GOOGLE_DRIVE_API_KEY,
  fetchEntries = readEntries,
} = {}) {
  const limit = limitConcurrency(6);
  const pending = new Map();
  const stats = { checked: 0, changed: 0, unchanged: 0, cached: 0 };

  async function entriesReader(link) {
    const { id, resourceKey } = folderDetails(link);
    const key = createHash("sha256").update(JSON.stringify([id, resourceKey, apiKey ? "api" : "public"])).digest("hex");
    if (!pending.has(key)) pending.set(key, limit(async () => {
      const filename = join(directory, `${key}.json`);
      let cached;
      try {
        const data = JSON.parse(await readFile(filename, "utf8"));
        if (data.version === 1 && validEntries(data.entries)) cached = data.entries;
      } catch (error) {
        if (error.code !== "ENOENT" && !(error instanceof SyntaxError)) throw error;
      }
      if (preferCache && cached) { stats.cached++; return cached; }
      // Le cartelle grandi passano direttamente alla vista completa ai controlli successivi.
      const entries = normalize(await fetchEntries(link, apiKey, Boolean(cached && cached.length >= 50)));
      if (!validEntries(entries)) throw new Error("Elenco Drive non valido.");
      stats.checked++;
      if (cached && JSON.stringify(entries) === JSON.stringify(cached)) stats.unchanged++;
      else {
        stats.changed++;
        await mkdir(directory, { recursive: true });
        const temporary = `${filename}.${randomUUID()}.tmp`;
        try {
          await writeFile(temporary, JSON.stringify({ version: 1, entries }) + "\n");
          await rename(temporary, filename);
        } finally { await rm(temporary, { force: true }); }
      }
      return entries;
    }));
    return pending.get(key);
  }

  return {
    stats,
    readFolder: link => readDriveFolder(link, { apiKey, entriesReader }),
  };
}
