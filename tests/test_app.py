import importlib
import json
import sqlite3
import struct
import sys
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── fixtures ──────────────────────────────────────────────────────────────────

def tiny_png() -> bytes:
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def make_epub(path: Path):
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("test-book")
    book.set_title("Spine Test")
    book.add_author("Ada Author")
    book.set_language("en")
    book.set_cover("cover.png", tiny_png(), create_page=False)

    def chap(name, title, body):
        c = epub.EpubHtml(title=title, file_name=name, lang="en")
        c.content = f"<html><head><title>{title}</title></head><body>{body}</body></html>"
        return c

    c1 = chap("ch1.xhtml", "One", "<h1>Chapter One</h1><p>Alpha beta.</p><p>Gamma delta.</p>")
    c2 = chap("ch2.xhtml", "Two",
              "<h1>Chapter Two</h1><p>Epsilon zeta.</p><h2 id='sec2'>Part B</h2><p>Eta theta.</p>")
    c3 = chap("ch3.xhtml", "Three", "<h1>Chapter Three</h1><p>Iota kappa<br/>lambda.</p>")
    # Manifest deliberately out of reading order
    for c in (c3, c1, c2):
        book.add_item(c)
    book.toc = [
        epub.Link("ch1.xhtml", "Chapter One", "c1"),
        (epub.Section("Middle", href="ch2.xhtml"),
         [epub.Link("ch2.xhtml#sec2", "Part B", "c2b")]),
        epub.Link("ch3.xhtml", "Chapter Three", "c3"),
    ]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = [c1, c2, c3]
    epub.write_epub(str(path), book)


@pytest.fixture
def env(tmp_path, monkeypatch):
    fs_root = tmp_path / "root"
    books = fs_root / "books"
    data = tmp_path / "data"
    books.mkdir(parents=True)
    data.mkdir()
    monkeypatch.setenv("BOOKS_DIR", str(books))
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("FS_ROOT", str(fs_root))
    monkeypatch.setenv("TZ", "UTC")
    import app as app_module
    mod = importlib.reload(app_module)
    mod.app.config["TESTING"] = True
    return {"mod": mod, "client": mod.app.test_client(), "books": books,
            "data": data, "root": fs_root, "tmp": tmp_path}


@pytest.fixture
def epub_file(env):
    p = env["books"] / "spine.epub"
    make_epub(p)
    return p


# ── tokenizer & text processing ───────────────────────────────────────────────

def test_tokenizer_splits_dashes_and_ellipses(env):
    tok = env["mod"].tokenize
    assert tok("word—word") == ["word—", "word"]
    assert tok("one–two") == ["one–", "two"]
    assert tok("wait...what") == ["wait...", "what"]
    assert tok("so…then") == ["so…", "then"]
    assert tok("dash--here") == ["dash--", "here"]


def test_tokenizer_splits_dashes_after_punctuation(env):
    tok = env["mod"].tokenize
    assert tok("contemptuously,—“yes, said she") == ["contemptuously,—", "“yes,", "said", "she"]
    assert tok("PRESS:—CHARLES WHITTINGHAM") == ["PRESS:—", "CHARLES", "WHITTINGHAM"]
    assert tok("well?—no") == ["well?—", "no"]


def test_tokenizer_attaches_punctuation_and_paragraphs(env):
    tok = env["mod"].tokenize
    assert tok("Hello , world — again") == ["Hello,", "world—", "again"]
    assert tok('" Quoted start') == ['"Quoted', "start"]
    assert tok("First para.\n\nSecond para.") == ["First", "para.", "¶", "Second", "para."]


def test_markdown_stripping_and_chapters(env):
    mod = env["mod"]
    md = (
        "# Title One\n\nSome **bold** and *em* and `code` and [a link](http://x).\n\n"
        "![img](pic.png)\n\n> quoted line\n\n- item one\n- item two\n\n---\n\n"
        "## Second\n\n### Not a chapter\n\nsnake_case_name stays <b>tagged</b>.\n"
    )
    blocks, marks = mod.parse_markdown(md)
    text = " ".join(blocks)
    for junk in ("**", "`", "](", "![", "<b>", "> ", "---", "#"):
        assert junk not in text
    assert "a link" in text and "snake_case_name" in text and "tagged" in text
    assert "item one" in blocks and "item two" in blocks
    words, chapters = mod.build_words(blocks, marks)
    assert [c["title"] for c in chapters] == ["Title One", "Second"]
    assert words[chapters[1]["index"]] == "Second"


