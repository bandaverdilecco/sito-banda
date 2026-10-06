"""Read public Google Drive albums using Python, with an optional local cache.

No Google account is required. Large folders use the complete embedded view or
the optional Drive API key. A refresh must succeed before its listing is used;
an inaccessible folder can never silently become an empty or stale gallery.
"""

from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import hashlib
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from typing import Callable
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


FOLDER_MIME = 'application/vnd.google-apps.folder'
MAX_CONCURRENCY = 6
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
_IDENTIFIER = re.compile(r'[A-Za-z0-9_-]+')
Entry = dict[str, str]
Fetcher = Callable[..., str | bytes | dict]


class DriveError(ValueError):
    """A readable, complete listing could not be obtained."""


def folder_details(link: str) -> dict[str, str]:
    """Validate a public folder URL and retain its optional resource key."""
    try:
        parsed = urlsplit(link)
        match = re.fullmatch(r'/drive/(?:u/\d+/)?folders/([A-Za-z0-9_-]+)/?', parsed.path)
        valid = (parsed.scheme == 'https' and parsed.hostname == 'drive.google.com'
                 and not parsed.username and not parsed.password and parsed.port in (None, 443)
                 and not any(ord(char) < 32 for char in link) and '\\' not in link)
        resource_key = parse_qs(parsed.query).get('resourcekey', [''])[0]
        if not valid or not match or any(ord(char) < 32 for char in resource_key):
            raise ValueError()
    except (TypeError, ValueError, AttributeError) as exc:
        raise DriveError('Inserisci il link HTTPS di una cartella pubblica Google Drive.') from exc
    return {'id': match[1], 'resourceKey': resource_key}


def _folder_link(identifier: str, resource_key: str = '') -> str:
    link = f'https://drive.google.com/drive/folders/{identifier}'
    return link + '?' + urlencode({'resourcekey': resource_key}) if resource_key else link


def _decode_javascript_string(value: str) -> str:
    """Decode literal escapes without executing the page's JavaScript."""
    def replace(match):
        hexadecimal, unicode, continuation, char = match.groups()
        if hexadecimal or unicode:
            return chr(int(hexadecimal or unicode, 16))
        if continuation:
            return ''
        return {'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', 'f': '\f', 'v': '\v', '0': '\0'}.get(char, char)

    decoded = re.sub(r'\\(?:x([\da-f]{2})|u([\da-f]{4})|(\r?\n)|(.))', replace, value, flags=re.I | re.S)
    # JavaScript encodes non-BMP characters as two UTF-16 surrogate escapes.
    return decoded.encode('utf-16', 'surrogatepass').decode('utf-16')


def _validated_entries(entries) -> list[Entry]:
    if not isinstance(entries, list):
        raise DriveError('Risposta Drive priva dell’elenco file.')
    for entry in entries:
        if (not isinstance(entry, dict) or not isinstance(entry.get('id'), str)
                or not _IDENTIFIER.fullmatch(entry['id']) or not isinstance(entry.get('name'), str)
                or not isinstance(entry.get('mimeType'), str) or not entry['mimeType']
                or ('resourceKey' in entry and not isinstance(entry['resourceKey'], str))
                or any(ord(char) < 32 for char in entry.get('resourceKey', ''))):
            raise DriveError('Elemento Drive non valido: elenco non aggiornato.')
    return entries


def parse_public_entries(html: str, folder_id: str) -> list[Entry]:
    """Read the main folder page; reject the public view's 50-item cutoff."""
    match = re.search(r"window\[['\"]_DRIVE_ivd['\"]\]\s*=\s*(['\"])((?:\\.|(?!\1).)*)\1", html, re.S)
    if not match:
        raise DriveError('Cartella non leggibile: verifica che sia pubblica oppure configura GOOGLE_DRIVE_API_KEY.')
    try:
        data = json.loads(_decode_javascript_string(match[2]))
    except (ValueError, UnicodeError) as exc:
        raise DriveError('Elenco Drive non riconosciuto. Configura GOOGLE_DRIVE_API_KEY.') from exc
    if not isinstance(data, list) or not data or not isinstance(data[0], list):
        raise DriveError('Elenco Drive non riconosciuto. Configura GOOGLE_DRIVE_API_KEY.')
    rows = data[0]
    if len(rows) >= 50 or (len(data) > 1 and data[1]):
        raise DriveError('Elenco Drive incompleto. Configura GOOGLE_DRIVE_API_KEY e ripeti la sincronizzazione.')
    entries = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 4 or not isinstance(row[1], list):
            raise DriveError('Elemento Drive non riconosciuto nell’elenco pubblico.')
        if folder_id in row[1]:
            entries.append({'id': row[0], 'name': row[2], 'mimeType': row[3]})
    return _validated_entries(entries)


