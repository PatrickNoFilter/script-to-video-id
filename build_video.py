#!/usr/bin/env python3
"""Build a narrated explainer MP4 from ANY markdown naskah or JSON scene list.

Pipeline: naskah -> scene parser -> Edge-TTS (id-ID) -> Pillow slides -> ffmpeg.
See naskah_parser.py for the supported markdown structure and visual directives.
"""
import asyncio
import os
import re
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H = 1920, 1080
WORK = Path(os.environ.get("VIDEO_WORK", str(ROOT / ".build"))).resolve()
AUDIO_DIR = WORK / "audio"
SLIDE_DIR = WORK / "slides"
OUT = Path(os.environ.get("VIDEO_OUT", str(ROOT / "output" / "video.mp4"))).resolve()
VOICE = os.environ.get("VIDEO_VOICE", "id-ID-GadisNeural")
GAP = 0.28
_music = os.environ.get("VIDEO_MUSIC")
MUSIC = Path(_music).resolve() if _music else None
LOOP = WORK / "music_loop.wav"

FONT_REG = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
_font_cache = {}


def F(size, bold=False):
    key = (size, bold)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)
    return _font_cache[key]


C = {
    "bg_top": (9, 14, 30),
    "bg_bot": (17, 27, 50),
    "grid": (26, 38, 64),
    "text": (240, 245, 255),
    "muted": (156, 173, 204),
    "dim": (105, 124, 158),
    "track": (33, 47, 76),
    "teal": (45, 212, 191),
    "orange": (251, 146, 60),
    "blue": (96, 165, 250),
    "purple": (167, 139, 250),
    "red": (248, 113, 113),
}


# ---------------------------------------------------------------------------
# Scene source: any markdown naskah or JSON scene list
# ---------------------------------------------------------------------------
import argparse

from naskah_parser import document_title, load_scenes

_ap = argparse.ArgumentParser(description="Naskah -> video naratif MP4")
_ap.add_argument("--naskah", default=str(ROOT / "examples" / "naskah-contoh.md"),
                 help="File naskah .md atau daftar scene .json")
_ap.add_argument("--output", default=None, help="Path MP4 hasil")
_ap.add_argument("--voice", default=None, help="Suara Edge-TTS")
_ap.add_argument("--music", default=None, help="Lagu background (opsional)")
_ap.add_argument("--words-per-scene", type=int, default=38,
                 help="Target kata per scene saat memotong narasi")
_args = _ap.parse_args()

OUT = Path(_args.output).resolve() if _args.output else OUT
VOICE = _args.voice or VOICE
if _args.music:
    MUSIC = Path(_args.music).resolve()
SCENES = load_scenes(_args.naskah, _args.words_per_scene)
DOC_TITLE = document_title(_args.naskah).upper()
if not SCENES:
    raise SystemExit(f"Tidak ada scene yang terbaca dari {_args.naskah}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def rgb(name):
    return C.get(name, C["teal"])


def wrap(text, font, max_width, draw):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit(text, max_size, min_size, max_width, max_lines, bold=True):
    for size in range(max_size, min_size - 1, -2):
        f = F(size, bold)
        tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        lines = wrap(text, f, max_width, tmp)
        if len(lines) <= max_lines:
            return f, lines
    return F(min_size, bold), wrap(text, F(min_size, bold), max_width, tmp)


def run(cmd, quiet=True):
    if quiet:
        return subprocess.run(cmd, capture_output=True, text=True)
    return subprocess.run(cmd, text=True)


def probe_duration(path):
    r = run([FFMPEG, "-hide_banner", "-i", str(path)])
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr)
    if not m:
        raise RuntimeError(f"Cannot probe duration: {path}\n{r.stderr[-500:]}")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


