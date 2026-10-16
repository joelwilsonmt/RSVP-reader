import os
import re
import json
import shutil
import tempfile
import hashlib
import sqlite3
import zipfile
import mimetypes
import posixpath
import threading
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote
from datetime import datetime, timedelta, timezone

from flask import Flask, render_template, request, jsonify, abort, send_file
from werkzeug.exceptions import HTTPException

app = Flask(__name__)

_ENV_BOOKS_DIR = Path(os.environ.get("BOOKS_DIR", "/books")).resolve()
DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data")).resolve()
FS_ROOT = Path(os.environ.get("FS_ROOT", "/")).resolve()
PORT = int(os.environ.get("PORT", 5002))
CACHE_DIR = DATA_DIR / "text_cache"
COVERS_DIR = DATA_DIR / "covers"

CACHE_VERSION = 6
SUPPORTED_EXTS = {".epub", ".pdf", ".txt", ".md", ".mobi", ".azw", ".azw3"}
MOBI_EXTS = {".mobi", ".azw", ".azw3"}
COVER_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp")  # ordered: find_cover search order
BOOK_ID_RE = re.compile(r"^[0-9a-f]{32}$")

DEFAULT_SETTINGS = {"wpm": 350, "pivot_guides": True, "ramp": True}
WPM_MIN, WPM_MAX = 100, 800
MAX_SECONDS_PER_SAVE = 600

_db_lock = threading.Lock()
_db_conn = None
_config_lock = threading.RLock()


# ── config ────────────────────────────────────────────────────────────────────

def _config_path() -> Path:
    return DATA_DIR / "config.json"