def parse_public_folder(html: str, folder_id: str) -> list[Entry]:
    """Return just image IDs and names from a complete public listing."""
    return [{'id': entry['id'], 'name': entry['name']}
            for entry in parse_public_entries(html, folder_id) if entry['mimeType'].startswith('image/')]


def parse_embedded_folder(html: str) -> list[Entry]:
    """Parse the complete embedded view, including nested folders and keys."""
    soup = BeautifulSoup(html, 'html.parser')
    container = soup.select_one('#entries, .flip-entries')
    if container is None:
        raise DriveError('Elenco completo Drive non leggibile. Configura GOOGLE_DRIVE_API_KEY.')
    entries = []
    for node in container.select('.flip-entry'):
        match = re.fullmatch(r'entry-([A-Za-z0-9_-]+)', node.get('id', ''))
        title = node.select_one('.flip-entry-title')
        anchor = node.find('a', href=True)
        if not match or title is None or anchor is None:
            raise DriveError('Elemento Drive non riconosciuto nell’elenco completo.')
        try:
            parsed = urlsplit(anchor['href'])
            if parsed.scheme != 'https' or not parsed.hostname:
                raise ValueError()
            resource_key = parse_qs(parsed.query).get('resourcekey', [''])[0]
        except ValueError as exc:
            raise DriveError('Collegamento Drive non valido nell’elenco completo.') from exc
        if '/folders/' in parsed.path:
            mime_type = FOLDER_MIME
        else:
            icons = [re.search(r'/type/([^?"#]+)', icon.get('src', '')) for icon in node.find_all('img')]
            mime_type = next((icon[1] for icon in icons if icon), '')
        entry = {'id': match[1], 'name': title.get_text(), 'mimeType': mime_type}
        if resource_key:
            entry['resourceKey'] = resource_key
        entries.append(entry)
    return _validated_entries(entries)


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise DriveError('Tempo massimo di sincronizzazione Drive superato. Riprova più tardi.')
    return remaining