# ---------------------------------------------------------------------------
# Slide rendering
# ---------------------------------------------------------------------------
def background(accent):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    top, bot = C["bg_top"], C["bg_bot"]
    for y in range(H):
        t = y / H
        col = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
        d.line([(0, y), (W, y)], fill=col)
    for x in range(0, W, 96):
        d.line([(x, 0), (x, H)], fill=C["grid"], width=1)
    for y in range(0, H, 96):
        d.line([(0, y), (W, y)], fill=C["grid"], width=1)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    a = rgb(accent)
    od.ellipse([W - 520, -260, W + 180, 440], fill=(*a, 20))
    od.ellipse([-300, H - 460, 300, H + 160], fill=(*a, 14))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def draw_header(draw, scene, idx, total):
    a = rgb(scene["accent"])
    draw.rectangle([0, 0, W, 8], fill=C["track"])
    draw.rectangle([0, 0, int(W * (idx + 1) / total), 8], fill=a)
    # chapter pill
    label = f"{scene['chapter']}  ·  {scene['title'].upper()}"
    font = F(25, True)
    tw = draw.textlength(label, font=font)
    draw.rounded_rectangle([70, 52, 70 + tw + 44, 104], radius=26, fill=C["track"])
    draw.rounded_rectangle([70, 52, 70 + tw + 44, 104], radius=26, outline=a, width=2)
    draw.text((92, 63), label, font=font, fill=a)
    draw.text((W - 90, 63), f"{idx+1:02d} / {total:02d}", font=F(26, True), fill=C["muted"], anchor="ra")
    # footer
    draw.text((72, H - 54), DOC_TITLE + " · Video Edukasi", font=F(22), fill=C["dim"])


def draw_headline(draw, scene):
    font, lines = fit(scene["headline"], 64, 42, W - 180, 2, bold=True)
    y = 138
    for line in lines:
        draw.text((72, y), line, font=font, fill=C["text"])
        y += int(font.size * 1.05)
    if scene.get("sub"):
        draw.text((76, y + 8), scene["sub"], font=F(30), fill=C["muted"])
        y += 48
    return max(y + 20, 340)


def draw_hook(draw, img, scene, y):
    a = rgb(scene["accent"])
    chips = scene["vis"][1]["chips"]
    d = ImageDraw.Draw(img)
    x = 90
    for i, chip in enumerate(chips):
        f = F(52, True)
        w = int(d.textlength(chip, font=f)) + 80
        box = [x, y + 60, x + w, y + 170]
        col = [a, C["orange"], C["purple"]][i % 3]
        d.rounded_rectangle(box, radius=24, fill=C["track"], outline=col, width=3)
        d.text((x + 40, y + 83), chip, font=f, fill=col)
        x += w + 36
    d.text((92, y + 230), "Haruskah kembali? Mari kita bedah datanya.", font=F(36), fill=C["muted"])


def draw_bullets(draw, img, scene, y):
    a = rgb(scene["accent"])
    items = scene["vis"][1]["items"]
    for i, item in enumerate(items):
        f, lines = fit(item, 42, 28, W - 420, 2, bold=False)
        box_y = y + i * 150
        draw.rounded_rectangle([80, box_y, W - 90, box_y + 122], radius=20, fill=C["track"])
        draw.ellipse([108, box_y + 33, 168, box_y + 93], fill=a)
        draw.text((138, box_y + 63), str(i + 1), font=F(34, True), fill=C["bg_top"], anchor="mm")
        ty = box_y + 26
        for line in lines:
            draw.text((200, ty), line, font=f, fill=C["text"])
            ty += int(f.size * 1.1)


def draw_split(draw, img, scene, y):
    a = rgb(scene["accent"])
    items = scene["vis"][1]["items"]
    pw = (W - 220) // 2
    for i, (label, body) in enumerate(items):
        x = 80 + i * (pw + 60)
        draw.rounded_rectangle([x, y, x + pw, y + 420], radius=28, fill=C["track"], outline=a, width=2)
        draw.text((x + 44, y + 40), label, font=F(34, True), fill=a)
        draw.line([(x + 44, y + 100), (x + pw - 44, y + 100)], fill=a, width=3)
        f, lines = fit(body, 44, 30, pw - 90, 3, bold=True)
        ty = y + 150
        for line in lines:
            draw.text((x + 44, ty), line, font=f, fill=C["text"])
            ty += int(f.size * 1.2)