def test_pdf_cleanup_heuristics(env):
    mod = env["mod"]
    pages = []
    for n in range(1, 6):
        pages.append(
            f"The Great Book\n"
            f"This is a fairly long line of body text that wraps onto the next exam-\n"
            f"ple line and keeps going for a while longer than usual here.\n"
            f"End of para.\n"
            f"Next paragraph starts here with a long line of words in it too ok.\n"
            f"{n}"
        )
    out = mod.clean_pdf_pages(pages)
    assert len(out) == 5
    flat = " ".join(" ".join(p) for p in out)
    assert "The Great Book" not in flat           # repeated header removed
    assert "example" in flat and "exam-" not in flat  # de-hyphenated
    assert not any(b.strip().isdigit() for p in out for b in p)  # page numbers dropped
    assert out[0][0].endswith("End of para.")     # short line + uppercase next -> break
    assert out[0][1].startswith("Next paragraph")


def test_pdf_cleanup_keeps_single_line_pages(env):
    pages = ["Same long single line of page text that repeats on every page of the book."] * 5
    out = env["mod"].clean_pdf_pages(pages)
    assert all(p == [pages[0]] for p in out)


def test_drop_cap_image_alt(env):
    blocks, _ = env["mod"].html_to_blocks(
        '<p><span><img alt="W" src="w.png"/></span>HEN Jane <img alt="" src="x.png"/>left.</p>')
    assert blocks == ["WHEN Jane left."]


def test_pdf_meta_junk_filter(env):
    clean = env["mod"].clean_pdf_meta
    assert clean("Microsoft Word - thesis.doc") is None
    assert clean("  ") is None
    assert clean("report.pdf") is None
    assert clean("Real Title") == "Real Title"


# ── epub ──────────────────────────────────────────────────────────────────────

def test_epub_spine_order_chapters_and_cover(env, epub_file):
    c = env["client"]
    r = c.get("/api/book", query_string={"path": str(epub_file)})
    assert r.status_code == 200, r.get_json()
    d = r.get_json()
    words = d["words"]
    assert d["title"] == "Spine Test" and d["author"] == "Ada Author"
    assert words.index("Alpha") < words.index("Epsilon") < words.index("Iota")
    assert "¶" in words
    # <br/> becomes a paragraph break
    assert words[words.index("kappa") + 1] == "¶"
    titles = [ch["title"] for ch in d["chapters"]]
    assert titles == ["Chapter One", "Middle", "Part B", "Chapter Three"]
    idx = {ch["title"]: ch["index"] for ch in d["chapters"]}
    assert words[idx["Chapter One"]] == "Chapter"
    assert words[idx["Middle"]:idx["Middle"] + 2] == ["Chapter", "Two"]
    assert words[idx["Part B"]:idx["Part B"] + 2] == ["Part", "B"]  # fragment-level
    assert words[idx["Chapter Three"] + 1] == "Three"
    assert "One" not in words[:1]  # <title> in <head> is not read
    assert d["has_cover"] is True
    assert d["start"] == 0 and d["total"] == len(words)
    assert len(d["book_id"]) == 32

    cov = c.get("/api/cover", query_string={"id": d["book_id"]})
    assert cov.status_code == 200
    assert cov.mimetype == "image/png"
    assert "max-age=86400" in cov.headers["Cache-Control"]

    cache = json.loads((env["data"] / "text_cache" / f"{d['book_id']}.json").read_text())
    assert cache["v"] == env["mod"].CACHE_VERSION and cache["chapters"] == d["chapters"]


def test_epub_meta_fast_path_and_cover(env, epub_file):
    c = env["client"]
    r = c.get("/api/meta", query_string={"path": str(epub_file)})
    d = r.get_json()
    assert r.status_code == 200
    assert d["title"] == "Spine Test" and d["author"] == "Ada Author"
    assert d["format"] == "epub" and d["has_cover"] is True
    assert d["path"] == str(epub_file)
    assert not (env["data"] / "text_cache" / f"{d['book_id']}.json").exists()
    assert c.get("/api/cover", query_string={"id": d["book_id"]}).status_code == 200
    # Second call is served from meta_cache
    assert c.get("/api/meta", query_string={"path": str(epub_file)}).get_json() == d


