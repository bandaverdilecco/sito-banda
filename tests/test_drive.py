"""Drive parsing, pagination and refresh behavior without network access or Node."""

from concurrent.futures import ThreadPoolExecutor
import html
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from app.drive import (
    DriveCache, DriveError, folder_details, parse_embedded_folder,
    parse_public_folder, read_drive_folder, read_entries,
)


FOLDER_MIME = "application/vnd.google-apps.folder"


def folder(identifier, resource_key=""):
    link = f"https://drive.google.com/drive/folders/{identifier}"
    return f"{link}?resourcekey={resource_key}" if resource_key else link


def photo(identifier, name=None, **extra):
    return {"id": identifier, "name": name or f"{identifier}.jpg", "mimeType": "image/jpeg", **extra}


def child(identifier="child", **extra):
    return {"id": identifier, "name": identifier, "mimeType": FOLDER_MIME, **extra}


def folder_html(rows, continuation=None, *, ensure_ascii=False):
    payload = json.dumps([rows, continuation], ensure_ascii=ensure_ascii)
    escaped = payload.replace("\\", "\\\\").replace("'", "\\'").replace('"', "\\x22")
    return f"<script>window['_DRIVE_ivd'] = '{escaped}';</script>"


def embedded_html(entries):
    rows = []
    for entry in entries:
        identifier = entry["id"]
        link = folder(identifier) if entry["mimeType"] == FOLDER_MIME else f"https://drive.google.com/file/d/{identifier}/view"
        if entry.get("resourceKey"):
            link += f'?resourcekey={entry["resourceKey"]}'
        rows.append(
            f'<div class="flip-entry" id="entry-{identifier}"><a href="{html.escape(link)}">'
            f'<img src="https://drive-thirdparty.googleusercontent.com/16/type/{entry["mimeType"]}">'
            f'<div class="flip-entry-title">{html.escape(entry["name"])}</div></a></div>'
        )
    return '<div class="flip-entries" id="entries">' + "".join(rows) + "</div>"


class DriveParsingTests(unittest.TestCase):
    def test_public_folder_handles_unicode_and_javascript_string_escapes(self):
        name = 'L\'estate – già qui 🎺 "Flauto" \\ 02.jpg'
        rows = [
            ["photo", ["root"], name, "image/jpeg"],
            ["video", ["root"], "Concerto.mp4", "video/mp4"],
            ["elsewhere", ["different"], "Other.jpg", "image/jpeg"],
        ]
        for ensure_ascii in (False, True):
            with self.subTest(ensure_ascii=ensure_ascii):
                self.assertEqual(parse_public_folder(folder_html(rows, ensure_ascii=ensure_ascii), "root"), [
                    {"id": "photo", "name": name},
                ])
        javascript_unicode = folder_html(rows).replace("à", r"\u00e0").replace("🎺", r"\uD83C\uDFBA")
        self.assertEqual(parse_public_folder(javascript_unicode, "root"), [{"id": "photo", "name": name}])

    def test_public_folder_rejects_truncated_or_unreadable_listings(self):
        row = ["photo", ["root"], "Photo.jpg", "image/jpeg"]
        for body in ("Sign in", folder_html([row] * 50), folder_html([row], "more"), folder_html(None)):
            with self.subTest(body=body[:80]):
                with self.assertRaises(DriveError):
                    parse_public_folder(body, "root")

    def test_embedded_listing_keeps_more_than_fifty_entries_and_decodes_entities(self):
        entries = [photo(f"photo{i}", f'Foto & {i} – l\'estate "2026".jpg') for i in range(75)]
        entries += [child(resourceKey="child-key")]
        actual = parse_embedded_folder(embedded_html(entries))
        self.assertEqual(len(actual), 76)
        self.assertEqual(actual[74]["name"], entries[74]["name"])
        self.assertEqual(actual[75]["mimeType"], FOLDER_MIME)
        self.assertEqual(actual[75]["resourceKey"], "child-key")

    def test_embedded_listing_rejects_missing_marker_and_malformed_entries(self):
        bodies = [
            "Sign in",
            '<div class="flip-entries"><div class="flip-entry" id="entry-photo"><a href="https://drive.google.com/file/d/photo/view">Photo</a></div></div>',
        ]
        for body in bodies:
            with self.subTest(body=body):
                with self.assertRaises(DriveError):
                    parse_embedded_folder(body)

    def test_folder_details_accepts_drive_account_paths_and_resource_keys(self):
        self.assertEqual(folder_details("https://drive.google.com/drive/u/2/folders/root/?resourcekey=key"), {
            "id": "root", "resourceKey": "key",
        })
        for link in ("http://drive.google.com/drive/folders/root", "https://example.com/drive/folders/root", "https://drive.google.com/file/d/root/view"):
            with self.subTest(link=link):
                with self.assertRaises(DriveError):
                    folder_details(link)