def atomic_write(path: Path, data) -> None:
    """Write via a temp file + rename so readers never see a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data.encode() if isinstance(data, str) else data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_config() -> dict:
    try:
        cfg = json.loads(_config_path().read_text())
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def write_config(updates: dict) -> dict:
    """Merge updates into config.json (read-modify-write under a lock)."""
    with _config_lock:
        cfg = read_config()
        cfg.update(updates)
        atomic_write(_config_path(), json.dumps(cfg, indent=2))
    return cfg


def get_books_dir() -> Path:
    books_dir = read_config().get("books_dir")
    if books_dir:
        p = Path(books_dir).expanduser().resolve()
        if is_within(p, FS_ROOT):  # a folder saved before FS_ROOT was tightened is ignored
            return p
    return _ENV_BOOKS_DIR


def set_books_dir(new_path: str) -> Path:
    p = Path(new_path).expanduser().resolve()
    if not is_within(p, FS_ROOT):
        raise ValueError(f"Outside allowed root ({FS_ROOT}): {p}")
    if not p.exists() or not p.is_dir():
        raise ValueError(f"Not a directory: {p}")
    write_config({"books_dir": str(p)})
    return p


def get_settings() -> dict:
    stored = read_config().get("settings") or {}
    merged = {**DEFAULT_SETTINGS, **{k: v for k, v in stored.items() if k in DEFAULT_SETTINGS}}
    try:  # a speed saved under an older, wider range is pulled back inside it
        merged["wpm"] = max(WPM_MIN, min(WPM_MAX, int(merged["wpm"])))
    except (TypeError, ValueError):
        merged["wpm"] = DEFAULT_SETTINGS["wpm"]
    return merged


def update_settings(partial: dict) -> dict:
    with _config_lock:
        return _update_settings(partial)


def _update_settings(partial: dict) -> dict:
    settings = get_settings()
    if "wpm" in partial:
        try:
            wpm = int(partial["wpm"])
        except (TypeError, ValueError):
            raise ValueError("wpm must be a number")
        settings["wpm"] = max(WPM_MIN, min(WPM_MAX, wpm))
    for key in ("pivot_guides", "ramp"):
        if key in partial:
            if not isinstance(partial[key], bool):
                raise ValueError(f"{key} must be true or false")
            settings[key] = partial[key]
    write_config({"settings": settings})
    return settings


# ── time ──────────────────────────────────────────────────────────────────────

def local_now() -> datetime:
    """Current time in the TZ env zone (falls back to the process local zone)."""
    tz_name = os.environ.get("TZ")
    if tz_name:
        try:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(tz_name))
        except Exception:
            pass
    return datetime.now().astimezone()


def local_today() -> str:
    return local_now().strftime("%Y-%m-%d")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── database ──────────────────────────────────────────────────────────────────

SCHEMA = """
    CREATE TABLE IF NOT EXISTS books_progress (
        book_id      TEXT PRIMARY KEY,
        path         TEXT NOT NULL,
        title        TEXT NOT NULL,
        author       TEXT,
        word_index   INTEGER NOT NULL DEFAULT 0,
        total_words  INTEGER NOT NULL DEFAULT 0,
        updated_at   TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS daily_stats (
        day      TEXT PRIMARY KEY,
        words    INTEGER NOT NULL DEFAULT 0,
        seconds  INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS meta_cache (
        path        TEXT PRIMARY KEY,
        mtime       REAL NOT NULL,
        size        INTEGER NOT NULL,
        book_id     TEXT NOT NULL,
        title       TEXT,
        author      TEXT,
        has_cover   INTEGER NOT NULL DEFAULT 0,
        word_count  INTEGER
    );
"""


def get_db():
    """Shared connection; callers must hold _db_lock while using it."""
    global _db_conn
    with _db_lock:
        if _db_conn is None:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(DATA_DIR / "progress.db"), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)
            _migrate_legacy_progress(conn)
            conn.commit()
            _db_conn = conn
    return _db_conn


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _migrate_legacy_progress(conn):
    """Move relpath-keyed `progress` rows into book_id-keyed `books_progress`. Idempotent.

    The old table is kept as `progress_legacy`; rows whose file isn't there yet (books
    volume not mounted, folder changed) stay unmigrated and are retried on each start.
    """
    if _table_exists(conn, "progress"):
        if _table_exists(conn, "progress_legacy"):
            conn.execute("DROP TABLE progress")
        else:
            conn.execute("ALTER TABLE progress RENAME TO progress_legacy")
    if not _table_exists(conn, "progress_legacy"):
        return
    cols = {r[1] for r in conn.execute("PRAGMA table_info(progress_legacy)")}
    if "migrated" not in cols:
        conn.execute("ALTER TABLE progress_legacy ADD COLUMN migrated INTEGER NOT NULL DEFAULT 0")
    books_dir = get_books_dir()
    for row in conn.execute("SELECT rowid, * FROM progress_legacy WHERE migrated = 0").fetchall():
        abs_path = (books_dir / row["relpath"].lstrip("/")).resolve()
        if not abs_path.is_file():
            continue
        try:
            book_id = compute_book_id(abs_path)
        except OSError:
            continue
        conn.execute(
            """INSERT OR IGNORE INTO books_progress
               (book_id, path, title, author, word_index, total_words, updated_at)
               VALUES (?, ?, ?, NULL, ?, ?, ?)""",
            (book_id, str(abs_path), row["title"], row["word_index"],
             row["total_words"], _normalize_legacy_ts(row["updated_at"])),
        )
        conn.execute("UPDATE progress_legacy SET migrated = 1 WHERE rowid = ?", (row["rowid"],))


def _normalize_legacy_ts(ts) -> str:
    """Legacy rows may hold SQLite CURRENT_TIMESTAMP ('YYYY-MM-DD HH:MM:SS', UTC)."""
    if not ts:
        return utc_now_iso()
    ts = str(ts)
    if re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", ts):
        return ts.replace(" ", "T") + "Z"
    return ts


def db_query(sql: str, params=()) -> list:
    conn = get_db()
    with _db_lock:
        return conn.execute(sql, params).fetchall()


def db_execute(sql: str, params=()):
    conn = get_db()
    with _db_lock:
        conn.execute(sql, params)
        conn.commit()


# ── path safety ───────────────────────────────────────────────────────────────

def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def confine(raw: str, root: Path = None) -> Path:
    """Resolve an absolute path (following symlinks); 403 unless inside FS_ROOT (and root)."""
    if not raw:
        abort(400, "Missing path")
    try:
        p = Path(raw).expanduser().resolve()
    except (ValueError, OSError, RuntimeError):  # embedded NUL, symlink loop, unknown ~user
        abort(400, "Invalid path")
    if not is_within(p, FS_ROOT) or (root is not None and not is_within(p, root)):
        abort(403, "Path is outside the allowed folder")
    return p


def resolve_book(raw: str) -> Path:
    """Confine a book path, reject unsupported extensions (400) and missing files (404)."""
    p = confine(raw)
    if p.suffix.lower() not in SUPPORTED_EXTS:
        abort(400, f"Unsupported file type: {p.suffix or '(none)'}")
    if not p.is_file():
        abort(404, f"File not found: {p}")
    return p


def book_format(path: Path) -> str:
    return path.suffix.lower().lstrip(".")


# ── book identity ─────────────────────────────────────────────────────────────

def compute_book_id(path: Path) -> str:
    """sha256(size + first 1 MiB + last 64 KiB), first 32 hex chars."""
    size = path.stat().st_size
    h = hashlib.sha256(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(1024 * 1024))
        f.seek(max(0, size - 64 * 1024))
        h.update(f.read(64 * 1024))
    return h.hexdigest()[:32]


def cached_meta_row(path: Path, st):
    rows = db_query(
        "SELECT * FROM meta_cache WHERE path = ? AND mtime = ? AND size = ?",
        (str(path), st.st_mtime, st.st_size),
    )
    return rows[0] if rows else None


def get_book_id(path: Path) -> str:
    st = path.stat()
    row = cached_meta_row(path, st)
    return row["book_id"] if row else compute_book_id(path)


def store_meta(path: Path, book_id: str, title, author, has_cover: bool, word_count=None):
    st = path.stat()
    db_execute(
        """INSERT INTO meta_cache (path, mtime, size, book_id, title, author, has_cover, word_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(path) DO UPDATE SET
             mtime=excluded.mtime, size=excluded.size, book_id=excluded.book_id,
             title=excluded.title, author=excluded.author, has_cover=excluded.has_cover,
             word_count=COALESCE(excluded.word_count,
                                 CASE WHEN meta_cache.book_id = excluded.book_id
                                      THEN meta_cache.word_count END)""",
        (str(path), st.st_mtime, st.st_size, book_id, title, author, int(has_cover), word_count),
    )


# ── covers ────────────────────────────────────────────────────────────────────

def find_cover(book_id: str):
    if not BOOK_ID_RE.match(book_id or ""):
        return None
    for ext in COVER_EXTS:
        p = COVERS_DIR / f"{book_id}{ext}"
        if p.is_file():
            return p
    return None


def save_cover(book_id: str, data: bytes, name_or_type: str) -> bool:
    """Write cover bytes; SVG and unknown types are skipped (not safe to serve inline)."""
    ext = Path(name_or_type).suffix.lower() if "." in name_or_type else ""
    if ext not in COVER_EXTS:
        ext = mimetypes.guess_extension(name_or_type) or ""
    if ext == ".jpe":
        ext = ".jpg"
    if ext not in COVER_EXTS or not data:
        return False
    atomic_write(COVERS_DIR / f"{book_id}{ext}", data)
    for other in COVER_EXTS:  # a re-extracted cover may change type; keep exactly one
        if other != ext:
            (COVERS_DIR / f"{book_id}{other}").unlink(missing_ok=True)
    return True


# ── html → blocks ─────────────────────────────────────────────────────────────

BLOCK_TAGS = ["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote",
              "section", "article", "header", "footer", "aside", "pre", "table", "tr",
              "dt", "dd", "figure", "figcaption", "ul", "ol", "hr", "body"]
MARK_RE = re.compile(r"^\x00M(\d+)\x00$")


def html_to_blocks(html, mark_fn=None) -> tuple[list[str], list[tuple[str, int]]]:
    """Convert HTML to paragraph blocks.

    mark_fn(soup) may return [(tag, label)]; each label is reported with the index of
    the first block at or after that tag, so callers can map anchors/headings to words.
    """
    from bs4 import BeautifulSoup

    soup = html if not isinstance(html, (str, bytes)) else BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "head", "title"]):
        tag.decompose()

    labels = []
    for tag, label in (mark_fn(soup) if mark_fn else []):
        tag.insert_before(f"\n\n\x00M{len(labels)}\x00\n\n")
        labels.append(label)
    for img in soup.find_all("img"):
        alt = (img.get("alt") or "").strip()
        if 0 < len(alt) <= 2 and alt.isalpha():
            img.replace_with(alt)  # drop-cap images carry their letter in alt
    for br in soup.find_all("br"):
        br.replace_with("\n\n")
    for tag in soup.find_all(BLOCK_TAGS):
        tag.insert_before("\n\n")
        tag.insert_after("\n\n")
    for tag in soup.find_all(re.compile(r"^mbp:pagebreak$")):
        tag.insert_before("\n\n")

    blocks, marks = [], []
    for chunk in re.split(r"\n\s*\n", soup.get_text()):
        chunk = re.sub(r"\s+", " ", chunk).strip()
        m = MARK_RE.match(chunk)
        if m:
            marks.append((labels[int(m.group(1))], len(blocks)))
        elif chunk:
            blocks.append(chunk)
    return blocks, marks


def first_heading(soup) -> str | None:
    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = re.sub(r"\s+", " ", tag.get_text(" ")).strip()
        if text:
            return text
    return None


# ── extraction: epub ──────────────────────────────────────────────────────────

OPF_NS = "{http://www.idpf.org/2007/opf}"
DC_NS = "{http://purl.org/dc/elements/1.1/}"
CONTAINER_NS = "{urn:oasis:names:tc:opendocument:xmlns:container}"


def read_epub_opf(path: Path) -> dict:
    """Fast metadata read: title, author and cover bytes straight from the OPF."""
    with zipfile.ZipFile(path) as z:
        container = ET.fromstring(z.read("META-INF/container.xml"))
        rootfile = container.find(f".//{CONTAINER_NS}rootfile").get("full-path")
        opf = ET.fromstring(z.read(rootfile))
        opf_dir = posixpath.dirname(rootfile)

        def dc(name):
            el = opf.find(f".//{DC_NS}{name}")
            text = (el.text or "").strip() if el is not None else ""
            return text or None

        items = [
            {"id": it.get("id", ""), "href": it.get("href", ""),
             "type": it.get("media-type", ""), "props": it.get("properties", "")}
            for it in opf.iter(f"{OPF_NS}item")
        ]
        cover = _pick_epub_cover(opf, items)
        cover_data = None
        if cover:
            name = posixpath.normpath(posixpath.join(opf_dir, unquote(cover["href"])))
            try:
                cover_data = (z.read(name), cover["type"] or name)
            except KeyError:
                cover_data = None
    return {"title": dc("title"), "author": dc("creator"), "cover": cover_data}


def _pick_epub_cover(opf, items: list[dict]):
    images = [it for it in items if it["type"].startswith("image/")]
    for it in images:
        if "cover-image" in it["props"].split():
            return it
    for meta in opf.iter(f"{OPF_NS}meta"):
        if meta.get("name") == "cover":
            match = next((it for it in images if it["id"] == meta.get("content")), None)
            if match:
                return match
    return next((it for it in images
                 if "cover" in it["id"].lower() or "cover" in it["href"].lower()), None)


def _flatten_toc(entries) -> list[tuple[str, str]]:
    if not isinstance(entries, (list, tuple)):
        entries = [entries] if entries else []  # ebooklib returns a bare Link for an empty NCX
    out = []
    for entry in entries:
        if isinstance(entry, (tuple, list)) and len(entry) == 2:
            section, children = entry
            if getattr(section, "href", ""):
                out.append((section.title, section.href))
            out.extend(_flatten_toc(children))
        elif hasattr(entry, "href"):
            if entry.href:
                out.append((entry.title, entry.href))
    return out


# A chapter label after sentence-ending punctuation: "...dear friend. CHAPTER XVII."
_CHAPTER_LABEL = re.compile(
    r"[.!?…\"”’)\]]\s+((?:chapter|book|part|volume|letter)\s+(?:\d+|[ivxlcdm]+)(?=$|[\s.:,—–-]).*)$",
    re.I)


def clean_toc_title(title: str) -> str:
    """Some TOCs prefix the label with a text snippet ("...dear friend. CHAPTER XVII.")."""
    title = re.sub(r"\s+", " ", title or "").strip()
    m = _CHAPTER_LABEL.search(title)
    if m:
        title = m.group(1)
    return title.rstrip(".").strip()


def _norm_href(href: str) -> str:
    return posixpath.normpath(unquote(href or "")).lstrip("./")


def _extract_epub(path: Path) -> dict:
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        book = epub.read_epub(str(path), options={"ignore_ncx": False})

    toc = [(clean_toc_title(t), h) for t, h in _flatten_toc(book.toc)]
    wanted = {}  # normalized file name -> set of fragment ids
    for _, href in toc:
        name, _, frag = href.partition("#")
        wanted.setdefault(_norm_href(name), set()).add(frag)

    blocks, file_start, anchor_block, headings = [], {}, {}, []
    for idref, _linear in book.spine:
        item = book.get_item_with_id(idref)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        name = _norm_href(item.get_name())
        soup = BeautifulSoup(item.get_content(), "html.parser")
        heading = first_heading(soup)
        frags = wanted.get(name) or wanted.get(posixpath.basename(name)) or set()

        def mark_fn(s, frags=frags):
            return [(el, el["id"]) for el in s.find_all(id=True) if el["id"] in frags]

        item_blocks, marks = html_to_blocks(soup, mark_fn)
        start = len(blocks)
        file_start[name] = start
        file_start.setdefault(posixpath.basename(name), start)
        for frag, idx in marks:
            anchor_block.setdefault((name, frag), start + idx)
        if heading:
            headings.append((heading, start))
        blocks.extend(item_blocks)

    chapter_marks = []
    for title, href in toc:
        name, _, frag = href.partition("#")
        name = _norm_href(name)
        idx = anchor_block.get((name, frag)) if frag else None
        if idx is None:
            idx = file_start.get(name, file_start.get(posixpath.basename(name)))
        if idx is not None and title:
            chapter_marks.append((title, idx))
    if not chapter_marks:
        chapter_marks = headings

    try:
        opf = read_epub_opf(path)
    except Exception:
        opf = {"title": None, "author": None, "cover": None}
    return {"title": opf["title"], "author": opf["author"], "cover": opf["cover"],
            "blocks": blocks, "marks": chapter_marks}


# ── extraction: mobi ──────────────────────────────────────────────────────────

def _extract_mobi(path: Path) -> dict:
    import mobi
    from bs4 import BeautifulSoup

    tempdir, filepath = mobi.extract(str(path))
    try:
        out = Path(filepath)
        if out.suffix.lower() == ".epub":
            return _extract_epub(out)
        if out.suffix.lower() == ".pdf":
            return _extract_pdf(out)
        soup = BeautifulSoup(out.read_bytes(), "html.parser")
        has_headings = bool(soup.find(["h1", "h2"]))

        def mark_fn(s):
            if has_headings:
                return [(h, first_heading_text(h)) for h in s.find_all(["h1", "h2"])
                        if first_heading_text(h)]
            breaks = s.find_all(re.compile(r"^mbp:pagebreak$"))
            return [(b, f"Section {i + 2}") for i, b in enumerate(breaks)]

        blocks, marks = html_to_blocks(soup, mark_fn)
        if marks and not has_headings:
            marks = [("Section 1", 0)] + marks
        return {"title": None, "author": None, "cover": None, "blocks": blocks, "marks": marks}
    finally:
        shutil.rmtree(tempdir, ignore_errors=True)


def first_heading_text(tag) -> str:
    return re.sub(r"\s+", " ", tag.get_text(" ")).strip()


# ── extraction: pdf ───────────────────────────────────────────────────────────

HF_MAX_LEN = 120
PAGE_NUM_RE = re.compile(r"^\s*(page\s+)?\d+(\s*(of|/)\s*\d+)?\s*$", re.IGNORECASE)
PARA_END_RE = re.compile(r"[.?!:\"”’]$")
JUNK_TITLE_RE = re.compile(
    r"^(microsoft (word|powerpoint) - |untitled|unknown|document\d*$)|\.(docx?|pdf|indd|rtf|tex|dvi)$",
    re.IGNORECASE,
)


def clean_pdf_meta(value) -> str | None:
    if not value:
        return None
    value = re.sub(r"\s+", " ", str(value)).strip()
    if not value or JUNK_TITLE_RE.search(value):
        return None
    return value


def _norm_hf(line: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\d+", "", line)).strip().lower()


def _edge_lines(lines: list[str]) -> list[int]:
    """First/last non-blank line indices; none for single-line pages or long lines."""
    idx = [i for i, l in enumerate(lines) if l.strip()]
    if len(idx) < 2:
        return []
    return sorted(i for i in {idx[0], idx[-1]} if len(lines[i].strip()) <= HF_MAX_LEN)


def clean_pdf_pages(pages: list[str]) -> list[list[str]]:
    """Turn raw per-page text into per-page paragraph blocks (see contract heuristics)."""
    page_lines = [p.replace("\r\n", "\n").replace("\r", "\n").split("\n") for p in pages]

    # Repeated header/footer lines
    junk = set()
    if len(pages) >= 4:
        counts = {}
        for lines in page_lines:
            for norm in {_norm_hf(lines[i]) for i in _edge_lines(lines)}:
                if norm:
                    counts[norm] = counts.get(norm, 0) + 1
        junk = {n for n, c in counts.items() if c >= 0.4 * len(pages)}

    cleaned = []
    for lines in page_lines:
        edges = set(_edge_lines(lines))
        keep = []
        for i, line in enumerate(lines):
            if PAGE_NUM_RE.match(line):
                continue
            if i in edges and _norm_hf(line) in junk:
                continue
            keep.append(line.strip())
        cleaned.append(keep)

    nonblank = [l for lines in cleaned for l in lines if l]
    avg = sum(len(l) for l in nonblank) / len(nonblank) if nonblank else 0
    return [_pdf_paragraphs(lines, avg) for lines in cleaned]


def _pdf_paragraphs(lines: list[str], avg: float) -> list[str]:
    blocks, cur = [], ""
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line:
            if cur:
                blocks.append(cur)
            cur = ""
            continue
        nxt = next((l for l in lines[i:] if l), "")
        if line.endswith("-") and len(line) > 1 and line[-2].isalpha() and nxt[:1].islower():
            # De-hyphenate: glue onto the next non-blank line
            while i < len(lines) and not lines[i]:
                i += 1
            if i < len(lines):
                lines = lines[:i] + [line[:-1] + lines[i]] + lines[i + 1:]
                continue
        cur = f"{cur} {line}" if cur else line
        if (nxt and PARA_END_RE.search(line) and (nxt[:1].isupper() or nxt[:1] in "\"“")
                and len(line) < 0.75 * avg):
            blocks.append(cur)
            cur = ""
    if cur:
        blocks.append(cur)
    return blocks


def _pdf_outline(reader, items, depth=0) -> list[tuple[str, int]]:
    out = []
    for it in items:
        if isinstance(it, list):
            if depth < 1:
                out.extend(_pdf_outline(reader, it, depth + 1))
            continue
        try:
            page = reader.get_destination_page_number(it)
        except Exception:
            continue
        title = re.sub(r"\s+", " ", str(getattr(it, "title", "") or "")).strip()
        if title and page is not None:
            out.append((title, page))
    return out


def _extract_pdf(path: Path) -> dict:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    page_blocks = clean_pdf_pages([page.extract_text() or "" for page in reader.pages])

    blocks, page_start = [], []
    for pblocks in page_blocks:
        if (blocks and pblocks and not PARA_END_RE.search(blocks[-1])
                and pblocks[0][:1].islower()):
            # Paragraph continues across the page break
            page_start.append(len(blocks) - 1)
            blocks[-1] = f"{blocks[-1]} {pblocks[0]}"
            blocks.extend(pblocks[1:])
        else:
            page_start.append(len(blocks))
            blocks.extend(pblocks)

    try:
        outline = _pdf_outline(reader, reader.outline)
    except Exception:
        outline = []
    marks = [(t, page_start[p]) for t, p in outline if 0 <= p < len(page_start)]
    meta = _pdf_meta(reader)
    return {"title": meta["title"], "author": meta["author"], "cover": None,
            "blocks": blocks, "marks": marks}


def _pdf_meta(reader) -> dict:
    try:
        info = reader.metadata or {}
    except Exception:
        info = {}
    return {"title": clean_pdf_meta(info.get("/Title")),
            "author": clean_pdf_meta(info.get("/Author"))}


# ── extraction: txt / md ──────────────────────────────────────────────────────

def split_blocks(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return [b for b in (re.sub(r"\s+", " ", c).strip() for c in re.split(r"\n\s*\n", text)) if b]


def _extract_txt(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return {"title": None, "author": None, "cover": None, "blocks": split_blocks(text), "marks": []}


MD_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
MD_HR_RE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
MD_LIST_RE = re.compile(r"^\s*([-*+]|\d+[.)])\s+")
MD_FENCE_RE = re.compile(r"^\s*(```|~~~)")
MD_REFDEF_RE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s+\S+")


def strip_md_inline(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"!\[[^\]]*\]\[[^\]]*\]", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\[[^\]]*\]", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"`+([^`]*)`+", r"\1", text)
    text = re.sub(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1", r"\2", text)
    text = re.sub(r"\*(?=\S)(.+?)(?<=\S)\*", r"\1", text)
    text = re.sub(r"(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)", r"\1", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    return text


def parse_markdown(text: str) -> tuple[list[str], list[tuple[str, int]]]:
    blocks, marks, para = [], [], []
    in_fence = False

    def flush():
        if para:
            block = re.sub(r"\s+", " ", " ".join(para)).strip()
            if block:
                blocks.append(block)
            para.clear()

    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if MD_FENCE_RE.match(raw):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            para.append(raw)
            continue
        line = re.sub(r"^(\s*>\s?)+", "", raw)
        if not line.strip() or MD_HR_RE.match(line) or MD_REFDEF_RE.match(line):
            flush()
            continue
        heading = MD_HEADING_RE.match(line)
        if heading:
            flush()
            title = strip_md_inline(heading.group(2)).strip()
            if title:
                if len(heading.group(1)) <= 2:
                    marks.append((title, len(blocks)))
                blocks.append(title)
            continue
        if MD_LIST_RE.match(line):
            flush()
            line = MD_LIST_RE.sub("", line)
        para.append(strip_md_inline(line))
    flush()
    return blocks, marks


def _extract_md(path: Path) -> dict:
    blocks, marks = parse_markdown(path.read_text(encoding="utf-8", errors="ignore"))
    return {"title": None, "author": None, "cover": None, "blocks": blocks, "marks": marks}


def extract_doc(path: Path) -> dict:
    ext = path.suffix.lower()
    if ext == ".epub":
        return _extract_epub(path)
    if ext == ".pdf":
        return _extract_pdf(path)
    if ext in MOBI_EXTS:
        return _extract_mobi(path)
    if ext == ".md":
        return _extract_md(path)
    return _extract_txt(path)


# ── tokenizer ─────────────────────────────────────────────────────────────────

JOINER_RE = re.compile(r"(?<=[\w,;:!?\"'”’)])(--+|[—–]+|\.{3}|…)(?=[\w\"'“‘])")


def tokenize_block(block: str) -> list[str]:
    """Split one paragraph into words; dashes/ellipses between words split, stray punctuation attaches."""
    block = JOINER_RE.sub(r"\1 ", block)
    tokens, pending = [], ""
    for word in block.split():
        if not any(c.isalnum() for c in word):
            if tokens:
                tokens[-1] += word
            else:
                pending += word
            continue
        tokens.append(pending + word)
        pending = ""
    if pending and not tokens:
        tokens.append(pending)
    return tokens


def _norm_tok(tok: str) -> str:
    return re.sub(r"[^\w]", "", tok).lower()


def snap_to_title(words: list[str], idx: int, title: str, limit: int, window: int = 80) -> int:
    """Anchors often sit on an illustration caption above the heading; move to the heading itself.

    Only a paragraph-initial match before `limit` (the next chapter) counts, and one- or
    two-letter titles ("I", "IV") never snap: they would match ordinary words.
    """
    want = [t for t in map(_norm_tok, (title or "").split()) if t]
    if not want or (len(want) == 1 and len(want[0]) < 3):
        return idx
    end = min(len(words), idx + window, limit)
    pos = [i for i in range(idx, end) if words[i] != "¶"]
    for k in range(len(pos) - len(want) + 1):
        i = pos[k]
        if i != idx and words[i - 1] != "¶":
            continue
        if all(_norm_tok(words[pos[k + j]]) == w for j, w in enumerate(want)):
            return i
    return idx


def build_words(blocks: list[str], marks=()) -> tuple[list[str], list[dict]]:
    """Join blocks with ¶ tokens; map (title, block_index) marks to word indices."""
    words, block_start = [], []
    for block in blocks:
        toks = tokenize_block(block)
        if toks and words:
            words.append("¶")
        block_start.append(len(words))
        words.extend(toks)
    block_start.append(len(words))

    last = max(len(words) - 1, 0)
    placed = sorted((min(block_start[min(max(b, 0), len(blocks))], last), title)
                    for title, b in marks)
    starts = sorted({i for i, _ in placed})
    chapters, seen = [], set()
    for idx, title in placed:
        nxt = next((s for s in starts if s > idx), len(words))
        idx = snap_to_title(words, idx, title, nxt)
        if (title, idx) not in seen:
            seen.add((title, idx))
            chapters.append({"title": title, "index": idx})
    chapters.sort(key=lambda c: c["index"])
    return words, chapters


def tokenize(text: str) -> list[str]:
    return build_words(split_blocks(text))[0]


# ── cache ─────────────────────────────────────────────────────────────────────

def cache_path(book_id: str) -> Path:
    return CACHE_DIR / f"{book_id}.json"


def load_book(path: Path, book_id: str) -> dict:
    """Return cached {words, chapters, title, author, has_cover}, extracting if needed."""
    cfile = cache_path(book_id)
    try:
        cached = json.loads(cfile.read_text())
        if cached.get("v") == CACHE_VERSION:
            if cached.get("has_cover") and not find_cover(book_id):
                raise ValueError("cover missing")  # re-extract to restore it
            return cached
    except Exception:
        pass

    doc = extract_doc(path)
    words, chapters = build_words(doc["blocks"], doc["marks"])
    has_cover = bool(doc.get("cover")) and save_cover(book_id, *doc["cover"])
    data = {
        "v": CACHE_VERSION,
        "words": words,
        "chapters": chapters,
        "title": doc.get("title") or path.stem,
        "author": doc.get("author"),
        "has_cover": has_cover,
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write(cfile, json.dumps(data))
    return data


def read_cached_book(book_id: str):
    try:
        cached = json.loads(cache_path(book_id).read_text())
        return cached if cached.get("v") == CACHE_VERSION else None
    except Exception:
        return None


# ── metadata ──────────────────────────────────────────────────────────────────

def book_meta(path: Path) -> dict:
    """Cheap metadata (no text extraction), cached in meta_cache by path+mtime+size."""
    st = path.stat()
    row = cached_meta_row(path, st)
    if row and (not row["has_cover"] or find_cover(row["book_id"])):
        return {"book_id": row["book_id"], "title": row["title"],
                "author": row["author"], "has_cover": bool(row["has_cover"])}

    book_id = compute_book_id(path)
    title, author, has_cover = None, None, bool(find_cover(book_id))
    cached = read_cached_book(book_id)
    ext = path.suffix.lower()
    if cached:
        title, author = cached.get("title"), cached.get("author")
        has_cover = has_cover or bool(cached.get("has_cover"))
    elif ext == ".epub":
        try:
            opf = read_epub_opf(path)
            title, author = opf["title"], opf["author"]
            if opf["cover"] and not has_cover:
                has_cover = save_cover(book_id, *opf["cover"])
        except Exception:
            pass
    elif ext == ".pdf":
        try:
            from pypdf import PdfReader
            meta = _pdf_meta(PdfReader(str(path)))
            title, author = meta["title"], meta["author"]
        except Exception:
            pass
    title = title or path.stem
    store_meta(path, book_id, title, author, has_cover)
    return {"book_id": book_id, "title": title, "author": author, "has_cover": has_cover}


# ── errors ────────────────────────────────────────────────────────────────────

@app.errorhandler(HTTPException)
def handle_http_error(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": e.description or e.name}), e.code
    return e


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    if isinstance(e, HTTPException):
        return handle_http_error(e)
    app.logger.exception("Unhandled error")
    if request.path.startswith("/api/"):
        return jsonify({"error": "Internal error"}), 500
    return "Internal Server Error", 500


@app.before_request
def reject_cross_site_writes():
    """Block CSRF: JSON is accepted as text/plain (sendBeacon), so check where writes come from."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    site = request.headers.get("Sec-Fetch-Site")
    if site is not None:
        ok = site in ("same-origin", "none")
    else:
        origin = request.headers.get("Origin")
        ok = origin is None or origin.split("://", 1)[-1] == request.host
    if not ok:
        abort(403, "Cross-site request refused")
    return None


def json_body() -> dict:
    """Parse a JSON body regardless of Content-Type (sendBeacon sends text/plain)."""
    try:
        data = json.loads(request.get_data(as_text=True) or "{}")
    except ValueError:
        abort(400, "Body must be JSON")
    if not isinstance(data, dict):
        abort(400, "Body must be a JSON object")
    return data


# ── routes: pages & config ────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# Served from the root so the service worker's scope covers the whole app.
@app.route("/sw.js")
def service_worker():
    resp = send_file(Path(app.static_folder) / "sw.js", mimetype="text/javascript", max_age=0)
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/manifest.webmanifest")
def manifest():
    return send_file(Path(app.static_folder) / "manifest.webmanifest",
                     mimetype="application/manifest+json", max_age=3600)


@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify({"books_dir": str(get_books_dir()), "fs_root": str(FS_ROOT)})


@app.route("/api/config", methods=["POST"])
def post_config():
    new_dir = str(json_body().get("books_dir", "")).strip()
    if not new_dir:
        abort(400, "books_dir is required")
    try:
        p = set_books_dir(new_dir)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"books_dir": str(p)})


