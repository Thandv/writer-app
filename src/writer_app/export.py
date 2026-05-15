"""
Export — produce a KDP-ready .docx (and .epub) of a finished book.

Source preference, per chapter:
  1. book-NN/revisions/chapter-NN.md   (user-revised version)
  2. book-NN/chapter-NN/final.md       (AI final)

Strategy:
  - If `pandoc` is on PATH, use it.
  - Else, write DOCX/EPUB from scratch using only stdlib (zipfile + XML).
"""

import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape
from .shared.memory import BookProject


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s or "untitled"


def _resolve_chapter_text(project: BookProject, book_n: int, chapter: dict) -> str:
    n = chapter["number"]
    user_rev = project.book_dir(book_n) / "revisions" / f"chapter-{n:02d}.md"
    if user_rev.exists():
        return user_rev.read_text(encoding="utf-8", errors="ignore")
    final = project.chapter_dir(book_n, n) / "final.md"
    if final.exists():
        return final.read_text(encoding="utf-8", errors="ignore")
    return ""


def _build_intermediate_markdown(project: BookProject, book_n: int) -> str:
    book = project.book(book_n)
    year = datetime.now().year
    author = project.author_pen_name or project.author_name or "(Author Name)"
    real_name = project.author_name or author
    title = book.title or f"Book {book_n}"
    series = project.title

    parts = [
        f"# {title}",
        "",
        f"_{series} — Book {book_n}_",
        "",
        f"by **{author}**",
        "",
        "---",
        "",
        f"## Copyright",
        "",
        f"Copyright © {year} {real_name}. All rights reserved.",
        "",
        "This is a work of fiction. Names, characters, places, and incidents "
        "are products of the author's imagination or are used fictitiously. "
        "Any resemblance to actual persons, living or dead, or actual events "
        "is coincidental.",
        "",
        "No part of this book may be reproduced, scanned, or distributed in any "
        "printed or electronic form without permission of the author.",
        "",
        "## AI Disclosure",
        "",
        "Portions of the prose in this book were drafted with the assistance of "
        "artificial-intelligence text-generation tools and subsequently reviewed "
        "by the author. The plot, characters, world, magic system, and editorial "
        "selection and arrangement of the text are the author's original work.",
        "",
        "---",
        "",
    ]
    for ch in sorted(book.chapters, key=lambda c: c["number"]):
        n = ch["number"]
        body = _resolve_chapter_text(project, book_n, ch).strip()
        if not body:
            continue
        chap_title = ch.get("title", f"Chapter {n}")
        parts.append(f"## Chapter {n} — {chap_title}")
        parts.append("")
        parts.append(body)
        parts.append("")
    return "\n".join(parts)


def _have_pandoc() -> bool:
    return shutil.which("pandoc") is not None


def _pandoc_convert(md_text: str, out_path: Path, fmt: str):
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(md_text)
        src = Path(f.name)
    try:
        subprocess.run(
            ["pandoc", str(src), "-o", str(out_path),
             "--from=markdown", f"--to={fmt}", "--standalone"],
            check=True, capture_output=True, text=True, timeout=120,
        )
    finally:
        src.unlink(missing_ok=True)


