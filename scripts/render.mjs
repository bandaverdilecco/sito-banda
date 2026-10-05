// Inserisce i due file HTML condivisi e adatta i link alla pagina corrente.
import { readFile } from "node:fs/promises";
import { dirname, relative, resolve, sep } from "node:path";

export async function renderPage(html, filename, root) {
  const page = relative(root, filename).split(sep).join("/");
  const prefix = relative(dirname(filename), root).split(sep).join("/");
  const fragments = {};
  for (const name of ["header", "footer", "scopri-filarmonica"]) {
    if (!html.includes(`<!-- include: ${name} -->`)) continue;
    let fragment = await readFile(resolve(root, "partials", `${name}.html`), "utf8");
    fragment = fragment.replace(/<a\b([^>]*?)href="([^"]+)"([^>]*?)>/g, (tag, before, href, after) => {
      if (href === page) return `<a${before}href="${href}"${after} aria-current="page">`;
      if (href === "foto.html" && page.startsWith("foto/")) {
        return `<a${before}href="${href}"${after} aria-current="true">`;
      }
      return tag;
    });
    fragment = fragment.replace(/\b(href|src)="([^"]+)"/g, (attribute, key, value) => {
      if (/^(?:[a-z][a-z\d+.-]*:|\/|#|\?)/i.test(value) || !prefix) return attribute;
      return `${key}="${prefix}/${value}"`;
    });
    fragments[name] = fragment.trimEnd();
  }
  return html.replace(/<!-- include: (header|footer|scopri-filarmonica) -->/g, (_, name) => fragments[name]);
}