@app.route("/api/settings", methods=["GET"])
def get_settings_route():
    return jsonify(get_settings())


@app.route("/api/settings", methods=["POST"])
def post_settings():
    try:
        return jsonify(update_settings(json_body()))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ── routes: browsing ──────────────────────────────────────────────────────────

def list_dir(target: Path) -> list[dict]:
    """Directory entries, dotfiles hidden, dirs first then files, case-insensitive."""
    children = [c for c in target.iterdir() if not c.name.startswith(".")]
    children.sort(key=lambda p: (not p.is_dir(), p.name.lower()))
    entries = []
    for child in children:
        is_dir = child.is_dir()
        ext = "" if is_dir else child.suffix.lower()
        entry = {
            "name": child.name,
            "path": str(child),
            "type": "dir" if is_dir else "file",
            "ext": ext,
            "supported": (not is_dir) and ext in SUPPORTED_EXTS,
        }
        if not is_dir:
            try:
                entry["size"] = child.stat().st_size
            except OSError:
                entry["size"] = 0
        entries.append(entry)
    return entries


@app.route("/api/browse")
def browse():
    books_dir = get_books_dir()
    raw = request.args.get("path", "").strip()
    target = confine(raw, root=books_dir) if raw else books_dir
    base = {"path": str(target), "root": str(books_dir),
            "parent": None if target == books_dir else str(target.parent), "entries": []}

    if not books_dir.is_dir():
        return jsonify({**base, "error": f"Books folder not found: {books_dir}"})
    if not target.exists():
        return jsonify({**base, "error": f"Folder not found: {target}"})
    if not target.is_dir():
        abort(400, f"Not a folder: {target}")
    try:
        return jsonify({**base, "entries": list_dir(target)})
    except PermissionError:
        return jsonify({**base, "error": "Permission denied reading this folder"})


