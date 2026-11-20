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


def section_info(heading):
    """'### [00:00 - 01:00] BAB 2: Data PISA & INOVASI' -> ('BAB 2', 'Data PISA & INOVASI')."""
    rest = re.sub(r"^###\s*", "", heading).strip()
    rest = re.sub(r"^\[[^\]]*\]\s*", "", rest).strip()
    if ":" in rest:
        prefix, title = rest.split(":", 1)
        title = title.strip()
    else:
        prefix, title = rest, rest
    prefix = prefix.strip()
    m = re.match(r"(BAB\s*\d+|INTRO|OUTRO)", prefix, re.I)
    chapter = m.group(1).upper() if m else prefix.upper()[:26]
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


def parse_markdown(path, words_per_scene):
    raw = Path(path).read_text(encoding="utf-8")
    sections = re.split(r"(?m)^###\s+", raw)[1:]
    scenes = []
    for body in sections:
        heading, _, rest = body.partition("\n")
        chapter, title = section_info(heading)
        m = re.search(r"\*\*Voiceover\s*\(Narasi\)\s*\*\*\s*:(.*?)(?=\n---|\Z)", rest, re.S)
        narration = clean_text(m.group(1) if m else "")
        if not narration.strip():
            narration = clean_text("\n".join(
                ln for ln in rest.splitlines()
                if ln.strip() and not ln.lstrip().startswith(("#", "|", "**", "*", "-", "<!--", ">"))
            ))
        chunks = chunk_text(narration, words_per_scene)
        if not chunks:
            continue

        directives = [parse_directive(c) for c in re.findall(r"<!--(.*?)-->", rest, re.S)]
        directives = [d for d in directives if d]
        if directives and len(directives) > len(chunks):
            chunks = chunk_to_count(narration, len(directives))

        hint_m = re.search(r"(?:\*Text on Screen\*|Text on Screen)\s*:\s*(.+)", rest)
        hint = clean_headline(clean_text(hint_m.group(1) if hint_m else ""), chunks[0])

        for i, chunk in enumerate(chunks):
            d = directives[i] if i < len(directives) else None
            d = dict(d or {})
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
    return scenes


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