_DOCX_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml"  ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml"   ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>
"""
_DOCX_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""
_DOCX_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""
_DOCX_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:styleId="Normal" w:default="1">
    <w:name w:val="Normal"/>
    <w:rPr><w:rFonts w:ascii="Garamond" w:hAnsi="Garamond"/><w:sz w:val="24"/></w:rPr>
    <w:pPr><w:spacing w:line="360" w:lineRule="auto"/><w:ind w:firstLine="360"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:basedOn w:val="Normal"/>
    <w:next w:val="Normal"/>
    <w:pPr><w:jc w:val="center"/><w:spacing w:before="2400" w:after="600"/><w:ind w:firstLine="0"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Garamond" w:hAnsi="Garamond"/><w:sz w:val="56"/><w:b/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="Heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:next w:val="Normal"/>
    <w:pPr><w:pageBreakBefore/><w:spacing w:before="600" w:after="400"/><w:jc w:val="center"/><w:ind w:firstLine="0"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Garamond" w:hAnsi="Garamond"/><w:sz w:val="36"/><w:b/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="Heading 2"/>
    <w:basedOn w:val="Normal"/>
    <w:next w:val="Normal"/>
    <w:pPr><w:spacing w:before="400" w:after="200"/><w:jc w:val="center"/><w:ind w:firstLine="0"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Garamond" w:hAnsi="Garamond"/><w:sz w:val="32"/><w:b/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="SceneBreak">
    <w:name w:val="Scene Break"/>
    <w:basedOn w:val="Normal"/>
    <w:next w:val="Normal"/>
    <w:pPr><w:spacing w:before="240" w:after="240"/><w:jc w:val="center"/><w:ind w:firstLine="0"/></w:pPr>
  </w:style>
</w:styles>
"""


def _para(text: str, style: str = "Normal", italic: bool = False) -> str:
    runs = []
    for line in text.split("\n"):
        line = escape(line)
        rpr = "<w:rPr><w:i/></w:rPr>" if italic else ""
        runs.append(f"<w:r>{rpr}<w:t xml:space=\"preserve\">{line}</w:t></w:r>")
    style_xml = f"<w:pPr><w:pStyle w:val=\"{style}\"/></w:pPr>"
    return f"<w:p>{style_xml}{''.join(runs)}</w:p>"


def _page_break() -> str:
    return "<w:p><w:r><w:br w:type=\"page\"/></w:r></w:p>"


def _build_docx_body(project: BookProject, book_n: int) -> str:
    book = project.book(book_n)
    year = datetime.now().year
    author = project.author_pen_name or project.author_name or "(Author Name)"
    real_name = project.author_name or author
    title = book.title or f"Book {book_n}"
    series = project.title

    body = []
    body.append(_para(title, style="Title"))
    body.append(_para(f"{series} — Book {book_n}", style="Heading2", italic=True))
    body.append(_para(f"by {author}", style="Heading2"))
    body.append(_page_break())
    body.append(_para("Copyright", style="Heading2"))
    body.append(_para(f"Copyright © {year} {real_name}. All rights reserved."))
    body.append(_para(
        "This is a work of fiction. Names, characters, places, and incidents are "
        "products of the author's imagination or are used fictitiously. Any "
        "resemblance to actual persons, living or dead, or actual events is "
        "coincidental."))
    body.append(_para(
        "No part of this book may be reproduced, scanned, or distributed in any "
        "printed or electronic form without permission of the author."))
    body.append(_page_break())
    body.append(_para("AI Disclosure", style="Heading2"))
    body.append(_para(
        "Portions of the prose in this book were drafted with the assistance of "
        "artificial-intelligence text-generation tools and subsequently reviewed "
        "by the author. The plot, characters, world, magic system, and editorial "
        "selection and arrangement of the text are the author's original work."))
    body.append(_page_break())

    for ch in sorted(book.chapters, key=lambda c: c["number"]):
        n = ch["number"]
        text = _resolve_chapter_text(project, book_n, ch).strip()
        if not text:
            continue
        chap_title = ch.get("title", f"Chapter {n}")
        body.append(_para(f"Chapter {n}", style="Heading1"))
        body.append(_para(chap_title, style="Heading2", italic=True))
        for para in re.split(r"\n\s*\n", text):
            para = para.strip()
            if not para:
                continue
            if para in ("⁂", "***", "* * *"):
                body.append(_para(para, style="SceneBreak"))
                continue
            body.append(_para(para))
    return "".join(body)