@app.route("/api/fs")
def fs_browse():
    """Filesystem browser for the folder/file picker, confined to FS_ROOT."""
    raw = request.args.get("path", "").strip()
    target = confine(raw) if raw else FS_ROOT
    if not target.exists():
        abort(404, f"Not found: {target}")

    entries = []
    if target.is_dir():
        try:
            entries = list_dir(target)
        except PermissionError:
            entries = []
    parent = None if target == FS_ROOT or target == target.parent else str(target.parent)
    return jsonify({
        "path": str(target),
        "parent": parent,
        "is_dir": target.is_dir(),
        "entries": entries,
    })


# ── routes: books ─────────────────────────────────────────────────────────────

@app.route("/api/meta")
def meta():
    path = resolve_book(request.args.get("path", ""))
    try:
        info = book_meta(path)
    except OSError as e:
        abort(422, f"Could not read file: {e}")
    return jsonify({**info, "path": str(path), "format": book_format(path)})


@app.route("/api/cover")
def cover():
    p = find_cover(request.args.get("id", ""))
    if not p:
        abort(404, "No cover")
    resp = send_file(p, mimetype=mimetypes.guess_type(p.name)[0] or "application/octet-stream",
                     max_age=86400)
    resp.headers["Cache-Control"] = "max-age=86400"
    return resp