def _http_get(url: str, *, headers: dict[str, str], timeout: float) -> bytes:
    """Bound each request and response size; never include keys in errors."""
    request = Request(url, headers={'User-Agent': 'FilarmonicaCMS/1.0', **headers})
    request_deadline = time.monotonic() + timeout
    try:
        with urlopen(request, timeout=timeout) as response:
            chunks = []
            size = 0
            while True:
                _remaining(request_deadline)
                chunk = response.read1(64 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise DriveError('Risposta Drive troppo grande. Configura GOOGLE_DRIVE_API_KEY.')
                chunks.append(chunk)
            return b''.join(chunks)
    except HTTPError as exc:
        raise DriveError(f'Google Drive ha risposto con HTTP {exc.code}. Verifica condivisione e chiave API.') from exc
    except (URLError, OSError, HTTPException) as exc:
        raise DriveError('Google Drive non raggiungibile. Riprova più tardi.') from exc


def _get(url: str, headers: dict[str, str], fetch: Fetcher, deadline: float):
    result = fetch(url, headers=headers, timeout=min(30.0, _remaining(deadline)))
    _remaining(deadline)
    try:
        return result.decode('utf-8') if isinstance(result, bytes) else result
    except UnicodeError as exc:
        raise DriveError('Risposta Drive non riconosciuta.') from exc


def _name_key(entry: Entry):
    # Case/accent-insensitive natural order, independent of installed OS locales.
    name = ''.join(char for char in unicodedata.normalize('NFKD', entry['name'].casefold())
                   if not unicodedata.combining(char))
    return tuple((1, int(part)) if part.isascii() and part.isdigit() else (0, part)
                 for part in re.split(r'([0-9]+)', name)), entry['id']


def read_entries(link: str, api_key: str | None = None, prefer_embedded: bool = False,
                 fetch: Fetcher | None = None, deadline: float | None = None) -> list[Entry]:
    """Read one folder completely. ``fetch`` is injectable for offline tests."""
    details = folder_details(link)
    identifier, resource_key = details['id'], details['resourceKey']
    fetch = fetch or _http_get
    deadline = deadline if deadline is not None else time.monotonic() + 120
    _remaining(deadline)
    if api_key:
        entries = []
        page_token = ''
        seen_tokens = set()
        while True:
            query = {'key': api_key, 'q': f"'{identifier}' in parents and trashed = false",
                     'fields': 'nextPageToken,incompleteSearch,files(id,name,mimeType,resourceKey)', 'pageSize': '1000'}
            if page_token:
                query['pageToken'] = page_token
            headers = {'X-Goog-Drive-Resource-Keys': f'{identifier}/{resource_key}'} if resource_key else {}
            body = _get('https://www.googleapis.com/drive/v3/files?' + urlencode(query), headers, fetch, deadline)
            try:
                data = json.loads(body) if isinstance(body, str) else body
            except (TypeError, ValueError) as exc:
                raise DriveError('Risposta Drive non riconosciuta.') from exc
            if not isinstance(data, dict) or data.get('incompleteSearch'):
                raise DriveError('Ricerca Drive incompleta. Riprova la sincronizzazione.')
            entries.extend(_validated_entries(data.get('files')))
            page_token = data.get('nextPageToken', '')
            if not isinstance(page_token, str) or (page_token and page_token in seen_tokens):
                raise DriveError('Paginazione Drive non valida.')
            if not page_token:
                break
            seen_tokens.add(page_token)
    else:
        public_url = _folder_link(identifier, resource_key)

        def read_public():
            body = _get(public_url, {}, fetch, deadline)
            if not isinstance(body, str):
                raise DriveError('Risposta Drive non riconosciuta.')
            return parse_public_entries(body, identifier)

        entries = None
        if not prefer_embedded:
            try:
                entries = read_public()
            except DriveError:
                # The complete view is also useful when the main view changes.
                _remaining(deadline)
        if entries is None:
            query = {'id': identifier}
            if resource_key:
                query['resourcekey'] = resource_key
            body = _get('https://drive.google.com/embeddedfolderview?' + urlencode(query), {}, fetch, deadline)
            if not isinstance(body, str):
                raise DriveError('Risposta Drive non riconosciuta.')
            entries = parse_embedded_folder(body)
            if not entries:
                # A private folder can present an empty embedded shell. Confirm
                # emptiness using the actual folder before removing any photos.
                entries = read_public()
    _remaining(deadline)
    return sorted(_validated_entries(entries), key=_name_key)


def _walk_folders(link: str, entries_reader: Callable[[str], list[Entry]], deadline: float) -> list[Entry]:
    """Traverse without holding parent workers while waiting for their children."""
    queue = deque([link])
    visited = set()
    photos = {}
    pending = {}
    executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENCY, thread_name_prefix='drive')
    try:
        while queue or pending:
            _remaining(deadline)
            while queue and len(pending) < MAX_CONCURRENCY:
                folder = queue.popleft()
                identifier = folder_details(folder)['id']
                if identifier in visited:
                    continue
                visited.add(identifier)
                pending[executor.submit(entries_reader, folder)] = identifier
            if not pending:
                continue
            completed, _ = wait(pending, timeout=_remaining(deadline), return_when=FIRST_COMPLETED)
            _remaining(deadline)
            for future in sorted(completed, key=lambda item: pending[item]):
                del pending[future]
                for entry in _validated_entries(future.result()):
                    if entry['mimeType'].startswith('image/'):
                        photos[entry['id']] = entry
                    elif entry['mimeType'] == FOLDER_MIME:
                        queue.append(_folder_link(entry['id'], entry.get('resourceKey', '')))
        return sorted(photos.values(), key=_name_key)
    finally:
        # A stalled request cannot prolong the caller's overall deadline. Pending
        # requests check the deadline before writing their cache results.
        executor.shutdown(wait=False, cancel_futures=True)


