#!/usr/bin/env python3
"""Parse a markdown naskah (or a JSON scene list) into render-ready scenes.

A scene has the same shape the renderer expects:
{text, chapter, title, headline, sub, accent, vis:(type, spec)}
"""
import json
import re
from pathlib import Path

ABBREV = ["Dr", "Prof", "No", "Mr", "Mrs", "Ms", "dll", "etc", "ca",
          "vs", "thn", "jt", "km", "Hr", "Sdt", "Rp"]
ABBREV_RE = re.compile(r"\b(" + "|".join(re.escape(a) for a in ABBREV) + r")\.")

ACCENT_CYCLE = {
    "INTRO": "teal", "OUTRO": "teal",
    "BAB 1": "orange", "BAB 2": "blue", "BAB 3": "purple", "BAB 4": "teal",
}


def clean_text(text):
    """Strip Markdown/HTML decoration so TTS reads plain words."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # links
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = text.replace("*", "")  # emphasis / italic markers
    text = re.sub(r"<[^>]+>", "", text)  # HTML tags
    text = re.sub(r"(?m)^\s*>\s?", "", text)  # blockquote markers
    text = text.replace('"', "").replace("\u201c", "").replace("\u201d", "")
    text = re.sub(r"Voiceover\s*\(Narasi\)\s*:", " ", text, flags=re.I)
    text = re.sub(r"Visual\s*Cue\s*:|Text\s*on\s*Screen\s*:", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text):
    protected = ABBREV_RE.sub(lambda m: m.group(1) + "<DOT>", text)
    parts = re.split(r"(?<=[.!?])\s+(?=[\w\"\u201c(])", protected)
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]


def chunk_text(text, words_per_scene):
    sentences = split_sentences(text)
    chunks, cur, count = [], [], 0
    for s in sentences:
        n = len(s.split())
        if cur and count + n > words_per_scene:
            chunks.append(" ".join(cur))
            cur, count = [], 0
        cur.append(s)
        count += n
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def chunk_to_count(text, n):
    """Split text into exactly n chunks (roughly equal word counts)."""
    sentences = split_sentences(text)
    if n <= 1 or len(sentences) <= 1:
        return [text] if text.strip() else []
    target = max(1, round(sum(len(s.split()) for s in sentences) / n))
    groups, cur, count = [], [], 0
    for s in sentences:
        w = len(s.split())
        if cur and len(groups) < n - 1 and count + w > target:
            groups.append(" ".join(cur))
            cur, count = [], 0
        cur.append(s)
        count += w
    if cur:
        groups.append(" ".join(cur))
    return groups


def parse_directive(comment):
    """Parse <!-- scene: type=stat big=56 label="..." --> into a dict."""
    inner = comment.strip()
    if inner.startswith("<!--"):
        inner = inner[4:]
    if inner.endswith("-->"):
        inner = inner[:-3]
    inner = inner.strip()
    if not re.match(r"^(scene|visual)\s*:", inner, re.I):
        return None
    inner = re.sub(r"^(scene|visual)\s*:\s*", "", inner, count=1, flags=re.I)
    pairs = re.findall(r'(\w+)\s*=\s*("[^"]*"|\'[^\']*\'|\S+)', inner)
    return {k: v.strip("\"'") for k, v in pairs}


HEADING_RE = re.compile(r"(?m)^(#{2,6})[ \t]+(.+?)[ \t]*$")
NARRATION_HEADING_RE = re.compile(r"voice[\s-]*over|narasi|narration", re.I)
MARKER_RE = re.compile(
    r"(?:\*\*)?(?:Voiceover\s*\(Narasi\)|Narasi\s*Presenter|Narasi|Voiceover)"
    r"\s*:\s*(?:\*\*)?\s*(.*?)(?=\n\s*---|\Z)",
    re.S | re.I,
)


def blockquote_text(body):
    """Collect consecutive '> ' lines (including blank '>' separators)."""
    kept = []
    for ln in body.splitlines():
        s = ln.strip()
        if s.startswith(">"):
            s = re.sub(r"^(?:>\s*)+", "", s).strip()
            if s or (kept and kept[-1]):
                kept.append(s)
        elif not s and kept and kept[-1]:
            kept.append("")
    while kept and not kept[0]:
        kept.pop(0)
    while kept and not kept[-1]:
        kept.pop()
    return "\n".join(kept)


def plain_fallback(body):
    """Old fallback: prose lines that are not headings/tables/lists/quotes."""
    return "\n".join(
        ln for ln in body.splitlines()
        if ln.strip() and not ln.lstrip().startswith(("#", "|", "**", "*", "-", "<!--", ">"))
    )


def block_narration(heading, body):
    """Find spoken text in one heading block, regardless of naskah style."""
    if NARRATION_HEADING_RE.search(heading):
        q = blockquote_text(body)
        if q:
            return clean_text(q)
    m = MARKER_RE.search(body)
    if m:
        txt = clean_text(m.group(1))
        if txt:
            return txt
    q = blockquote_text(body)
    if q:
        return clean_text(q)
    return clean_text(plain_fallback(body))


def section_info(heading):
    """'### [00:00 - 01:00] BAB 2: Data PISA & INOVASI' -> ('BAB 2', 'Data PISA & INOVASI')."""
    rest = re.sub(r"^#{2,6}\s*", "", heading).strip()
    rest = re.sub(r"^\[[^\]]*\]\s*", "", rest).strip()
    rest = re.sub(r"^[^\w]+", "", rest).strip()  # emoji / decorative prefix
    rest = re.sub(r"[\(（]?\s*\d{1,2}:\d{2}\s*[–—-]\s*\d{1,2}:\d{2}\s*\)?\s*$", "", rest).strip()
    if ":" in rest:
        prefix, title = rest.split(":", 1)
        title = title.strip()
    else:
        prefix, title = rest, rest
    prefix = prefix.strip()
    if re.search(r"\bINTRO\b", prefix, re.I):
        chapter = "INTRO"
    elif re.search(r"\bOUTRO\b", prefix, re.I):
        chapter = "OUTRO"
    else:
        m = re.match(r"BAB\s*\d+", prefix, re.I)
        chapter = m.group(0).upper() if m else prefix.upper()[:26]
    if not title or title == prefix:
        title = prefix
    return chapter, title


def visual_from_directive(d, fallback_sentences, headline_hint):
    """Build the (type, spec) tuple used by the renderer."""
    if not d:
        items = fallback_sentences[:3]
        if len(items) == 1:
            return "quote", {"text": items[0].rstrip("."), "by": headline_hint}
        return "bullets", {"items": [s.rstrip(".") for s in items]}

    typ = d.get("type", "bullets").lower()
    items = d.get("items", "")
    parts = [p.strip() for p in items.split("|") if p.strip()] or fallback_sentences[:3]

    if typ == "hook":
        return typ, {"chips": [c.strip() for c in d.get("chips", "IPA|IPS|BAHASA").split("|")]}
    if typ == "bullets":
        return typ, {"items": [p.rstrip(".") for p in parts]}
    if typ == "split":
        out = []
        for p in parts:
            if "::" in p:
                a, b = p.split("::", 1)
                out.append((a.strip(), b.strip()))
            else:
                out.append((p.strip(), ""))
        return typ, {"items": out}
    if typ == "stat":
        return typ, {"big": d.get("big", ""), "label": d.get("label", ""),
                     "sub": d.get("sub", "")}
    if typ == "card":
        return typ, {"tag": d.get("tag", ""), "title": d.get("title", ""),
                     "bullets": [p.rstrip(".") for p in parts],
                     "foot": d.get("foot", "")}
    if typ == "quote":
        return typ, {"text": d.get("text", fallback_sentences[0] if fallback_sentences else headline_hint),
                     "by": d.get("by", "")}
    if typ == "cta":
        return typ, {"chips": [c.strip() for c in d.get("chips", "LIKE|SHARE|SUBSCRIBE").split("|")]}
    if typ == "title":
        return typ, {"big": d.get("big", "?")}
    if typ == "cards":
        out = []
        for p in parts:
            f = [x.strip() for x in p.split("::")]
            f += [""] * (4 - len(f))
            out.append((f[0], f[1], f[2], f[3] or "teal"))
        return typ, {"items": out}
    if typ == "progress":
        rows = []
        for p in parts:
            f = [x.strip() for x in p.split(":")]
            if len(f) >= 3:
                rows.append((f[0], float(f[1]), float(f[2])))
        return typ, {"rows": rows, "foot": d.get("foot", "")}
    if typ == "chart":
        subjects = [s.strip() for s in d.get("subjects", "Membaca,Matematika,Sains").split(",")]
        groups = []
        for g in d.get("groups", "").split("|"):
            f = [x.strip() for x in g.split(":")]
            if len(f) >= 3:
                vals = [(subjects[i], float(v)) for i, v in enumerate(f[2].split(",")) if i < len(subjects)]
                groups.append((f[0], f[1], vals))
        if not groups:
            return "bullets", {"items": [p.rstrip(".") for p in parts]}
        return typ, {"groups": groups, "foot": d.get("foot", "")}
    return "bullets", {"items": [p.rstrip(".") for p in parts]}


def clean_headline(text, fallback):
    text = (text or "").replace("\\n", "\n")
    text = re.sub(r"[\"']", "", text).replace("\u201c", "").replace("\u201d", "")
    text = text.replace("*", "").strip()
    parts = [p.strip() for p in text.split("/") if p.strip()]
    if parts:
        text = parts[0] if len(parts[0]) >= 12 else " ".join(parts)
    if not text:
        text = fallback[:140].rstrip(" ,.;:")
    if len(text) > 58 and "\n" not in text:
        words, cur = [], ""
        for w in text.replace("\n", " ").split():
            if len(cur) + len(w) + 1 > 28:
                words.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        if cur:
            words.append(cur)
        text = "\n".join(words[:2])
    return text


def find_title(raw):
    """YouTube title from metadata (Judul/Judul Konten) or the first H1."""
    m = re.search(r"(?im)^\*{0,2}Judul(?:\s+(?:Utama\s+)?(?:Konten|Video))?\*{0,2}\s*:\s*(.+)", raw)
    if not m:
        m = re.search(r"(?m)^#\s+(.+)", raw)
    return clean_text(m.group(1)).strip() if m else ""


def apply_opening(scenes, raw):
    """Make the first scene an unmistakable title + hook card."""
    if not scenes:
        return scenes
    title = find_title(raw)
    if not title:
        return scenes
    first = scenes[0]
    first["headline"] = title
    first["sub"] = split_sentences(first["text"])[0] if split_sentences(first["text"]) else ""
    first["vis"] = ("opening", {})
    first["is_opening"] = True
    return scenes


def parse_markdown(path, words_per_scene):
    """Parse any markdown naskah, no matter which heading level holds narration.

    Supports: '**Voiceover (Narasi)**:' prose, a 'Voiceover Narasi' heading
    with '> ' blockquotes, plain blockquotes, HTML scene directives, and
    heading prefixes such as emoji or '[00:00 - 01:00]' time ranges.
    """
    raw = Path(path).read_text(encoding="utf-8")
    blocks = []
    matches = list(HEADING_RE.finditer(raw))
    for j, m in enumerate(matches):
        start = m.end()
        end = matches[j + 1].start() if j + 1 < len(matches) else len(raw)
        heading = m.group(2).strip()
        body = raw[start:end]
        blocks.append({
            "level": len(m.group(1)),
            "heading": heading,
            "body": body,
            "narr": block_narration(heading, body),
        })

    narrating = [b for b in blocks if b["narr"].strip()]
    if not narrating:
        return []
    # The deepest heading level that actually carries spoken text defines a scene.
    use_level = max(b["level"] for b in narrating)

    scenes = []
    for idx, b in enumerate(blocks):
        if b["level"] != use_level or not b["narr"].strip():
            continue
        ancestor = next((p for p in reversed(blocks[:idx])
                         if p["level"] < use_level), None)
        ctx = [b["body"]] + ([ancestor["body"]] if ancestor else [])
        own = b["heading"]
        heading_for_meta = ancestor["heading"] if ancestor and NARRATION_HEADING_RE.search(own) else own
        chapter, title = section_info(heading_for_meta)
        narration = b["narr"]
        chunks = chunk_text(narration, words_per_scene)
        if not chunks:
            continue

        comments = []
        for piece in ctx:
            comments += re.findall(r"<!--(.*?)-->", piece, re.S)
        directives = [parse_directive(c) for c in comments]
        directives = [d for d in directives if d]
        if directives and len(directives) > len(chunks):
            chunks = chunk_to_count(narration, len(directives))

        hint_src = " ".join(ctx)
        hint_m = re.search(r"Text[\s-]*On?[\s-]*Screen\s*\*{0,2}\s*:\s*(.+)",
                           hint_src, re.I)
        hint = clean_headline(clean_text(hint_m.group(1) if hint_m else ""), chunks[0])

        for i, chunk in enumerate(chunks):
            d = dict(directives[i] if i < len(directives) else None or {})
            headline = clean_headline(d.pop("headline", "" if i else hint), chunk)
            sub = d.pop("sub", "")
            accent = d.pop("accent", ACCENT_CYCLE.get(chapter, "teal"))
            vis = visual_from_directive(d or None, split_sentences(chunk), headline)
            scenes.append({
                "text": chunk,
                "chapter": chapter,
                "title": title,
                "headline": headline,
                "sub": sub,
                "accent": accent,
                "vis": vis,
            })
    return apply_opening(scenes, raw)


def parse_json(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("scenes", [])
    out = []
    for s in data:
        vis = s.get("vis")
        if isinstance(vis, list) and len(vis) == 2:
            vis = (vis[0], vis[1])
        else:
            vis = ("bullets", {"items": [s.get("text", "")[:80]]})
        out.append({
            "text": s.get("text", ""),
            "chapter": s.get("chapter", "SCENE"),
            "title": s.get("title", ""),
            "headline": s.get("headline", s.get("text", "")[:60]),
            "sub": s.get("sub", ""),
            "accent": s.get("accent", "teal"),
            "vis": vis,
        })
    return out


def load_scenes(path, words_per_scene=38):
    path = Path(path)
    if path.suffix.lower() == ".json":
        return parse_json(path)
    return parse_markdown(path, words_per_scene)


def document_title(path):
    """Take the first H1 of a markdown naskah as the video's footer title."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        return "VIDEO EDUKASI"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return clean_text(line[2:].strip())[:64]
    return "VIDEO EDUKASI"