@app.route("/api/book")
def book():
    path = resolve_book(request.args.get("path", ""))
    try:
        book_id = get_book_id(path)
        data = load_book(path, book_id)
    except HTTPException:
        raise
    except Exception as e:
        app.logger.exception("Extraction failed for %s", path)
        abort(422, f"Could not read this {book_format(path).upper()} file: {e}")
    if not data["words"]:
        abort(422, "No readable text found in this file (it may be scanned images or DRM-protected).")

    store_meta(path, book_id, data["title"], data["author"], data["has_cover"],
               word_count=len(data["words"]))
    rows = db_query("SELECT word_index FROM books_progress WHERE book_id = ?", (book_id,))
    start = rows[0]["word_index"] if rows else 0
    start = max(0, min(start, len(data["words"]) - 1))

    return jsonify({
        "book_id": book_id,
        "path": str(path),
        "title": data["title"],
        "author": data["author"],
        "words": data["words"],
        "total": len(data["words"]),
        "chapters": data["chapters"],
        "start": start,
        "has_cover": bool(data["has_cover"]),
    })


# ── routes: progress & stats ──────────────────────────────────────────────────

@app.route("/api/progress", methods=["GET"])
def get_progress():
    rows = db_query("SELECT * FROM books_progress ORDER BY updated_at DESC")
    result = []
    for row in rows:
        if not row["path"] or not Path(row["path"]).is_file():
            continue
        total = row["total_words"]
        result.append({
            "book_id": row["book_id"],
            "path": row["path"],
            "title": row["title"],
            "author": row["author"],
            "word_index": row["word_index"],
            "total_words": total,
            "percent": round(row["word_index"] / total * 100, 1) if total else 0,
            "updated_at": row["updated_at"],
            "has_cover": find_cover(row["book_id"]) is not None,
        })
    return jsonify(result)


