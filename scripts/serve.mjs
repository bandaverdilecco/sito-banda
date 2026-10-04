// Anteprima locale dei file in public/. Non richiede pacchetti npm.
import { createServer } from "node:http";
import { watch } from "node:fs";
import { readFile, realpath, stat } from "node:fs/promises";
import { extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { renderPage } from "./render.mjs";
import { generateAlbumPages, loadAlbums } from "./albums.mjs";

const { values } = parseArgs({
  options: {
    port: { type: "string", default: "8080" },
    ip: { type: "string", default: "0.0.0.0" },
  },
});
const port = Number(values.port);
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error("La porta deve essere un numero tra 1 e 65535.");
}
const root = fileURLToPath(new URL("../public/", import.meta.url));
const publicRoot = await realpath(root);
const mimeTypes = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".svg": "image/svg+xml",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".webp": "image/webp",
  ".avif": "image/avif",
  ".gif": "image/gif",
  ".ico": "image/x-icon",
  ".pdf": "application/pdf",
};
const redirects = new Map(
  (await readFile(resolve(root, "_redirects"), "utf8"))
    .split("\n")
    .filter((line) => line.trim() && !line.startsWith("#"))
    .map((line) => line.split(/\s+/).slice(0, 2)),
);

// Solo nell’anteprima: aggiorna le pagine aperte quando si salva un JSON.
const reloadClients = new Set();
let reloadTimer;
const dataWatcher = watch(new URL("../data/", import.meta.url), (_, filename) => {
  if (filename && String(filename) !== "albums.json") return;
  clearTimeout(reloadTimer);
  reloadTimer = setTimeout(async () => {
    try {
      await loadAlbums();
      for (const client of reloadClients) client.write("data: reload\n\n");
    } catch (error) {
      console.error(`JSON non valido, anteprima conservata: ${error.message}`);
    }
  }, 250);
});
dataWatcher.on("error", error => console.error(`Aggiornamento automatico: ${error.message}`));
const withAutoReload = html => html.replace("</body>", `<script>
  (() => {
    let updates;
    const connect = () => {
      updates = new EventSource('/__dev/album-updates');
      updates.onmessage = () => location.reload();
    };
    connect();
    window.addEventListener('pagehide', () => updates.close());
    window.addEventListener('pageshow', event => { if (event.persisted) connect(); });
  })();
</script></body>`);

const server = createServer(async (request, response) => {
  if (!["GET", "HEAD"].includes(request.method)) {
    response.writeHead(405, { Allow: "GET, HEAD" }).end();
    return;
  }
  try {
    const url = new URL(request.url, "http://localhost");
    const pathname = decodeURIComponent(url.pathname);
    if (pathname === "/__dev/album-updates") {
      response.writeHead(200, {
        "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive",
      });
      if (request.method === "HEAD") { response.end(); return; }
      response.write(": connected\n\n");
      reloadClients.add(response);
      response.on("close", () => reloadClients.delete(response));
      return;
    }
    const redirect = redirects.get(pathname.replace(/\/$/, ""));
    if (redirect) {
      const hashIndex = redirect.indexOf("#");
      const target = hashIndex < 0 ? redirect : redirect.slice(0, hashIndex);
      const hash = hashIndex < 0 ? "" : redirect.slice(hashIndex);
      const query = url.search && target.includes("?") ? "&" + url.search.slice(1) : url.search;
      response.writeHead(301, { Location: target + query + hash }).end();
      return;
    }
    const albumPath = pathname.slice(1);
    if (albumPath === "foto.html" || /^foto\/[a-z0-9-]+\.html$/.test(albumPath)) {
      let pages;
      try {
        pages = await generateAlbumPages(albumPath);
      } catch (error) {
        console.error(error.message);
        response.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" });
        response.end(request.method === "HEAD" ? undefined : "Impossibile generare la galleria. Controlla i dati degli album e il terminale.");
        return;
      }
      if (!pages.has(albumPath)) throw new Error("Album non trovato");
      const body = Buffer.from(withAutoReload(await renderPage(pages.get(albumPath), resolve(root, albumPath), root)));
      response.writeHead(200, {
        "Content-Type": "text/html; charset=utf-8", "Content-Length": body.length, "Cache-Control": "no-store",
      });
      response.end(request.method === "HEAD" ? undefined : body);
      return;
    }
    let filename = resolve(root, "." + pathname);
    if ((await stat(filename)).isDirectory()) filename = resolve(filename, "index.html");
    filename = await realpath(filename);
    if (!filename.startsWith(publicRoot + sep) || !mimeTypes[extname(filename)]) {
      throw new Error("File non pubblico");
    }
    let body = await readFile(filename);
    if (extname(filename) === ".html") {
      body = Buffer.from(withAutoReload(await renderPage(body.toString("utf8"), filename, root)));
    }
    response.writeHead(200, {
      "Content-Type": mimeTypes[extname(filename)],
      "Content-Length": body.length,
      "Cache-Control": "no-store",
    });
    response.end(request.method === "HEAD" ? undefined : body);
  } catch {
    const filename = resolve(root, "404.html");
    const body = await renderPage(await readFile(filename, "utf8"), filename, root);
    response.writeHead(404, { "Content-Type": "text/html; charset=utf-8" });
    response.end(request.method === "HEAD" ? undefined : body);
  }
});

server.on("error", (error) => {
  dataWatcher.close();
  console.error(error.message);
  process.exitCode = 1;
});
server.on("close", () => {
  dataWatcher.close();
  clearTimeout(reloadTimer);
  for (const client of reloadClients) client.end();
});
server.listen(port, values.ip);
