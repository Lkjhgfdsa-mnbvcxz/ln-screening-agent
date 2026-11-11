"""Bounded parsing of uploaded/local bytes, not HTTP fetching, OCR or content execution.

PDF/DOCX/XLSX use optional libraries present in the development environment.
No parsed text or LLM output is inherently verified source truth.
"""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile
from .models import Block, SourceDocument

MAX_BYTES = 10 * 1024 * 1024
MAX_BLOCKS = 50000
MAX_TEXT_CHARS = 1_500_000
MAX_ZIP_XML_BYTES = 12 * 1024 * 1024

class UnsupportedDocument(ValueError): pass
class DocumentTooLarge(ValueError): pass

class _HTMLBlocks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.groups: list[tuple[str,str]] = []
        self.current: list[str] = []
        self.active = "paragraph"
        self.ignore_depth = 0
        self.references: list[dict[str,str]] = []
        self.current_link: dict | None = None
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "iframe"):
            self.ignore_depth += 1
            return
        if self.ignore_depth:
            return
        if tag == "a":
            href=dict(attrs).get("href", "") or ""
            if href and not href.strip().lower().startswith(("javascript:", "data:", "file:")):
                self.current_link={"href":href,"text":""}
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "tr"):
            self._flush()
            self.active = "heading" if tag.startswith("h") else ("table_row" if tag == "tr" else "paragraph")
        elif tag in ("td", "th"):
            self.current.append(" | ")
        elif tag == "br":
            self.current.append(" ")
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "iframe"):
            self.ignore_depth = max(0, self.ignore_depth - 1)
            return
        if tag == "a" and self.current_link is not None:
            self.current_link["text"]=self.current_link["text"].strip()
            self.current_link["status"]="not_fetched_not_verified"
            self.references.append(self.current_link)
            self.current_link=None
        if not self.ignore_depth and tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "tr"):
            self._flush()
            self.active = "paragraph"
    def handle_data(self, data):
        if not self.ignore_depth:
            self.current.append(data)
            if self.current_link is not None:
                self.current_link["text"]+=data
    def _flush(self):
        value = re.sub(r"\s+", " ", "".join(self.current)).strip(" |")
        if value:
            self.groups.append((value, self.active))
        self.current = []
    def finish(self):
        self._flush()
        return self.groups

_HEADING = re.compile(r"^(第[一二三四五六七八九十百0-9]+[章节条]|(?:[一二三四五六七八九十]+、)|(?:\d+[.、]\s+))")

def _plain_blocks(text: str, kind: str = "paragraph") -> list[tuple[int|None,str,str,str]]:
    out=[]
    for page,part in enumerate(text.split("\f"), 1):
        for line in part.splitlines():
            line = line.strip()
            if not line: continue
            out.append((page,line,"heading" if _HEADING.match(line) else kind,""))
    return out

def _docx_rows(data: bytes) -> list[tuple[int|None,str,str,str]]:
    ns="{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with ZipFile(BytesIO(data)) as z:
        info = z.getinfo("word/document.xml")
        if info.file_size > MAX_ZIP_XML_BYTES: raise DocumentTooLarge("DOCX XML is too large")
        root = ET.fromstring(z.read(info))
    body = root.find(".//"+ns+"body")
    if body is None:return []
    rows=[]
    def text_of(node):
        return "".join(t.text or "" for t in node.iter(ns+"t")).strip()
    for n in body:
        if n.tag==ns+"p":
            content=text_of(n)
            if content:
                style=n.find("./"+ns+"pPr/"+ns+"pStyle")
                code=(style.get(ns+"val","") if style is not None else "")
                kind="heading" if code.lower().startswith("heading") or _HEADING.match(content) else "paragraph"
                rows.append((None,content,kind,""))
        elif n.tag==ns+"tbl":
            for ri,tr in enumerate(n.findall("./"+ns+"tr"),1):
                parts=[text_of(td) for td in tr.findall("./"+ns+"tc")]
                if any(parts): rows.append((None," | ".join(parts),"table_row",f"row:{ri}"))
    return rows

