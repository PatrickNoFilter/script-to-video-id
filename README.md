# script-to-video-id

Pipeline sederhana untuk mengubah naskah video edukasi berbahasa Indonesia menjadi MP4 naratif: **naskah → 37 scene → Edge-TTS → slide Pillow → ffmpeg**. Cocok untuk video YouTube bertema edukasi/kebijakan dengan grafik data, kartu poin, dan perbandingan.

Proyek ini adalah versi open-source dari pipeline yang dipakai untuk video *"Dilema Penjurusan SMA: IPA, IPS & Bahasa Kembali?"*.

## Fitur

- Narasi bahasa Indonesia gratis tanpa API key via [Edge-TTS](https://github.com/rany2/edge-tts) (`id-ID-GadisNeural` / `id-ID-ArdiNeural`).
- Slide 1920×1080 digambar dengan Pillow: judul, grafik batang PISA, kartu paket, panel perbandingan, CTA.
- Durasi slide mengikuti durasi narasi per scene (otentik, tidak dipaksa).
- Background music opsional dengan **loop crossfade sample-exact** (tidak terdengar sambungannya) + auto-duck saat narasi berbicara.
- Tanpa subtitle secara default; fokus ke teks di layar yang sudah ada di slide.
- Output H.264/AAC MP4, 25 fps.

## Cara kerja

```
SCENES (di build_video.py)
  ├─> Edge-TTS       -> audio per scene (.mp3)
  ├─> Pillow         -> slide per scene (.png)
  └─> ffmpeg         -> concat + mix musik -> output/video.mp4
```

## Instalasi

```bash
git clone https://github.com/PatrickNoFilter/script-to-video-id.git
cd script-to-video-id
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Butuh font Noto Sans di sistem (`/usr/share/fonts/truetype/noto/`). Di Debian/Ubuntu: `sudo apt install fonts-noto`.

## Pemakaian

```bash
python build_video.py
```

Output default: `output/video.mp4`.

### Opsi lewat environment variable

| Variable | Default | Fungsi |
| :--- | :--- | :--- |
| `VIDEO_OUT` | `output/video.mp4` | Path file MP4 hasil |
| `VIDEO_WORK` | `.build/` | Folder sementara (audio + slide) |
| `VIDEO_VOICE` | `id-ID-GadisNeural` | Suara Edge-TTS |
| `VIDEO_MUSIC` | *(kosong)* | Path lagu untuk di-loop jadi background music |

Contoh dengan musik:

```bash
VIDEO_MUSIC="/path/ke/lagu.m4a" VIDEO_OUT="output/video-dengan-musik.mp4" python build_video.py
```

Tanpa musik (default) tetap menghasilkan video dengan narasi saja.

## Audio: ducking & seamless loop

Dua hal yang terjadi otomatis saat `VIDEO_MUSIC` diisi:

### 1. Audio ducking (sidechain compression)

Saat narasi bersuara, musik diturunkan volumenya; saat narasi jeda, musik naik lagi. Efek ini disebut **audio ducking** atau **sidechain compression**. Narasi dipakai sebagai *sidechain* yang menekan musik.

Filter yang dipakai:

```text
sidechaincompress=threshold=0.012:ratio=6:attack=20:release=350
```

- `threshold` — ambang level narasi sebelum musik mulai ditekan.
- `ratio` — seberapa kuat musik ditekan (6:1).
- `attack` — 20 ms, kecepatan musik mengecil saat narasi masuk.
- `release` — 350 ms, kecepatan musik kembali naik setelah narasi jeda.

Musik juga sudah diset `volume=0.16` sebelum di-duck, dan `amix` memakai `normalize=0` supaya level narasi tidak ikut turun.

### 2. Seamless music loop (crossfade sample-exact)

Lagu dipotong menjadi dua bagian:

```text
loop = lagu[4s : durasi-4s] + crossfade(lagu[durasi-4s : durasi], lagu[0 : 4s])
```

Empat detik akhir lagu di-crossfade dengan empat detik awalnya. Ujung loop berakhir tepat di sampel yang sama dengan awal loop, sehingga saat diulang dengan `-stream_loop -1` tidak terdengar "klik" atau jeda. Perhitungannya dilakukan per sampel PCM 16-bit 48 kHz di fungsi `prepare_music_loop()`, bukan sekadar `afade` bawaan ffmpeg.

## Kustomisasi

- **Teks & visual:** edit list `SCENES` di `build_video.py`. Tiap scene berisi `chapter`, `title`, `headline`, `sub`, `accent`, `vis`, dan kalimat narasi yang diambil dari `SECTIONS`.
- **Narasi:** ubah kalimat di `SECTIONS` (diambil verbatim dari naskah contoh di `examples/`).
- **Suara:** ganti `VIDEO_VOICE` atau `VOICE`. Lihat suara Indonesia: `edge-tts --list-voices | grep id-ID`.
- **Warna/tipografi:** ubah dictionary `C` dan fungsi `F()`.

## Struktur

```
.
├── build_video.py              # pipeline utama
├── requirements.txt
├── examples/
│   ├── naskah-contoh.md        # naskah sumber
│   └── youtube-metadata-contoh.txt  # judul, deskripsi, chapter, tag
└── output/                     # hasil MP4 (di-gitignore)
```

## Kredit

- [edge-tts](https://github.com/rany2/edge-tts) — TTS
- [Pillow](https://python-pillow.org/) — rendering slide
- [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) — binary ffmpeg
- Terinspirasi oleh `faceless-video-pipeline` dan `Automated-Explainer-Video-Generator`.

## Lisensi

MIT — lihat [LICENSE](LICENSE).
