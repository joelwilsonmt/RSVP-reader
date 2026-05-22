import os
import re
import json
import hashlib
import sqlite3
import threading
from pathlib import Path
from datetime import datetime, timezone

from flask import Flask, render_template, request, jsonify, abort

app = Flask(__name__)

_ENV_BOOKS_DIR = Path(os.environ.get("BOOKS_DIR", "/books")).resolve()
DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data")).resolve()
PORT = int(os.environ.get("PORT", 5002))
CACHE_DIR = DATA_DIR / "text_cache"

_db_lock = threading.Lock()
_db_conn = None
_config_lock = threading.Lock()


def _config_path() -> Path:
    return DATA_DIR / "config.json"


def get_books_dir() -> Path:
    try:
        cfg = json.loads(_config_path().read_text())
        return Path(cfg["books_dir"]).expanduser().resolve()
    except Exception:
        return _ENV_BOOKS_DIR


def set_books_dir(new_path: str) -> Path:
    p = Path(new_path).expanduser().resolve()
    if not p.exists() or not p.is_dir():
        raise ValueError(f"Not a directory: {p}")
    with _config_lock:
        _config_path().write_text(json.dumps({"books_dir": str(p)}))
    return p

SUPPORTED_EXTS = {".epub", ".pdf", ".txt", ".md", ".mobi", ".azw", ".azw3"}


# ── database ──────────────────────────────────────────────────────────────────