class DriveReadingTests(unittest.TestCase):
    def test_api_follows_pages_sorts_filenames_and_preserves_resource_keys(self):
        calls = []

        def fetch(url, *, headers, timeout):
            query = parse_qs(urlsplit(url).query)
            calls.append(query)
            self.assertEqual(headers.get("X-Goog-Drive-Resource-Keys"), "root/folder-key")
            self.assertEqual(query["q"], ["'root' in parents and trashed = false"])
            self.assertEqual(query["key"], ["test-key"])
            self.assertGreater(timeout, 0)
            if len(calls) == 1:
                return {"files": [photo("ten", "10.jpg"), {"id": "video", "name": "1.mp4", "mimeType": "video/mp4"}], "nextPageToken": "second"}
            return {"files": [photo("two", "2.jpg", resourceKey="photo-key")]}

        photos = read_drive_folder(folder("root", "folder-key"), api_key="test-key", fetch=fetch)
        self.assertEqual([entry["id"] for entry in photos], ["two", "ten"])
        self.assertEqual(photos[0]["resourceKey"], "photo-key")
        self.assertEqual(calls[1]["pageToken"], ["second"])
        self.assertNotIn("pageToken", calls[0])

    def test_api_rejects_repeated_pagination_tokens(self):
        calls = []

        def fetch(url, **kwargs):
            calls.append(url)
            return {"files": [photo("image")], "nextPageToken": "again"}

        with self.assertRaises(DriveError):
            read_entries(folder("root"), api_key="test-key", fetch=fetch)
        self.assertEqual(len(calls), 2)

    def test_api_requests_and_rejects_incomplete_search_results(self):
        calls = []

        def fetch(url, **kwargs):
            query = parse_qs(urlsplit(url).query)
            calls.append(query)
            self.assertIn("incompleteSearch", query["fields"][0].split(","))
            return {"files": [photo("partial")], "incompleteSearch": True, "nextPageToken": "second"}

        with self.assertRaises(DriveError):
            read_entries(folder("root"), api_key="test-key", fetch=fetch)
        self.assertEqual(len(calls), 1)

    def test_api_rejects_invalid_file_responses(self):
        for response in ({}, {"files": None}, {"files": {}}, {"files": [{"id": "image", "name": None, "mimeType": "image/jpeg"}]}):
            with self.subTest(response=response):
                with self.assertRaises(DriveError):
                    read_entries(folder("root"), api_key="test-key", fetch=lambda *args, **kwargs: response)

    def test_expired_deadline_prevents_another_network_request(self):
        calls = []

        def fetch(url, **kwargs):
            calls.append(url)
            return {"files": []}

        with self.assertRaises(DriveError):
            read_entries(folder("root"), api_key="test-key", fetch=fetch, deadline=time.monotonic() - 1)
        self.assertEqual(calls, [])

    def test_large_public_listing_falls_back_to_complete_embedded_view(self):
        entries = [photo(f"photo{i}", f"{i}.jpg") for i in range(75)]
        calls = []

        def fetch(url, **kwargs):
            calls.append(url)
            if urlsplit(url).path == "/embeddedfolderview":
                self.assertEqual(parse_qs(urlsplit(url).query)["resourcekey"], ["folder-key"])
                return embedded_html(entries)
            return folder_html([[entry["id"], ["root"], entry["name"], entry["mimeType"]] for entry in entries[:50]])

        actual = read_entries(folder("root", "folder-key"), api_key="", fetch=fetch)
        self.assertEqual(len(actual), 75)
        self.assertEqual([entry["name"] for entry in actual[:3]], ["0.jpg", "1.jpg", "2.jpg"])
        self.assertEqual(len(calls), 2)

    def test_empty_embedded_view_cannot_erase_inaccessible_folder(self):
        calls = []

        def fetch(url, **kwargs):
            calls.append(url)
            return embedded_html([]) if urlsplit(url).path == "/embeddedfolderview" else "Sign in"

        with self.assertRaises(DriveError):
            read_entries(folder("root"), api_key="", prefer_embedded=True, fetch=fetch)
        self.assertEqual(len(calls), 2)

    def test_empty_embedded_view_is_confirmed_by_public_folder(self):
        calls = []

        def fetch(url, **kwargs):
            calls.append(url)
            return embedded_html([]) if urlsplit(url).path == "/embeddedfolderview" else folder_html([])

        self.assertEqual(read_entries(folder("root"), api_key="", prefer_embedded=True, fetch=fetch), [])
        self.assertEqual(len(calls), 2)

    def test_nested_folders_deduplicate_cycles_photos_and_exclude_videos(self):
        calls = []

        def entries_reader(link):
            details = folder_details(link)
            calls.append(details)
            if details["id"] == "root":
                return [child(resourceKey="child-key"), photo("ten", "10.jpg")]
            return [child("root"), photo("ten", "10.jpg"), photo("two", "2.jpg"),
                    {"id": "video", "name": "movie.mp4", "mimeType": "video/mp4"}]

        actual = read_drive_folder(folder("root"), api_key="", entries_reader=entries_reader)
        self.assertEqual([entry["id"] for entry in actual], ["two", "ten"])
        self.assertEqual(calls, [{"id": "root", "resourceKey": ""}, {"id": "child", "resourceKey": "child-key"}])


class DriveCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="filarmonica-drive-tests-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def cache(self, fetch, **kwargs):
        return DriveCache(self.directory, api_key="test-key", fetch=fetch, **kwargs)

    def snapshot(self):
        return {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.directory.glob("*.json")}

    def test_nested_changes_renames_and_removals_refresh_when_parent_is_unchanged(self):
        listing = [photo("old")]
        calls = []

        def fetch(url, **kwargs):
            query = parse_qs(urlsplit(url).query)["q"][0]
            calls.append(query)
            return {"files": [child()] if query.startswith("'root'") else listing}

        cache = self.cache(fetch)
        self.assertEqual([entry["id"] for entry in cache.read_folder(folder("root"))], ["old"])
        self.assertEqual(cache.stats["changed"], 2)
        previous = self.snapshot()
        self.assertEqual(len(previous), 2)
        cache = self.cache(fetch)
        cache.read_folder(folder("root"))
        self.assertEqual(cache.stats["unchanged"], 2)
        self.assertEqual(self.snapshot(), previous)
        listing = [photo("old", "Renamed.jpg")]
        cache = self.cache(fetch)
        self.assertEqual(cache.read_folder(folder("root"))[0]["name"], "Renamed.jpg")
        self.assertEqual(cache.stats["changed"], 1)
        self.assertEqual(cache.stats["unchanged"], 1)
        listing = [photo("new")]
        self.assertEqual([entry["id"] for entry in self.cache(fetch).read_folder(folder("root"))], ["new"])
        listing = []
        self.assertEqual(self.cache(fetch).read_folder(folder("root")), [])
        self.assertEqual(len(calls), 10)

    def test_preferred_cache_works_offline_and_fetches_new_folders(self):
        self.cache(lambda *args, **kwargs: {"files": [photo("saved")]}).read_folder(folder("root"))
        calls = []

        def fetch(url, **kwargs):
            calls.append(url)
            return {"files": [photo("new")]}

        cache = self.cache(fetch, prefer_cache=True)
        self.assertEqual(cache.read_folder(folder("root"))[0]["id"], "saved")
        self.assertEqual(cache.stats["cached"], 1)
        self.assertEqual(calls, [])
        self.assertEqual(cache.read_folder(folder("new-folder"))[0]["id"], "new")
        self.assertEqual(len(calls), 1)

    def test_corrupted_cache_is_repaired(self):
        self.cache(lambda *args, **kwargs: {"files": [photo("saved")]}).read_folder(folder("root"))
        path, = self.directory.glob("*.json")
        path.write_text("{", encoding="utf-8")
        cache = self.cache(lambda *args, **kwargs: {"files": [photo("replacement")]}, prefer_cache=True)
        self.assertEqual(cache.read_folder(folder("root"))[0]["id"], "replacement")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["entries"][0]["id"], "replacement")
        self.assertEqual(list(self.directory.glob("*.tmp")), [])

    def test_invalid_cache_entry_schema_is_refetched(self):
        self.cache(lambda *args, **kwargs: {"files": [photo("saved")]}).read_folder(folder("root"))
        path, = self.directory.glob("*.json")
        path.write_text(json.dumps({"version": 1, "entries": [{"id": "saved", "name": None}]}), encoding="utf-8")
        cache = self.cache(lambda *args, **kwargs: {"files": [photo("replacement")]}, prefer_cache=True)
        self.assertEqual(cache.read_folder(folder("root"))[0]["id"], "replacement")
        self.assertEqual(cache.stats["cached"], 0)
        self.assertEqual(cache.stats["changed"], 1)

    def test_failed_refresh_preserves_cache_and_never_silently_returns_stale_photos(self):
        self.cache(lambda *args, **kwargs: {"files": [photo("saved")]}).read_folder(folder("root"))
        previous = self.snapshot()

        def fetch(*args, **kwargs):
            raise DriveError("HTTP 403")

        with self.assertRaisesRegex(DriveError, "HTTP 403"):
            self.cache(fetch).read_folder(folder("root"))
        self.assertEqual(self.snapshot(), previous)

    def test_timed_out_refresh_returns_before_fetch_finishes_and_preserves_cache(self):
        self.cache(lambda *args, **kwargs: {"files": [photo("saved")]}).read_folder(folder("root"))
        previous = self.snapshot()
        started = threading.Event()
        release = threading.Event()
        workers = []

        def fetch(url, **kwargs):
            started.set()
            if not release.wait(3):
                raise AssertionError("Test did not release the simulated slow request")
            return {"files": [photo("late-replacement")]}

        def tracked_executor(*args, **kwargs):
            executor = ThreadPoolExecutor(*args, **kwargs)
            workers.append(executor)
            return executor

        with patch("app.drive.ThreadPoolExecutor", side_effect=tracked_executor):
            with ThreadPoolExecutor(max_workers=1) as caller:
                future = caller.submit(
                    read_drive_folder, folder("root"), cache_directory=self.directory,
                    api_key="test-key", fetch=fetch, timeout=0.1,
                )
                try:
                    self.assertTrue(started.wait(1), "Refresh never started")
                    # The caller must receive the deadline error while the
                    # request is still blocked, without waiting for the network.
                    with self.assertRaises(DriveError):
                        future.result(timeout=1)
                    self.assertFalse(release.is_set())
                finally:
                    release.set()
                    for executor in workers:
                        executor.shutdown(wait=True, cancel_futures=True)
        # Join late workers before inspecting disk, so this proves they cannot
        # replace previously successful results after the caller has timed out.
        self.assertEqual(self.snapshot(), previous)
        self.assertEqual(list(self.directory.glob("*.tmp")), [])

    def test_shared_folder_is_requested_once_for_concurrent_readers(self):
        calls = []

        def fetch(url, **kwargs):
            calls.append(url)
            time.sleep(0.03)
            return {"files": [photo("shared")]}

        cache = self.cache(fetch)
        with ThreadPoolExecutor(max_workers=12) as executor:
            results = list(executor.map(cache.read_folder, [folder("root")] * 12))
        self.assertEqual(len(calls), 1)
        self.assertTrue(all([entry["id"] for entry in result] == ["shared"] for result in results))

    def test_fetch_concurrency_is_bounded_and_a_failure_releases_the_queue(self):
        active = 0
        peak = 0
        lock = threading.Lock()

        def fetch(url, **kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            try:
                time.sleep(0.03)
                if parse_qs(urlsplit(url).query)["q"][0].startswith("'folder0'"):
                    raise DriveError("Expected failure")
                return {"files": [photo("image")]}
            finally:
                with lock:
                    active -= 1

        cache = self.cache(fetch)
        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = [executor.submit(cache.read_folder, folder(f"folder{i}")) for i in range(24)]
            errors = [future.exception() for future in futures if future.exception() is not None]
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], DriveError)
        self.assertGreater(peak, 1)
        self.assertLessEqual(peak, 6)
        self.assertEqual(active, 0)


if __name__ == "__main__":
    unittest.main()