def draw_stat(draw, img, scene, y):
    a = rgb(scene["accent"])
    spec = scene["vis"][1]
    draw.text((84, y), spec["big"], font=F(170, True), fill=a)
    draw.text((92, y + 200), spec["label"], font=F(46, True), fill=C["text"])
    if spec.get("sub"):
        f, lines = fit(spec["sub"], 36, 26, W - 200, 2, bold=False)
        ty = y + 270
        for line in lines:
            draw.text((94, ty), line, font=f, fill=C["muted"])
            ty += int(f.size * 1.25)


def draw_card(draw, img, scene, y):
    a = rgb(scene["accent"])
    spec = scene["vis"][1]
    draw.rounded_rectangle([80, y, W - 90, 900], radius=28, fill=C["track"], outline=a, width=3)
    draw.rounded_rectangle([120, y + 34, 120 + int(draw.textlength(spec["tag"], font=F(28, True))) + 44, y + 92],
                           radius=20, fill=a)
    draw.text((142, y + 50), spec["tag"], font=F(28, True), fill=C["bg_top"])
    draw.text((122, y + 130), spec["title"], font=F(76, True), fill=C["text"])
    ty = y + 250
    for b in spec["bullets"]:
        f, lines = fit(b, 40, 28, W - 320, 2, bold=False)
        draw.ellipse([130, ty + 12, 148, ty + 30], fill=a)
        for line in lines:
            draw.text((176, ty), line, font=f, fill=C["text"])
            ty += int(f.size * 1.18)
        ty += 18
    if spec.get("foot"):
        draw.text((124, 856), spec["foot"], font=F(26), fill=C["muted"])


def draw_chart(draw, img, scene, y):
    groups = scene["vis"][1]["groups"]
    foot = scene["vis"][1].get("foot")
    lx = 110
    # legend
    gx = 400
    for name, colname, _ in groups:
        col = rgb(colname)
        draw.rounded_rectangle([gx, y + 6, gx + 34, y + 40], radius=8, fill=col)
        draw.text((gx + 48, y + 4), name, font=F(30, True), fill=col)
        gx += 60 + int(draw.textlength(name, font=F(30, True))) + 90
    maxv = 600
    bar_x, bar_w = 400, 1180
    start = y + 70
    subjects = groups[0][2]
    for si, (subject, _) in enumerate(subjects):
        ry = start + si * 190
        draw.text((lx, ry + 40), subject, font=F(38, True), fill=C["text"])
        for gi, (gname, colname, vals) in enumerate(groups):
            col = rgb(colname)
            by = ry + gi * 46
            val = vals[si][1]
            draw.rounded_rectangle([bar_x, by, bar_x + bar_w, by + 28], radius=11, fill=C["track"])
            draw.rounded_rectangle([bar_x, by, bar_x + int(bar_w * val / maxv), by + 28], radius=11, fill=col)
            draw.text((bar_x + bar_w + 20, by - 4), str(val), font=F(32, True), fill=col)
    if foot:
        draw.text((110, 930), foot, font=F(26), fill=C["muted"])


def draw_progress(draw, img, scene, y):
    a = rgb(scene["accent"])
    spec = scene["vis"][1]
    lx, bw = 180, 900
    for i, (label, before, after) in enumerate(spec["rows"]):
        ry = y + 80 + i * 220
        draw.text((lx, ry), label, font=F(42, True), fill=C["text"])
        draw.text((lx + 300, ry + 4), f"{before:.1f} ->", font=F(40, True), fill=C["dim"])
        draw.rounded_rectangle([lx + 460, ry + 8, lx + 460 + bw, ry + 48], radius=14, fill=C["track"])
        draw.rounded_rectangle([lx + 460, ry + 8, lx + 460 + int(bw * before / 100), ry + 48], radius=14, fill=C["dim"])
        draw.rounded_rectangle([lx + 460, ry + 70, lx + 460 + bw, ry + 110], radius=14, fill=C["track"])
        draw.rounded_rectangle([lx + 460, ry + 70, lx + 460 + int(bw * after / 100), ry + 110], radius=14, fill=a)
        draw.text((lx + 460 + bw + 24, ry + 66), f"{after:.1f}", font=F(42, True), fill=a)
    if spec.get("foot"):
        draw.text((180, 930), spec["foot"], font=F(26), fill=C["muted"])


