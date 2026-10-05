// Genera HTML completo per l'hosting, inserendo header e footer condivisi.
import { readdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { renderPage } from "./render.mjs";
import { generateAlbumPages } from "./albums.mjs";
import { createDriveCache } from "./drive-cache.mjs";
import { writeOutput } from "./output.mjs";
import { generateHomePage } from "./home.mjs";

const { values } = parseArgs({ options: { "no-cached-drive": { type: "boolean", default: false } } });
const drive = createDriveCache({ preferCache: !values["no-cached-drive"] });

const source = new URL("../public/", import.meta.url);
const output = new URL("../dist/", import.meta.url);
// Verifica dati e cartelle prima di sostituire l’ultima build riuscita.
const albumPages = await generateAlbumPages(undefined, { readFolder: drive.readFolder });
const root = fileURLToPath(source);
const target = fileURLToPath(output);
const home = await generateHomePage(root);
const files = new Map();
async function buildPages(directory = "") {
  for (const entry of await readdir(resolve(root, directory), { withFileTypes: true })) {
    if (!directory && entry.name === "partials") continue;
    const path = directory ? `${directory}/${entry.name}` : entry.name;
    if (path === "index.html") continue;
    if (entry.isDirectory()) await buildPages(path);
    else {
      const filename = resolve(root, path);
      const contents = await readFile(filename);
      files.set(path, entry.name.endsWith(".html")
        ? await renderPage(contents.toString("utf8"), filename, root) : contents);
    }
  }
}
await buildPages();
files.set("index.html", await renderPage(home, resolve(root, "index.html"), root));
for (const [path, html] of albumPages) {
  files.set(path, await renderPage(html, resolve(root, path), root));
}
const result = await writeOutput(target, files);
// L’anteprima usa la stessa homepage, aggiornata solo da questo comando.
if (await readFile(resolve(root, "index.html"), "utf8").catch(error => {
  if (error.code === "ENOENT") return "";
  throw error;
}) !== home) await writeFile(resolve(root, "index.html"), home);
console.log(`Sito statico pronto in dist/: ${result.updated} file aggiornati, ${result.removed} rimossi.`);
console.log(`Drive: ${drive.stats.checked} cartelle verificate, ${drive.stats.changed} elenchi aggiornati, ${drive.stats.cached} letti dalla cache.`);