def _normalize(entries: list[Entry]) -> list[Entry]:
    return sorted(({'id': entry['id'], 'name': entry['name'], 'mimeType': entry['mimeType'],
                    **({'resourceKey': entry['resourceKey']} if entry.get('resourceKey') else {})}
                   for entry in _validated_entries(entries)), key=lambda entry: entry['id'])


class DriveCache:
    """One refresh session, sharing requests across concurrent album reads.

    Instantiate a new session for each subsequent refresh. Existing version-1
    cache files remain compatible. Normal sessions recheck every nested folder;
    ``prefer_cache`` must be explicitly requested for an offline read.
    """

    def __init__(self, directory: Path | str, *, api_key: str | None = None, prefer_cache: bool = False,
                 fetch: Fetcher | None = None, timeout: float = 120):
        self.directory = Path(directory)
        self.api_key = api_key
        self.prefer_cache = prefer_cache
        self.fetch = fetch
        self.timeout = timeout
        self.stats = dict(checked=0, changed=0, unchanged=0, cached=0)
        self._pending: dict[str, Future] = {}
        self._lock = threading.Lock()
        self._limit = threading.BoundedSemaphore(MAX_CONCURRENCY)

    def _count(self, key: str):
        with self._lock:
            self.stats[key] += 1

    def _refresh(self, link: str, filename: Path, deadline: float) -> list[Entry]:
        cached = None
        try:
            data = json.loads(filename.read_text(encoding='utf-8'))
            if isinstance(data, dict) and data.get('version') == 1:
                cached = _normalize(data.get('entries'))
        except (FileNotFoundError, ValueError, UnicodeError):
            pass
        _remaining(deadline)
        if self.prefer_cache and cached is not None:
            self._count('cached')
            return cached
        entries = _normalize(read_entries(link, self.api_key, cached is not None and len(cached) >= 50,
                                          fetch=self.fetch, deadline=deadline))
        self._count('checked')
        if entries == cached:
            self._count('unchanged')
            return entries
        _remaining(deadline)
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.directory,
                                             prefix=filename.name + '.', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({'version': 1, 'entries': entries}, stream, ensure_ascii=False, separators=(',', ':'))
                stream.write('\n')
            _remaining(deadline)
            os.replace(temporary, filename)
            self._count('changed')
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return entries

    def _entries(self, link: str, deadline: float) -> list[Entry]:
        details = folder_details(link)
        # Match JSON.stringify([id, resourceKey, mode]) used by old caches.
        identity = json.dumps([details['id'], details['resourceKey'], 'api' if self.api_key else 'public'],
                              ensure_ascii=False, separators=(',', ':'))
        key = hashlib.sha256(identity.encode('utf-8')).hexdigest()
        with self._lock:
            existing = self._pending.get(key)
            if existing is None:
                existing = self._pending[key] = Future()
                owner = True
            else:
                owner = False
        if not owner:
            try:
                return existing.result(timeout=_remaining(deadline))
            except TimeoutError as exc:
                raise DriveError('Tempo massimo di sincronizzazione Drive superato.') from exc
        acquired = False
        try:
            acquired = self._limit.acquire(timeout=_remaining(deadline))
            if not acquired:
                raise DriveError('Tempo massimo di sincronizzazione Drive superato.')
            result = self._refresh(link, self.directory / f'{key}.json', deadline)
            existing.set_result(result)
            return result
        except BaseException as exc:
            existing.set_exception(exc)
            raise
        finally:
            if acquired:
                self._limit.release()

    def read_folder(self, link: str) -> list[Entry]:
        deadline = time.monotonic() + self.timeout
        return _walk_folders(link, lambda folder: self._entries(folder, deadline), deadline)


def read_drive_folder(link: str, *, cache_directory: Path | str | None = None, api_key: str | None = None,
                      timeout: float = 120, prefer_cache: bool = False, fetch: Fetcher | None = None,
                      entries_reader: Callable[[str], list[Entry]] | None = None) -> list[Entry]:
    """Collect image files from an album and all its nested public folders."""
    if cache_directory is not None and entries_reader is None:
        return DriveCache(cache_directory, api_key=api_key, timeout=timeout,
                          prefer_cache=prefer_cache, fetch=fetch).read_folder(link)
    deadline = time.monotonic() + timeout
    reader = entries_reader or (lambda folder: read_entries(folder, api_key, fetch=fetch, deadline=deadline))
    return _walk_folders(link, reader, deadline)