def draw_cards(draw, img, scene, y):
    items = scene["vis"][1]["items"]
    pw = (W - 240) // 3
    for i, (num, title, body, colname) in enumerate(items):
        x = 80 + i * (pw + 40)
        col = rgb(colname)
        draw.rounded_rectangle([x, y + 30, x + pw, y + 500], radius=28, fill=C["track"], outline=col, width=3)
        draw.text((x + 40, y + 60), num, font=F(64, True), fill=col)
        draw.text((x + 40, y + 160), title, font=F(46, True), fill=C["text"])
        if body:
            draw.text((x + 40, y + 240), body, font=F(30), fill=C["muted"])


def draw_quote(draw, img, scene, y):
    a = rgb(scene["accent"])
    spec = scene["vis"][1]
    draw.text((110, y - 30), "\u201c", font=F(180, True), fill=a)
    f, lines = fit(spec["text"], 54, 36, W - 320, 3, bold=True)
    ty = y + 150
    for line in lines:
        draw.text((180, ty), line, font=f, fill=C["text"])
        ty += int(f.size * 1.2)
    draw.text((184, ty + 40), "— " + spec["by"], font=F(32), fill=C["muted"])


def draw_title(draw, img, scene, y):
    a = rgb(scene["accent"])
    big = scene["vis"][1]["big"]
    draw.text((W - 120, y + 160), big, font=F(320, True), fill=(28, 40, 66), anchor="ra")
    draw.text((110, y + 200), scene.get("sub") or "", font=F(42, True), fill=a)


def draw_cta(draw, img, scene, y):
    a = rgb(scene["accent"])
    chips = scene["vis"][1]["chips"]
    x = 100
    for i, chip in enumerate(chips):
        f = F(36, True)
        w = int(draw.textlength(chip, font=f)) + 70
        col = [a, C["orange"], C["blue"], C["purple"]][i % 4]
        draw.rounded_rectangle([x, y + 90, x + w, y + 180], radius=24, fill=C["track"], outline=col, width=3)
        draw.text((x + 35, y + 112), chip, font=f, fill=col)
        x += w + 30


def draw_opening(draw, img, scene, y):
    """Title card: the actual YouTube title + the hook question."""
    a = rgb(scene["accent"])
    draw.text((100, 250), "JUDUL VIDEO & HOOK", font=F(26, True), fill=a)
    font, lines = fit(scene["headline"], 72, 44, W - 220, 3, bold=True)
    ty = 310
    for line in lines:
        draw.text((100, ty), line, font=font, fill=C["text"])
        ty += int(font.size * 1.12)
    draw.rounded_rectangle([100, ty + 24, 440, ty + 34], radius=5, fill=a)
    if scene.get("sub"):
        sf, slines = fit(scene["sub"], 40, 28, W - 280, 3, bold=False)
        ty += 80
        for line in slines:
            draw.text((105, ty), line, font=sf, fill=C["muted"])
            ty += int(sf.size * 1.2)


def render_slide(scene, idx, total, path):
    img = background(scene["accent"])
    d = ImageDraw.Draw(img)
    draw_header(d, scene, idx, total)
    typ = scene["vis"][0]
    if typ == "opening":
        draw_opening(d, img, scene, 0)
        img.save(path)
        return
    y = draw_headline(d, scene)
    fn = {"hook": draw_hook, "bullets": draw_bullets, "split": draw_split,
          "stat": draw_stat, "card": draw_card, "chart": draw_chart,
          "progress": draw_progress, "cards": draw_cards, "quote": draw_quote,
          "title": draw_title, "cta": draw_cta}[typ]
    fn(d, img, scene, y)
    img.save(path)


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------
async def synth_all():
    import edge_tts
    durations = []
    for i, scene in enumerate(SCENES, 1):
        audio = AUDIO_DIR / f"audio_{i:03d}.mp3"
        if not audio.exists():
            comm = edge_tts.Communicate(scene["text"], VOICE, rate="+2%")
            with open(audio, "wb") as f:
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
        durations.append(probe_duration(audio))
        print(f"  TTS {i:02d}/{len(SCENES)}  {durations[-1]:5.1f}s  {scene['headline'].splitlines()[0]}", flush=True)
    return durations


