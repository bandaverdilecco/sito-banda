import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { renderAlbum, renderIndex, validateAlbums, coverSource } from "./albums.mjs";
import { parsePublicFolder, parseEmbeddedFolder, readDriveFolder } from "./drive.mjs";

const album = { slug: "nuovo-concerto", title: "Concerto", date: "2026-10", description: "Lecco", folder: "", cover: "" };

test("configured albums render with valid local covers and index links", async () => {
  const metadata = JSON.parse(await readFile(new URL("../data/albums.json", import.meta.url), "utf8"));
  const template = await readFile(new URL("../templates/album.html", import.meta.url), "utf8");
  const index = renderIndex(validateAlbums(metadata), "{{yearLinks}}{{albumSections}}");
  for (const item of metadata.albums) {
    const html = renderAlbum(item, [], template);
    assert.ok(html);
    if (item.cover.startsWith("assets/")) await readFile(new URL(`../public/${item.cover}`, import.meta.url));
    assert.ok(index.includes(`href="foto/${item.slug}.html"`));
    assert.ok(!html.includes("{{"));
  }
});

test("embedded listing includes more than 50 photos and decodes names", () => {
  const html = '<div class="flip-entries">' + Array.from({length: 75}, (_, i) =>
    `<div class="flip-entry" id="entry-photo${i}"><a href="https://drive.google.com/file/d/photo${i}/view"><img src="https://drive-thirdparty.googleusercontent.com/16/type/image/jpeg"><div class="flip-entry-title">Foto &amp; ${i}.jpg</div></a></div>`).join("") + '</div>';
  const files = parseEmbeddedFolder(html);
  assert.equal(files.length, 75);
  assert.equal(files[74].name, "Foto & 74.jpg");
  assert.throws(() => parseEmbeddedFolder("Sign in"));
});

test("nested folders are traversed once, duplicate images and videos excluded", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async url => {
    const id = new URL(url).pathname.split("/").at(-1);
    calls.push(id);
    const rows = id === "root" ? [
      ["child", ["root"], "Subfolder", "application/vnd.google-apps.folder"],
      ["image", ["root"], "Foto.jpg", "image/jpeg"],
    ] : [
      ["root", ["child"], "Cycle", "application/vnd.google-apps.folder"],
      ["image", ["child"], "Foto.jpg", "image/jpeg"],
      ["second", ["child"], "Seconda.jpg", "image/jpeg"],
      ["video", ["child"], "Video.mp4", "video/mp4"],
    ];
    return { ok: true, text: async () => folderHtml(rows) };
  };
  try {
    const photos = await readDriveFolder("https://drive.google.com/drive/folders/root", {apiKey: ""});
    assert.deepEqual(calls, ["root", "child"]);
    assert.deepEqual(photos.map(file => file.id), ["image", "second"]);
  } finally { globalThis.fetch = originalFetch; }
});

test("new entries generate sorted year groups, escaped text and an empty gallery", () => {
  const albums = validateAlbums({ albums: [
    { ...album, slug: "precedente", date: "2025-01" },
    { ...album, title: '<Nuovo> & "concerto"' },
  ] });
  const html = renderIndex(albums, "{{yearLinks}}{{albumSections}}");
  assert.ok(html.indexOf('href="#foto-2026"') < html.indexOf('href="#foto-2025"'));
  assert.ok(html.includes("&lt;Nuovo&gt; &amp; &quot;concerto&quot;"));
  assert.ok(html.includes('href="foto/nuovo-concerto.html"'));
  const gallery = renderAlbum(album, [], "{{gallery}}");
  assert.ok(gallery.includes("Le fotografie saranno disponibili a breve."));
  assert.ok(!gallery.includes("gallery-photo"));
});

test("invalid metadata fails before generating output", () => {
  for (const changes of [{ slug: "../bad" }, { date: "2026-13" }, { cover: "javascript:alert(1)" }, { folder: "https://example.com/folder" }]) {
    assert.throws(() => validateAlbums({ albums: [{ ...album, ...changes }] }));
  }
  assert.throws(() => validateAlbums({ albums: [album, album] }));
  assert.equal(coverSource("https://drive.google.com/file/d/photo123/view"), "https://lh3.googleusercontent.com/d/photo123=s800");
});

const folderHtml = rows => `window['_DRIVE_ivd'] = '${JSON.stringify([rows, null]).replaceAll('"', '\\x22')}';`;
test("public folder reader filters videos and rejects possibly truncated listings", () => {
  assert.deepEqual(parsePublicFolder(folderHtml([
    ["photo", ["folder"], "Foto.jpg", "image/jpeg"],
    ["video", ["folder"], "Video.mp4", "video/mp4"],
  ]), "folder"), [{ id: "photo", name: "Foto.jpg" }]);
  assert.throws(() => parsePublicFolder(folderHtml(Array(50).fill(["photo", ["folder"], "Foto.jpg", "image/jpeg"])), "folder"));
  assert.throws(() => parsePublicFolder("Sign in", "folder"));
});

test("Drive API follows all pages, filters videos, sorts filenames and passes resource keys", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push(new URL(url));
    assert.equal(options.headers["X-Goog-Drive-Resource-Keys"], "folder/key");
    const body = calls.length === 1
      ? { files: [{ id: "ten", name: "10.jpg", mimeType: "image/jpeg" }, { id: "video", name: "a.mp4", mimeType: "video/mp4" }], nextPageToken: "second" }
      : { files: [{ id: "two", name: "2.jpg", mimeType: "image/jpeg", resourceKey: "photo-key" }] };
    return { ok: true, json: async () => body };
  };
  try {
    const photos = await readDriveFolder("https://drive.google.com/drive/folders/folder?resourcekey=key", { apiKey: "test-key" });
    assert.deepEqual(photos.map(photo => photo.id), ["two", "ten"]);
    assert.equal(calls[1].searchParams.get("pageToken"), "second");
    const html = renderAlbum(album, photos, "{{gallery}}");
    assert.ok(html.includes("resourcekey=photo-key"));
    assert.ok(!html.includes("test-key"));
  } finally {
    globalThis.fetch = originalFetch;
  }
});
