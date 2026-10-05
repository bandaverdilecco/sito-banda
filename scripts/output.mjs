import { mkdir, readFile, readdir, rm, rmdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

// Mantiene data e contenuto dei file invariati; elimina quelli non più generati.
export async function writeOutput(root, files) {
  let updated = 0;
  let removed = 0;
  await mkdir(root, { recursive: true });
  for (const [path, contents] of files) {
    const filename = resolve(root, path);
    const body = Buffer.isBuffer(contents) ? contents : Buffer.from(contents);
    let previous;
    try { previous = await readFile(filename); }
    catch (error) { if (error.code !== "ENOENT") throw error; }
    if (previous?.equals(body)) continue;
    await mkdir(dirname(filename), { recursive: true });
    await writeFile(filename, body);
    updated++;
  }
  async function clean(directory = "") {
    for (const entry of await readdir(resolve(root, directory), { withFileTypes: true })) {
      const path = directory ? `${directory}/${entry.name}` : entry.name;
      const filename = resolve(root, path);
      if (entry.isDirectory()) {
        await clean(path);
        if (!(await readdir(filename)).length) await rmdir(filename);
      } else if (!files.has(path)) { await rm(filename); removed++; }
    }
  }
  await clean();
  return { updated, removed };
}