# ---------------------------------------------------------------------------
# Background music (seamless crossfaded loop)
# ---------------------------------------------------------------------------
def prepare_music_loop():
    """Create a sample-exact seamless loop: body + crossfade(tail, head)."""
    import array
    import wave
    if MUSIC is None or LOOP.exists():
        return
    raw = subprocess.run(
        [FFMPEG, "-v", "error", "-i", str(MUSIC), "-f", "s16le",
         "-acodec", "pcm_s16le", "-ar", "48000", "-ac", "2", "pipe:1"],
        capture_output=True).stdout
    samples = array.array("h")
    samples.frombytes(raw[:len(raw) // 4 * 4])
    frames = len(samples) // 2
    x = 4 * 48000  # 4 second crossfade
    body = samples[2 * x:2 * (frames - x)]
    seam = array.array("h", [0]) * (2 * x)
    for i in range(x):
        w = i / (x - 1)
        w2 = 1.0 - w
        for ch in range(2):
            tail_v = samples[2 * (frames - x + i) + ch]
            head_v = samples[2 * i + ch]
            seam[2 * i + ch] = int(tail_v * w2 + head_v * w)
    loop = body + seam
    with wave.open(str(LOOP), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        wav.writeframes(loop.tobytes())
    print(f"Music loop: {frames/48000:.1f}s source -> {len(loop)//2/48000:.1f}s seamless loop", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SLIDE_DIR.mkdir(parents=True, exist_ok=True)
    total = len(SCENES)
    print(f"Rendering {total} slides...", flush=True)
    for i, scene in enumerate(SCENES, 1):
        render_slide(scene, i - 1, total, SLIDE_DIR / f"slide_{i:03d}.png")
    print("Synthesizing narration...", flush=True)
    durations = asyncio.run(synth_all())

    # silence between scenes
    silence = AUDIO_DIR / "silence.mp3"
    run([FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
         "-t", str(GAP), "-c:a", "libmp3lame", "-b:a", "48k", str(silence)])

    alist = WORK / "audio_list.txt"
    with open(alist, "w") as f:
        for i in range(1, total + 1):
            f.write(f"file '{AUDIO_DIR / f'audio_{i:03d}.mp3'}'\n")
            if i < total:
                f.write(f"file '{silence}'\n")

    ilist = WORK / "image_list.txt"
    with open(ilist, "w") as f:
        for i in range(1, total + 1):
            f.write(f"file '{SLIDE_DIR / f'slide_{i:03d}.png'}'\n")
            f.write(f"duration {durations[i-1] + (GAP if i < total else 0.04):.3f}\n")
        f.write(f"file '{SLIDE_DIR / f'slide_{total:03d}.png'}'\n")

    total_dur = sum(durations) + GAP * (total - 1)
    use_music = MUSIC is not None
    if use_music:
        print("Preparing music loop...", flush=True)
        prepare_music_loop()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    print("Assembling MP4...", flush=True)
    cmd = [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(alist)]
    if use_music:
        cmd += ["-stream_loop", "-1", "-i", str(LOOP)]
    cmd += ["-f", "concat", "-safe", "0", "-i", str(ilist)]
    if use_music:
        fc = (
            "[0:a]aresample=48000[narr];"
            f"[1:a]atrim=0:{total_dur:.3f},asetpts=N/SR/TB,volume=0.16[music];"
            "[music][narr]sidechaincompress=threshold=0.012:ratio=6:attack=20:release=350[ducked];"
            "[narr][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[out]"
        )
        cmd += ["-filter_complex", fc, "-map", "2:v", "-map", "[out]",
                "-t", f"{total_dur:.3f}"]
    else:
        cmd += ["-map", "0:a", "-map", "1:v"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-r", "25",
            "-c:a", "aac", "-b:a", "192k", str(OUT)]
    r = run(cmd)
    if r.returncode != 0:
        print(r.stderr[-3000:])
        raise SystemExit(1)
    print(f"DONE: {OUT}  ({OUT.stat().st_size/1024/1024:.1f} MB)", flush=True)
    print(f"Duration: {probe_duration(OUT):.1f}s | no subtitles | music: {"on" if use_music else "off"}", flush=True)


if __name__ == "__main__":
    main()
