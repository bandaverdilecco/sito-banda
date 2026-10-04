// Genera HTML completo per l'hosting, inserendo header e footer condivisi.
import { cp, mkdir, rm, readdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { renderPage } from "./render.mjs";
import { generateAlbumPages } from "./albums.mjs";

const source = new URL("../public/", import.meta.url);
const output = new URL("../dist/", import.meta.url);
// Verifica dati e cartelle prima di sostituire l’ultima build riuscita.
const albumPages = await generateAlbumPages();
await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });
await cp(source, output, { recursive: true });
const root = fileURLToPath(source);
const target = fileURLToPath(output);
async function buildPages(directory = "") {
  for (const entry of await readdir(resolve(root, directory), { withFileTypes: true })) {
    if (!directory && entry.name === "partials") continue;
    const path = directory ? `${directory}/${entry.name}` : entry.name;
    if (entry.isDirectory()) await buildPages(path);
    else if (entry.name.endsWith(".html")) {
      const filename = resolve(root, path);
      const html = await readFile(filename, "utf8");
      await writeFile(resolve(target, path), await renderPage(html, filename, root));
    }
  }
}
await buildPages();
for (const [path, html] of albumPages) {
  await mkdir(dirname(resolve(target, path)), { recursive: true });
  await writeFile(resolve(target, path), await renderPage(html, resolve(root, path), root));
}
await rm(new URL("partials/", output), { recursive: true, force: true });
console.log("Sito statico pronto in dist/.");