def test_epub_toc_fallback_to_headings(env, tmp_path):
    from ebooklib import epub
    mod = env["mod"]
    book = epub.EpubBook()
    book.set_identifier("x")
    book.set_title("No TOC")
    items = []
    for i in range(2):
        it = epub.EpubHtml(title=f"c{i}", file_name=f"c{i}.xhtml")
        it.content = f"<html><body><h2>Head {i}</h2><p>Text {i}.</p></body></html>"
        book.add_item(it)
        items.append(it)
    book.add_item(epub.EpubNcx())
    book.spine = items
    p = env["books"] / "notoc.epub"
    epub.write_epub(str(p), book)
    doc = mod.extract_doc(p)
    words, chapters = mod.build_words(doc["blocks"], doc["marks"])
    assert [ch["title"] for ch in chapters] == ["Head 0", "Head 1"]


# ── txt / md via API ──────────────────────────────────────────────────────────

def test_txt_and_md_books(env):
    c = env["client"]
    txt = env["books"] / "plain.txt"
    txt.write_text("Hello there.\n\nGeneral Kenobi—you are bold.")
    d = c.get("/api/book", query_string={"path": str(txt)}).get_json()
    assert d["words"] == ["Hello", "there.", "¶", "General", "Kenobi—", "you", "are", "bold."]
    assert d["title"] == "plain" and d["author"] is None and d["chapters"] == []

    md = env["books"] / "notes.md"
    md.write_text("# Intro\n\nSome *text*.\n\n## Next\n\nMore.")
    d = c.get("/api/book", query_string={"path": str(md)}).get_json()
    assert d["chapters"] == [{"title": "Intro", "index": 0}, {"title": "Next", "index": 5}]
    assert "*text*." not in d["words"] and "text." in d["words"]


# ── path safety ───────────────────────────────────────────────────────────────

def test_path_confinement(env, epub_file):
    c = env["client"]
    outside = env["tmp"] / "outside.txt"
    outside.write_text("secret words")
    assert c.get("/api/book", query_string={"path": str(outside)}).status_code == 403
    assert c.get("/api/meta", query_string={"path": str(outside)}).status_code == 403
    assert c.get("/api/fs", query_string={"path": str(env["tmp"])}).status_code == 403
    r = c.get("/api/book", query_string={"path": str(env["books"] / ".." / ".." / "outside.txt")})
    assert r.status_code == 403 and "error" in r.get_json()
    # Symlink escaping the root is resolved and rejected
    link = env["books"] / "link.txt"
    link.symlink_to(outside)
    assert c.get("/api/book", query_string={"path": str(link)}).status_code == 403
    # Browse is confined to the library root (even inside FS_ROOT)
    other = env["root"] / "other"
    other.mkdir()
    assert c.get("/api/browse", query_string={"path": str(other)}).status_code == 403
    # ...but opening a book outside the library (inside FS_ROOT) is fine and doesn't move the library
    (other / "x.txt").write_text("hi there")
    assert c.get("/api/book", query_string={"path": str(other / "x.txt")}).status_code == 200
    assert c.get("/api/config").get_json()["books_dir"] == str(env["books"])


def test_unsupported_extension_and_missing(env):
    c = env["client"]
    bad = env["books"] / "config.json"
    bad.write_text("{}")
    r = c.get("/api/book", query_string={"path": str(bad)})
    assert r.status_code == 400 and "error" in r.get_json()
    assert c.get("/api/meta", query_string={"path": str(bad)}).status_code == 400
    r = c.get("/api/book", query_string={"path": str(env["books"] / "nope.epub")})
    assert r.status_code == 404 and "error" in r.get_json()
    assert c.get("/api/cover", query_string={"id": "0" * 32}).status_code == 404
    assert c.get("/api/cover", query_string={"id": "../etc"}).status_code == 404