def _write_docx(project: BookProject, book_n: int, out_path: Path):
    body_xml = _build_docx_body(project, book_n)
    document_xml = (
        f"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
        f"<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
        f"<w:body>{body_xml}"
        f"<w:sectPr><w:pgSz w:w=\"12240\" w:h=\"15840\"/>"
        f"<w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\"/></w:sectPr>"
        f"</w:body></w:document>"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _DOCX_CONTENT_TYPES)
        z.writestr("_rels/.rels", _DOCX_RELS)
        z.writestr("word/_rels/document.xml.rels", _DOCX_DOC_RELS)
        z.writestr("word/styles.xml", _DOCX_STYLES)
        z.writestr("word/document.xml", document_xml)


_EPUB_CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
_EPUB_CSS = """\
body { font-family: Georgia, serif; line-height: 1.6; margin: 1em; }
h1   { text-align: center; margin-top: 3em; font-size: 2em; }
h2   { text-align: center; margin-top: 2em; font-size: 1.5em; }
p    { text-indent: 1.5em; margin: 0 0 0.5em; }
.scene-break { text-align: center; margin: 1.5em 0; text-indent: 0; }
.titlepage   { text-align: center; margin-top: 30%; }
.titlepage h1 { font-size: 2.5em; }
.titlepage .by { font-style: italic; margin-top: 2em; }
"""


def _html_paragraphs(text: str) -> str:
    out = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if para in ("⁂", "***", "* * *"):
            out.append(f'<p class="scene-break">{escape(para)}</p>')
        else:
            out.append(f"<p>{escape(para)}</p>")
    return "\n".join(out)


def _chapter_xhtml(title: str, n: int, body_md: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
  <title>Chapter {n}</title>
  <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>
  <h1>Chapter {n}</h1>
  <h2>{escape(title)}</h2>
{_html_paragraphs(body_md)}
</body>
</html>
"""


def _titlepage_xhtml(title: str, series: str, book_n: int, author: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
  <title>{escape(title)}</title>
  <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>
  <div class="titlepage">
    <h1>{escape(title)}</h1>
    <p><em>{escape(series)} — Book {book_n}</em></p>
    <p class="by">by {escape(author)}</p>
  </div>
</body>
</html>
"""


def _frontmatter_xhtml(real_name: str, year: int) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
  <title>Copyright and Disclosure</title>
  <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>
  <h2>Copyright</h2>
  <p>Copyright © {year} {escape(real_name)}. All rights reserved.</p>
  <p>This is a work of fiction. Names, characters, places, and incidents are
  products of the author's imagination or are used fictitiously. Any
  resemblance to actual persons, living or dead, or actual events is
  coincidental.</p>
  <p>No part of this book may be reproduced, scanned, or distributed in any
  printed or electronic form without permission of the author.</p>

  <h2>AI Disclosure</h2>
  <p>Portions of the prose in this book were drafted with the assistance of
  artificial-intelligence text-generation tools and subsequently reviewed by
  the author. The plot, characters, world, magic system, and editorial
  selection and arrangement of the text are the author's original work.</p>
</body>
</html>
"""


def _write_epub(project: BookProject, book_n: int, out_path: Path):
    book = project.book(book_n)
    year = datetime.now().year
    author = project.author_pen_name or project.author_name or "(Author Name)"
    real_name = project.author_name or author
    title = book.title or f"Book {book_n}"
    series = project.title
    book_uuid = "urn:uuid:" + str(uuid.uuid4())

    chapters = [c for c in sorted(book.chapters, key=lambda c: c["number"])
                if _resolve_chapter_text(project, book_n, c).strip()]

    manifest_items = [
        '<item id="ncx"     href="toc.ncx"        media-type="application/x-dtbncx+xml"/>',
        '<item id="css"     href="styles.css"     media-type="text/css"/>',
        '<item id="title"   href="titlepage.xhtml" media-type="application/xhtml+xml"/>',
        '<item id="front"   href="frontmatter.xhtml" media-type="application/xhtml+xml"/>',
    ]
    spine_items = ['<itemref idref="title"/>', '<itemref idref="front"/>']
    nav_points  = []
    for i, ch in enumerate(chapters, start=1):
        cid = f"ch{i:03d}"
        manifest_items.append(
            f'<item id="{cid}" href="{cid}.xhtml" media-type="application/xhtml+xml"/>'
        )
        spine_items.append(f'<itemref idref="{cid}"/>')
        nav_points.append(
            f'<navPoint id="np-{cid}" playOrder="{i+2}">'
            f'<navLabel><text>Chapter {ch["number"]}: {escape(ch.get("title",""))}</text></navLabel>'
            f'<content src="{cid}.xhtml"/></navPoint>'
        )

    content_opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="bookid">{book_uuid}</dc:identifier>
    <dc:title>{escape(title)}</dc:title>
    <dc:creator opf:role="aut">{escape(author)}</dc:creator>
    <dc:language>en</dc:language>
    <dc:date>{year}</dc:date>
    <dc:rights>Copyright © {year} {escape(real_name)}. All rights reserved.</dc:rights>
    <dc:description>{escape(series)} — Book {book_n}</dc:description>
  </metadata>
  <manifest>
    {"".join(manifest_items)}
  </manifest>
  <spine toc="ncx">
    {"".join(spine_items)}
  </spine>
</package>
"""

    toc_ncx = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{book_uuid}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{escape(title)}</text></docTitle>
  <navMap>
    <navPoint id="np-title" playOrder="1"><navLabel><text>Title page</text></navLabel><content src="titlepage.xhtml"/></navPoint>
    <navPoint id="np-front" playOrder="2"><navLabel><text>Copyright</text></navLabel><content src="frontmatter.xhtml"/></navPoint>
    {"".join(nav_points)}
  </navMap>
</ncx>
"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", _EPUB_CONTAINER, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf",      content_opf,     compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/toc.ncx",          toc_ncx,         compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/styles.css",       _EPUB_CSS,       compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/titlepage.xhtml",
                   _titlepage_xhtml(title, series, book_n, author),
                   compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/frontmatter.xhtml",
                   _frontmatter_xhtml(real_name, year),
                   compress_type=zipfile.ZIP_DEFLATED)
        for i, ch in enumerate(chapters, start=1):
            cid = f"ch{i:03d}"
            body = _resolve_chapter_text(project, book_n, ch).strip()
            z.writestr(f"OEBPS/{cid}.xhtml",
                       _chapter_xhtml(ch.get("title", ""), ch["number"], body),
                       compress_type=zipfile.ZIP_DEFLATED)