def get_db():
    global _db_conn
    if _db_conn is None:
        _db_conn = sqlite3.connect(
            str(DATA_DIR / "progress.db"),
            check_same_thread=False,
        )
        _db_conn.row_factory = sqlite3.Row
        _db_conn.execute("""
            CREATE TABLE IF NOT EXISTS progress (
                relpath      TEXT PRIMARY KEY,
                title        TEXT NOT NULL,
                word_index   INTEGER NOT NULL DEFAULT 0,
                total_words  INTEGER NOT NULL DEFAULT 0,
                updated_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        _db_conn.commit()
    return _db_conn


# ── path safety ───────────────────────────────────────────────────────────────

def safe_resolve(relpath: str) -> Path:
    """Resolve relpath inside the current books dir; abort(403) if it escapes."""
    books_dir = get_books_dir()
    clean = relpath.lstrip("/") if relpath else ""
    candidate = (books_dir / clean).resolve()
    try:
        candidate.relative_to(books_dir)
    except ValueError:
        abort(403)
    return candidate


# ── text extraction ───────────────────────────────────────────────────────────

def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".epub":
        return _extract_epub(path)
    elif ext == ".pdf":
        return _extract_pdf(path)
    elif ext in (".mobi", ".azw", ".azw3"):
        return _extract_mobi(path)
    else:
        return path.read_text(encoding="utf-8", errors="ignore")


def _extract_epub(path: Path) -> str:
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup

    book = epub.read_epub(str(path), options={"ignore_ncx": True})
    parts = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        parts.append(soup.get_text(separator=" "))
    return "\n\n".join(parts)


def _extract_mobi(path: Path) -> str:
    import mobi
    import shutil
    from bs4 import BeautifulSoup

    tempdir, filepath = mobi.extract(str(path))
    try:
        html = Path(filepath).read_bytes()
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        return soup.get_text(separator=" ")
    finally:
        shutil.rmtree(tempdir, ignore_errors=True)


def _extract_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages)


# ── tokenizer ─────────────────────────────────────────────────────────────────

def tokenize(text: str) -> list[str]:
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    tokens = []
    # Split into paragraph-blocks (2+ newlines) and single-line chunks
    blocks = re.split(r"\n{2,}", text)
    for i, block in enumerate(blocks):
        if i > 0:
            tokens.append("¶")
        # Within a block collapse whitespace and split on spaces
        block = re.sub(r"[ \t]+", " ", block).replace("\n", " ").strip()
        if not block:
            continue
        for word in block.split(" "):
            word = word.strip()
            if word:
                tokens.append(word)

    return tokens


# ── cache ─────────────────────────────────────────────────────────────────────

def cache_key(relpath: str) -> Path:
    h = hashlib.sha256(relpath.encode()).hexdigest()
    return CACHE_DIR / f"{h}.json"


def load_words(relpath: str) -> list[str]:
    abs_path = safe_resolve(relpath)
    if not abs_path.exists() or not abs_path.is_file():
        abort(404)

    cfile = cache_key(relpath)
    file_mtime = abs_path.stat().st_mtime

    if cfile.exists():
        meta = json.loads(cfile.read_text())
        if meta.get("mtime") == file_mtime:
            return meta["words"]

    text = extract_text(abs_path)
    words = tokenize(text)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cfile.write_text(json.dumps({"mtime": file_mtime, "words": words}))
    return words


# ── routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/browse")
def browse():
    relpath = request.args.get("path", "")
    target = safe_resolve(relpath)

    books_dir = get_books_dir()
    if not books_dir.exists() or not books_dir.is_dir():
        return jsonify({
            "path": "", "parent": None, "entries": [],
            "error": f"Books folder not found: {books_dir}",
        })

    if not target.exists():
        return jsonify({"path": relpath.strip("/"), "parent": None, "entries": [],
                        "error": f"Folder not found: {target}"})
    if not target.is_dir():
        abort(400)

    entries = []
    try:
        children = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return jsonify({"path": relpath.strip("/"), "parent": None, "entries": [],
                        "error": "Permission denied reading this folder"})
    for child in children:
        ext = child.suffix.lower()
        child_rel = str(child.relative_to(books_dir))
        if child_rel == ".":
            child_rel = ""
        entry = {
            "name": child.name,
            "type": "dir" if child.is_dir() else "file",
            "relpath": child_rel,
            "ext": ext if child.is_file() else "",
            "supported": ext in SUPPORTED_EXTS if child.is_file() else False,
        }
        if child.is_file():
            try:
                entry["size"] = child.stat().st_size
            except OSError:
                entry["size"] = 0
        entries.append(entry)

    # Compute parent
    if relpath.strip("/") == "":
        parent = None
    else:
        p = Path(relpath.strip("/")).parent
        parent = str(p) if str(p) != "." else ""

    return jsonify({
        "path": relpath.strip("/"),
        "parent": parent,
        "entries": entries,
    })


@app.route("/api/file/words")
def file_words():
    relpath = request.args.get("relpath", "")
    if not relpath:
        abort(400)

    words = load_words(relpath)
    title = Path(relpath).stem

    db = get_db()
    with _db_lock:
        row = db.execute(
            "SELECT word_index FROM progress WHERE relpath = ?", (relpath,)
        ).fetchone()
    start = row["word_index"] if row else 0
    # Clamp in case total changed after re-parse
    start = max(0, min(start, len(words) - 1))

    return jsonify({
        "relpath": relpath,
        "title": title,
        "words": words,
        "total": len(words),
        "start": start,
    })


@app.route("/api/progress", methods=["GET"])
def get_progress():
    db = get_db()
    with _db_lock:
        rows = db.execute(
            "SELECT * FROM progress ORDER BY updated_at DESC"
        ).fetchall()

    books_dir = get_books_dir()
    result = []
    for row in rows:
        abs_path = books_dir / row["relpath"].lstrip("/")
        if not abs_path.exists():
            continue
        total = row["total_words"]
        pct = round(row["word_index"] / total * 100, 1) if total else 0
        result.append({
            "relpath": row["relpath"],
            "title": row["title"],
            "word_index": row["word_index"],
            "total_words": total,
            "percent": pct,
            "updated_at": row["updated_at"],
        })
    return jsonify(result)


@app.route("/api/progress", methods=["POST"])
def post_progress():
    data = request.get_json(force=True)
    relpath = data.get("relpath", "")
    title = data.get("title", Path(relpath).stem)
    word_index = int(data.get("word_index", 0))
    total_words = int(data.get("total_words", 0))

    if not relpath:
        abort(400)

    db = get_db()
    with _db_lock:
        db.execute(
            """INSERT INTO progress (relpath, title, word_index, total_words, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(relpath) DO UPDATE SET
                 title=excluded.title,
                 word_index=excluded.word_index,
                 total_words=excluded.total_words,
                 updated_at=excluded.updated_at""",
            (relpath, title, word_index, total_words,
             datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
        )
        db.commit()
    return jsonify({"ok": True})


@app.route("/api/progress", methods=["DELETE"])
def delete_progress():
    relpath = request.args.get("relpath", "")
    if not relpath:
        abort(400)
    db = get_db()
    with _db_lock:
        db.execute("DELETE FROM progress WHERE relpath = ?", (relpath,))
        db.commit()
    return jsonify({"ok": True})


@app.route("/api/fs")
def fs_browse():
    """Unrestricted filesystem browser used by the folder/file picker UI."""
    req_path = request.args.get("path", "/").strip() or "/"
    target = Path(req_path).expanduser().resolve()
    if not target.exists():
        abort(404)

    entries = []
    if target.is_dir():
        try:
            children = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            children = []
        for child in children:
            ext = child.suffix.lower()
            entry = {
                "name": child.name,
                "path": str(child),
                "type": "dir" if child.is_dir() else "file",
                "ext": ext,
                "supported": ext in SUPPORTED_EXTS if child.is_file() else False,
            }
            if child.is_file():
                try:
                    entry["size"] = child.stat().st_size
                except OSError:
                    entry["size"] = 0
            entries.append(entry)

    parent = str(target.parent) if target != target.parent else None
    return jsonify({
        "path": str(target),
        "parent": parent,
        "is_dir": target.is_dir(),
        "entries": entries,
    })


@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify({"books_dir": str(get_books_dir())})


@app.route("/api/config", methods=["POST"])
def post_config():
    data = request.get_json(force=True)
    new_dir = data.get("books_dir", "").strip()
    if not new_dir:
        abort(400)
    try:
        p = set_books_dir(new_dir)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"books_dir": str(p)})


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    get_db()
    app.run(host="0.0.0.0", port=PORT)