def _xlsx_rows(data: bytes) -> list[tuple[int|None,str,str,str]]:
    try: from openpyxl import load_workbook
    except ImportError as e: raise UnsupportedDocument("XLSX reader requires openpyxl") from e
    wb = load_workbook(BytesIO(data),read_only=True,data_only=True,keep_links=False)
    try:
        rows=[]
        for sheet in wb:
            for i,values in enumerate(sheet.iter_rows(values_only=True),1):
                values=[str(x).strip() if x is not None else "" for x in values]
                if any(values): rows.append((None," | ".join(values),"table_row",f"sheet:{sheet.title};row:{i}"))
                if len(rows)>MAX_BLOCKS: raise DocumentTooLarge("too many spreadsheet rows")
        return rows
    finally: wb.close()

def _pdf_rows(data: bytes) -> tuple[list[tuple[int|None,str,str,str]],list[str]]:
    try: from pypdf import PdfReader
    except ImportError as e: raise UnsupportedDocument("PDF reader requires pypdf") from e
    reader=PdfReader(BytesIO(data), strict=False)
    if reader.is_encrypted: raise UnsupportedDocument("encrypted PDF requires authorized decryption")
    if len(reader.pages)>300: raise DocumentTooLarge("PDF has too many pages for local review")
    out=[]; warnings=[];total_chars=0
    for page_idx,p in enumerate(reader.pages,1):
        txt=p.extract_text() or ""
        total_chars+=len(txt)
        if total_chars>MAX_TEXT_CHARS: raise DocumentTooLarge("PDF expanded text too large")
        if not txt.strip(): warnings.append(f"PAGE_{page_idx}_NO_SEARCHABLE_TEXT_OCR_MAY_BE_REQUIRED")
        for row in _plain_blocks(txt):out.append((page_idx,row[1],row[2],row[3]))
        if len(out)>MAX_BLOCKS: raise DocumentTooLarge("too many PDF text blocks")
    return out,warnings

def parse_document(data: bytes, *, document_id: str, content_type: str,
                   source_url: str = "", title: str = "", publisher: str = "",
                   document_number: str = "", retrieved_at: str = "") -> SourceDocument:
    if not isinstance(data,bytes): raise TypeError("data must be bytes")
    if not document_id: raise ValueError("document_id required")
    if len(data)>MAX_BYTES: raise DocumentTooLarge("input exceeds 10MB local safety limit")
    ct=content_type.lower().split(";",1)[0].strip()
    warnings=[]
    references=[]
    if ct in ("text/plain","text/markdown","application/json"):
        rows=_plain_blocks(data.decode("utf-8-sig",errors="replace"))
    elif ct in ("text/html","application/xhtml+xml"):
        doc=_HTMLBlocks(); doc.feed(data.decode("utf-8-sig",errors="replace"))
        rows=[(None,s,k,"") for s,k in doc.finish()]
        references=doc.references[:200]
    elif ct=="application/pdf":
        rows,warnings=_pdf_rows(data)
    elif ct=="application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        rows=_docx_rows(data)
    elif ct=="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        rows=_xlsx_rows(data)
    else:
        raise UnsupportedDocument(f"unsupported content type: {ct}")
    if len(rows)>MAX_BLOCKS: raise DocumentTooLarge("too many text blocks")
    if sum(len(r[1]) for r in rows)>MAX_TEXT_CHARS: raise DocumentTooLarge("extracted text exceeds limit")
    section=""; blocks=[]
    for i,(page,txt,kind,hint) in enumerate(rows):
        if kind=="heading": section=txt[:180]
        blocks.append(Block(index=i,page=page,text=txt,section=section,kind=kind,location_hint=hint))
    return SourceDocument(document_id=document_id,source_url=source_url,title=title,publisher=publisher,
       content_type=ct,sha256=sha256(data).hexdigest(),blocks=tuple(blocks),warnings=tuple(warnings),
       retrieved_at=retrieved_at or datetime.now(timezone.utc).isoformat(),document_number=document_number,
       references=tuple(references))