def test_browse_and_fs(env, epub_file):
    c = env["client"]
    (env["books"] / ".hidden").write_text("x")
    (env["books"] / "Zdir").mkdir()
    (env["books"] / "adir").mkdir()
    (env["books"] / "B.txt").write_text("b")
    d = c.get("/api/browse").get_json()
    assert d["path"] == str(env["books"]) and d["root"] == str(env["books"]) and d["parent"] is None
    names = [e["name"] for e in d["entries"]]
    assert names == ["adir", "Zdir", "B.txt", "spine.epub"]
    e = d["entries"][3]
    assert e["path"] == str(epub_file) and e["supported"] and e["ext"] == ".epub" and e["size"] > 0
    sub = c.get("/api/browse", query_string={"path": str(env["books"] / "adir")}).get_json()
    assert sub["parent"] == str(env["books"])

    fs = c.get("/api/fs").get_json()
    assert fs["path"] == str(env["root"]) and fs["parent"] is None and fs["is_dir"]
    fs2 = c.get("/api/fs", query_string={"path": str(env["books"])}).get_json()
    assert fs2["parent"] == str(env["root"])
    assert ".hidden" not in [e["name"] for e in fs2["entries"]]


def test_config_and_settings(env):
    c = env["client"]
    assert c.get("/api/config").get_json() == {"books_dir": str(env["books"]),
                                               "fs_root": str(env["root"])}
    assert c.post("/api/config", json={"books_dir": str(env["tmp"])}).status_code == 400
    new = env["root"] / "lib2"
    new.mkdir()
    assert c.post("/api/config", json={"books_dir": str(new)}).get_json() == {"books_dir": str(new)}

    assert c.get("/api/settings").get_json() == {"wpm": 350, "pivot_guides": True, "ramp": True}
    assert c.post("/api/settings", json={"wpm": 5000}).get_json()["wpm"] == 800
    s = c.post("/api/settings", json={"ramp": False}).get_json()
    assert s == {"wpm": 800, "pivot_guides": True, "ramp": False}
    assert c.post("/api/settings", json={"ramp": "no"}).status_code == 400
    # Settings and books_dir coexist in config.json
    cfg = json.loads((env["data"] / "config.json").read_text())
    assert cfg["books_dir"] == str(new) and cfg["settings"]["ramp"] is False


# ── progress / stats / migration ──────────────────────────────────────────────

def test_progress_keyed_by_id_survives_rename(env):
    c = env["client"]
    p = env["books"] / "a.txt"
    p.write_text(" ".join(f"w{i}" for i in range(100)))
    d = c.get("/api/book", query_string={"path": str(p)}).get_json()
    bid = d["book_id"]
    r = c.post("/api/progress", json={"book_id": bid, "path": str(p), "title": "A",
                                      "word_index": 40, "total_words": 100})
    assert r.get_json() == {"ok": True}

    moved = env["books"] / "renamed.txt"
    p.rename(moved)
    assert c.get("/api/progress").get_json() == []  # stored path gone -> skipped
    d2 = c.get("/api/book", query_string={"path": str(moved)}).get_json()
    assert d2["book_id"] == bid and d2["start"] == 40

    c.post("/api/progress", data=json.dumps({"book_id": bid, "path": str(moved), "title": "A",
                                             "word_index": 50, "total_words": 100}),
           content_type="text/plain")  # sendBeacon style
    lst = c.get("/api/progress").get_json()
    assert len(lst) == 1
    row = lst[0]
    assert row["path"] == str(moved) and row["word_index"] == 50 and row["percent"] == 50.0
    assert set(row) == {"book_id", "path", "title", "author", "word_index", "total_words",
                        "percent", "updated_at", "has_cover"}
    assert row["updated_at"].endswith("Z")

    assert c.delete("/api/progress", query_string={"id": bid}).get_json() == {"ok": True}
    assert c.get("/api/progress").get_json() == []


def test_stats_count_played_words_not_position_jumps(env):
    c = env["client"]
    bid = "a" * 32
    def post(idx, secs=None, words=None):
        body = {"book_id": bid, "path": "/x", "title": "T", "word_index": idx, "total_words": 10000}
        if secs is not None:
            body["seconds_read"] = secs
        if words is not None:
            body["words_read"] = words
        assert c.post("/api/progress", json=body).status_code == 200

    post(2900)                     # first save mid-book: no words
    post(3000, 30, 100)            # +100 played words, +30s
    post(3200, 9999, 200)          # seconds clamped to 600
    post(6000)                     # chapter jump / scrub: position only
    post(6100, 1, 5000)            # words capped by seconds at WPM_MAX (1s -> 14)
    post(6100, -5, 50)             # negative seconds -> 0 -> no words either
    s = c.get("/api/stats").get_json()
    assert s["today"] == {"words": 314, "seconds": 631}
    assert s["week"] == {"words": 314, "seconds": 631}
    assert s["streak_days"] == 1
    assert len(s["days"]) == 14 and s["days"][-1]["words"] == 314
    assert s["days"][0]["words"] == 0

    # Remove then undo (re-post of the old position) adds nothing
    c.delete("/api/progress", query_string={"id": bid})
    post(6100)
    assert c.get("/api/stats").get_json()["today"]["words"] == 314