def _as_int(value, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        abort(400, f"{name} must be a number")


@app.route("/api/progress", methods=["POST"])
def post_progress():
    data = json_body()
    book_id = str(data.get("book_id", "")).strip()
    if not BOOK_ID_RE.match(book_id):
        abort(400, "book_id is required")
    path = str(data.get("path", "") or "")
    title = data.get("title")
    title = title if isinstance(title, str) and title.strip() else (Path(path).stem or "Untitled")
    author = data.get("author")
    author = author if isinstance(author, str) and author.strip() else None
    word_index = max(0, _as_int(data.get("word_index", 0), "word_index"))
    total_words = max(0, _as_int(data.get("total_words", 0), "total_words"))
    try:
        seconds = float(data.get("seconds_read") or 0)
    except (TypeError, ValueError):
        seconds = 0
    seconds = int(round(max(0, min(MAX_SECONDS_PER_SAVE, seconds))))
    # Words come from the client's playback count, not the position delta: seeks,
    # chapter jumps and undo-restores move the position without reading anything.
    try:
        words_read = int(data.get("words_read") or 0)
    except (TypeError, ValueError):
        words_read = 0
    words_read = max(0, min(words_read, -(-seconds * WPM_MAX // 60)))

    conn = get_db()
    with _db_lock:
        conn.execute(
            """INSERT INTO books_progress
               (book_id, path, title, author, word_index, total_words, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(book_id) DO UPDATE SET
                 path=CASE WHEN excluded.path != '' THEN excluded.path ELSE books_progress.path END,
                 title=excluded.title,
                 author=COALESCE(excluded.author, books_progress.author),
                 word_index=excluded.word_index,
                 total_words=excluded.total_words,
                 updated_at=excluded.updated_at""",
            (book_id, path, title, author, word_index, total_words, utc_now_iso()),
        )
        if words_read or seconds:
            conn.execute(
                """INSERT INTO daily_stats (day, words, seconds) VALUES (?, ?, ?)
                   ON CONFLICT(day) DO UPDATE SET
                     words = words + excluded.words,
                     seconds = seconds + excluded.seconds""",
                (local_today(), words_read, seconds),
            )
        conn.commit()
    return jsonify({"ok": True})


@app.route("/api/progress", methods=["DELETE"])
def delete_progress():
    book_id = request.args.get("id", "")
    if not book_id:
        abort(400, "id is required")
    db_execute("DELETE FROM books_progress WHERE book_id = ?", (book_id,))
    return jsonify({"ok": True})


@app.route("/api/stats")
def stats():
    today = local_now().date()
    rows = db_query("SELECT day, words, seconds FROM daily_stats WHERE day >= ?",
                    ((today - timedelta(days=400)).isoformat(),))
    by_day = {r["day"]: r for r in rows}

    def day_at(offset):
        return (today - timedelta(days=offset)).isoformat()

    def totals(days):
        return {"words": sum(by_day[d]["words"] for d in days if d in by_day),
                "seconds": sum(by_day[d]["seconds"] for d in days if d in by_day)}

    def active(day):
        return day in by_day and by_day[day]["words"] > 0

    # Streak counts back from today, or from yesterday if nothing read yet today
    offset = 0 if active(day_at(0)) else 1
    streak = 0
    while active(day_at(offset + streak)):
        streak += 1

    return jsonify({
        "today": totals([day_at(0)]),
        "week": totals([day_at(i) for i in range(7)]),
        "streak_days": streak,
        "days": [{"day": day_at(i), "words": by_day[day_at(i)]["words"] if day_at(i) in by_day else 0}
                 for i in range(13, -1, -1)],
    })


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    get_db()
    app.run(host="0.0.0.0", port=PORT)