def export_book(project: BookProject, book_n: int, formats: list[str]) -> list[Path]:
    book = project.book(book_n)
    if not book.chapters:
        print(f"  [Export] Book {book_n}: no chapters yet.")
        return []

    book_dir = project.book_dir(book_n)
    slug = _slugify(book.title or f"book-{book_n}")
    written = []

    if _have_pandoc() and "md" not in formats:
        md_text = _build_intermediate_markdown(project, book_n)
        for fmt in formats:
            out_path = book_dir / f"{slug}.{fmt}"
            print(f"  [Export] pandoc → {out_path}")
            try:
                _pandoc_convert(md_text, out_path, fmt=fmt)
                written.append(out_path)
            except subprocess.CalledProcessError as e:
                print(f"  [Export] pandoc failed for {fmt}: {e.stderr[:300]}")
        return written

    for fmt in formats:
        out_path = book_dir / f"{slug}.{fmt}"
        if fmt == "docx":
            print(f"  [Export] writing {out_path} (manual)")
            _write_docx(project, book_n, out_path)
            written.append(out_path)
        elif fmt == "epub":
            print(f"  [Export] writing {out_path} (manual)")
            _write_epub(project, book_n, out_path)
            written.append(out_path)
        elif fmt == "md":
            print(f"  [Export] writing {out_path}")
            out_path.write_text(_build_intermediate_markdown(project, book_n),
                                encoding="utf-8")
            written.append(out_path)
        else:
            print(f"  [Export] format {fmt} not supported without pandoc; skipping.")
    return written
