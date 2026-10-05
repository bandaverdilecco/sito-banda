import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, readdir, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createDriveCache, limitConcurrency } from "./drive-cache.mjs";
import { writeOutput } from "./output.mjs";

const folder = id => `https://drive.google.com/drive/folders/${id}`;
const image = (id, name = `${id}.jpg`) => ({ id, name, mimeType: "image/jpeg" });
const child = { id: "child", name: "Child", mimeType: "application/vnd.google-apps.folder" };
async function temporary(t) {
  const directory = await mkdtemp(join(tmpdir(), "filarmonica-cache-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  return directory;
}

test("nested changes, renames and removals are detected even if the parent is unchanged", async t => {
  const directory = await temporary(t);
  let listing = [image("old")];
  const calls = [];
  const fetchEntries = async link => {
    calls.push(link);
    return link === folder("root") ? [child] : listing;
  };
  const options = { directory, apiKey: "", fetchEntries };
  let cache = createDriveCache(options);
  assert.deepEqual((await cache.readFolder(folder("root"))).map(p => p.id), ["old"]);
  assert.equal(cache.stats.changed, 2);
  const times = await Promise.all((await readdir(directory)).map(async name => [name, (await stat(join(directory, name))).mtimeMs]));
  cache = createDriveCache(options);
  await cache.readFolder(folder("root"));
  assert.equal(cache.stats.unchanged, 2);
  for (const [name, time] of times) assert.equal((await stat(join(directory, name))).mtimeMs, time);
  listing = [image("new", "Renamed.jpg")];
  cache = createDriveCache(options);
  assert.deepEqual((await cache.readFolder(folder("root"))).map(p => p.id), ["new"]);
  assert.equal(cache.stats.changed, 1);
  assert.equal(cache.stats.unchanged, 1);
  listing = [];
  cache = createDriveCache(options);
  assert.deepEqual(await cache.readFolder(folder("root")), []);
  assert.equal(calls.length, 8);
});

test("cached builds need no network; new folders are fetched and corrupted cache repaired", async t => {
  const directory = await temporary(t);
  await createDriveCache({ directory, apiKey: "", fetchEntries: async () => [image("photo")] }).readFolder(folder("root"));
  let calls = 0;
  const options = { directory, apiKey: "", preferCache: true, fetchEntries: async () => { calls++; return [image("new")]; } };
  let cache = createDriveCache(options);
  assert.equal((await cache.readFolder(folder("root")))[0].id, "photo");
  assert.equal(calls, 0);
  assert.equal(cache.stats.cached, 1);
  await cache.readFolder(folder("new-folder"));
  assert.equal(calls, 1);
  for (const name of await readdir(directory)) await writeFile(join(directory, name), "{");
  cache = createDriveCache(options);
  assert.equal((await cache.readFolder(folder("root")))[0].id, "new");
  assert.equal(calls, 2);
});

test("normal builds fail on access errors without overwriting cached data", async t => {
  const directory = await temporary(t);
  await createDriveCache({ directory, apiKey: "", fetchEntries: async () => [image("photo")] }).readFolder(folder("root"));
  const filename = join(directory, (await readdir(directory))[0]);
  const previous = await readFile(filename, "utf8");
  const cache = createDriveCache({ directory, apiKey: "", fetchEntries: async () => { throw new Error("HTTP 403"); } });
  await assert.rejects(cache.readFolder(folder("root")), /HTTP 403/);
  assert.equal(await readFile(filename, "utf8"), previous);
});

test("shared folders are requested only once per build", async t => {
  const directory = await temporary(t);
  let calls = 0;
  const cache = createDriveCache({ directory, apiKey: "", fetchEntries: async () => { calls++; return [image("photo")]; } });
  await Promise.all(Array.from({ length: 12 }, () => cache.readFolder(folder("root"))));
  assert.equal(calls, 1);
});

test("request concurrency is bounded and failures release the queue", async () => {
  const limit = limitConcurrency(6);
  let active = 0;
  let peak = 0;
  const results = await Promise.allSettled(Array.from({ length: 24 }, (_, i) => limit(async () => {
    active++;
    peak = Math.max(peak, active);
    await new Promise(resolve => setTimeout(resolve, 5));
    active--;
    if (i === 0) throw new Error("Expected failure");
  })));
  assert.equal(peak, 6);
  assert.equal(active, 0);
  assert.equal(results.filter(r => r.status === "rejected").length, 1);
});

test("incremental output preserves untouched files and removes obsolete pages", async t => {
  const directory = await temporary(t);
  const initial = new Map([["index.html", "Home"], ["foto/old.html", "Old album"], ["styles.css", "CSS"]]);
  assert.deepEqual(await writeOutput(directory, initial), { updated: 3, removed: 0 });
  const time = (await stat(join(directory, "index.html"))).mtimeMs;
  assert.deepEqual(await writeOutput(directory, initial), { updated: 0, removed: 0 });
  const next = new Map([["index.html", "Home"], ["foto/new.html", "New album"], ["styles.css", "New CSS"]]);
  assert.deepEqual(await writeOutput(directory, next), { updated: 2, removed: 1 });
  assert.equal((await stat(join(directory, "index.html"))).mtimeMs, time);
  await assert.rejects(readFile(join(directory, "foto/old.html")), { code: "ENOENT" });
});
