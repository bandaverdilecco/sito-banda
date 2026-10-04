// Anteprima locale dei file in public/. Non richiede pacchetti npm.
import { createServer } from "node:http";
import { readFile, realpath, stat } from "node:fs/promises";
import { networkInterfaces } from "node:os";
import { extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { renderPage } from "./render.mjs";

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

const server = createServer(async (request, response) => {
  if (!["GET", "HEAD"].includes(request.method)) {
    response.writeHead(405, { Allow: "GET, HEAD" }).end();
    return;
  }
  try {
    const url = new URL(request.url, "http://localhost");
    const pathname = decodeURIComponent(url.pathname);
    const redirect = redirects.get(pathname.replace(/\/$/, ""));
    if (redirect) {
      const hashIndex = redirect.indexOf("#");
      const target = hashIndex < 0 ? redirect : redirect.slice(0, hashIndex);
      const hash = hashIndex < 0 ? "" : redirect.slice(hashIndex);
      const query = url.search && target.includes("?") ? "&" + url.search.slice(1) : url.search;
      response.writeHead(301, { Location: target + query + hash }).end();
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
      body = Buffer.from(await renderPage(body.toString("utf8"), filename, root));
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
  console.error(error.message);
  process.exitCode = 1;
});
server.listen(port, values.ip, () => {
  const address = server.address().address;
  if (address === "0.0.0.0" || address === "::") {
    console.log(`Su questo computer: http://127.0.0.1:${port}`);
    const localAddresses = new Set();
    for (const [name, interfaces] of Object.entries(networkInterfaces())) {
      if (/^(docker|veth|br-|virbr|vmnet|vboxnet|tun|tap|wg|tailscale|utun|cni|podman)/i.test(name)) continue;
      for (const entry of interfaces || []) {
        if (!entry.internal && entry.family === "IPv4") localAddresses.add(entry.address);
      }
    }
    for (const localAddress of localAddresses) {
      console.log(`Nella rete locale: http://${localAddress}:${port}`);
    }
  } else {
    const host = address.includes(":") ? `[${address}]` : address;
    console.log(`Sito: http://${host}:${port}`);
  }
  console.log("Modifica i file in public/ e aggiorna il browser. Ctrl+C per uscire.");
});