def test_streak_counts_from_yesterday(env):
    mod, c = env["mod"], env["client"]
    from datetime import timedelta
    today = mod.local_now().date()
    conn = mod.get_db()
    for off in (1, 2, 3, 5):
        conn.execute("INSERT INTO daily_stats VALUES (?, 100, 60)",
                     ((today - timedelta(days=off)).isoformat(),))
    conn.commit()
    s = c.get("/api/stats").get_json()
    assert s["streak_days"] == 3
    assert s["today"] == {"words": 0, "seconds": 0}
    assert s["week"] == {"words": 400, "seconds": 240}


def test_legacy_progress_migration(env, epub_file):
    mod = env["mod"]
    db_path = env["data"] / "progress.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE progress (relpath TEXT PRIMARY KEY, title TEXT NOT NULL,
                    word_index INTEGER NOT NULL DEFAULT 0, total_words INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("INSERT INTO progress VALUES ('spine.epub', 'Spine', 7, 30, '2025-05-01 10:00:00')")
    conn.execute("INSERT INTO progress VALUES ('gone.epub', 'Gone', 1, 2, '2025-05-01T10:00:00Z')")
    conn.commit()
    conn.close()

    c = env["client"]
    lst = c.get("/api/progress").get_json()
    assert len(lst) == 1
    row = lst[0]
    assert row["book_id"] == mod.compute_book_id(epub_file)
    assert row["path"] == str(epub_file) and row["word_index"] == 7 and row["total_words"] == 30
    assert row["updated_at"] == "2025-05-01T10:00:00Z"

    # Idempotent: a fresh process re-running migration changes nothing
    mod2 = importlib.reload(mod)
    assert len(mod2.app.test_client().get("/api/progress").get_json()) == 1
    tables = {r[0] for r in sqlite3.connect(db_path).execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "progress" not in tables and "progress_legacy" in tables
    # And the book opens at the migrated position
    d = mod2.app.test_client().get("/api/book", query_string={"path": str(epub_file)}).get_json()
    assert d["start"] == 7


def test_api_errors_are_json(env):
    c = env["client"]
    r = c.get("/api/nope")
    assert r.status_code == 404 and r.is_json and "error" in r.get_json()
    r = c.post("/api/progress", data="not json", content_type="text/plain")
    assert r.status_code == 400 and "error" in r.get_json()
    assert c.get("/api/file/words").status_code == 404


def test_extraction_error_is_422(env):
    c = env["client"]
    bad = env["books"] / "broken.epub"
    bad.write_bytes(b"this is not a zip")
    r = c.get("/api/book", query_string={"path": str(bad)})
    assert r.status_code == 422 and "error" in r.get_json()
    # meta degrades gracefully
    m = c.get("/api/meta", query_string={"path": str(bad)}).get_json()
    assert m["title"] == "broken" and m["has_cover"] is False


def test_clean_toc_title_strips_snippet_prefix():
    from app import clean_toc_title
    assert clean_toc_title("delighted to see their dear friend again. CHAPTER XVII.") == "CHAPTER XVII"
    assert clean_toc_title("Chapter 3: The Storm") == "Chapter 3: The Storm"
    assert clean_toc_title("Preface") == "Preface"
    assert clean_toc_title("The Book Mill") == "The Book Mill"
    assert clean_toc_title("Notes on a Letter I Never Sent") == "Notes on a Letter I Never Sent"


def test_chapter_start_snaps_past_caption_to_heading(env):
    build = env["mod"].build_words
    blocks = ["end of chapter one.", "I hope Mr. Bingley will like it.", "CHAPTER II.", "Mr. Bennet was"]
    words, chapters = build(blocks, [("CHAPTER II", 1), ("Missing Title", 3)])
    assert words[chapters[0]["index"]:chapters[0]["index"] + 2] == ["CHAPTER", "II."]
    assert words[chapters[1]["index"]] == "Mr."


def test_chapter_snap_stays_inside_its_chapter(env):
    build = env["mod"].build_words
    # One-letter titles never snap (would hit the pronoun); no snapping past the next mark.
    blocks = ["CHAPTER THE FIRST", "Text.", "CHAPTER THE SECOND", "I said so.", "More."]
    words, chapters = build(blocks, [("I", 0), ("II", 2)])
    assert [c["index"] for c in chapters] == sorted(c["index"] for c in chapters)
    assert chapters[0] == {"title": "I", "index": 0}
    assert words[chapters[1]["index"]] == "CHAPTER"
    blocks = ["Caption.", "Body of one.", "Epilogue here", "Epilogue"]
    words, chapters = build(blocks, [("Epilogue", 0), ("Next", 2)])
    assert chapters[0]["index"] == 0  # the "Epilogue" paragraph lies past the next mark


def test_cross_site_writes_refused(env):
    c = env["client"]
    body = json.dumps({"wpm": 500})
    r = c.post("/api/settings", data=body, content_type="text/plain",
               headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    r = c.post("/api/settings", data=body, content_type="text/plain",
               headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = c.post("/api/settings", data=body, content_type="text/plain",
               headers={"Sec-Fetch-Site": "same-origin", "Origin": "http://localhost"})
    assert r.status_code == 200 and r.get_json()["wpm"] == 500
    assert c.get("/api/settings", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200


def test_bad_input_is_400_not_500(env):
    c = env["client"]
    r = c.get("/api/meta", query_string={"path": str(env["books"]) + "/a\x00.epub"})
    assert r.status_code == 400
    r = c.post("/api/progress", json={"book_id": "b" * 32, "path": "/x", "author": {"x": 1},
                                      "title": ["t"], "word_index": 1, "total_words": 2})
    assert r.status_code == 200
    row = env["mod"].db_query("SELECT title, author FROM books_progress")[0]
    assert row["title"] == "x" and row["author"] is None


def test_saved_books_dir_outside_fs_root_is_ignored(env):
    mod = env["mod"]
    mod.write_config({"books_dir": str(env["tmp"])})  # parent of FS_ROOT
    assert mod.get_books_dir() == env["books"]


def test_cover_type_change_keeps_one_file(env):
    mod = env["mod"]
    bid = "c" * 32
    assert mod.save_cover(bid, b"jpgdata", "image/jpeg")
    assert mod.save_cover(bid, tiny_png(), "cover.png")
    files = sorted(p.name for p in mod.COVERS_DIR.iterdir())
    assert files == [f"{bid}.png"]
    assert mod.find_cover(bid).suffix == ".png"


def test_legacy_rows_retry_when_file_appears(env, epub_file):
    mod = env["mod"]
    db_path = env["data"] / "progress.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE progress (relpath TEXT PRIMARY KEY, title TEXT NOT NULL,
                    word_index INTEGER NOT NULL DEFAULT 0, total_words INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("INSERT INTO progress VALUES ('later.epub', 'Later', 9, 30, '2025-05-01 10:00:00')")
    conn.commit()
    conn.close()
    assert env["client"].get("/api/progress").get_json() == []  # file not there yet

    epub_file.rename(env["books"] / "later.epub")
    mod2 = importlib.reload(mod)
    lst = mod2.app.test_client().get("/api/progress").get_json()
    assert len(lst) == 1 and lst[0]["word_index"] == 9

    # Once migrated, removing the book is not undone by the next start
    mod2.app.test_client().delete("/api/progress", query_string={"id": lst[0]["book_id"]})
    mod3 = importlib.reload(mod2)
    assert mod3.app.test_client().get("/api/progress").get_json() == []


def test_wpm_saved_under_old_range_is_clamped(env):
    mod = env["mod"]
    mod.write_config({"settings": {"wpm": 1100}})
    assert env["client"].get("/api/settings").get_json()["wpm"] == 800
    mod.write_config({"settings": {"wpm": "fast"}})
    assert env["client"].get("/api/settings").get_json()["wpm"] == 350
