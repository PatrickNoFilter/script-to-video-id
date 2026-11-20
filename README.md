# script-to-video-id

Pipeline generik untuk mengubah **naskah apa pun** (Markdown atau JSON) menjadi MP4 naratif berbahasa Indonesia: **naskah → parser scene → Edge-TTS → slide Pillow → ffmpeg**. Jumlah scene tidak di-hardcode—pipeline memotong narasi otomatis sesuai panjang yang Anda tentukan. Cocok untuk video YouTube edukasi, kebijakan, tutorial, atau penjelasan data.

Contoh yang disertakan adalah naskah video *"Dilema Penjurusan SMA: IPA, IPS & Bahasa Kembali?"*.

## Fitur

- Narasi bahasa Indonesia gratis tanpa API key via [Edge-TTS](https://github.com/rany2/edge-tts) (`id-ID-GadisNeural` / `id-ID-ArdiNeural`).
- Slide 1920×1080 digambar dengan Pillow: judul, grafik batang PISA, kartu paket, panel perbandingan, CTA.
- Durasi slide mengikuti durasi narasi per scene (otentik, tidak dipaksa).
- Background music opsional dengan **loop crossfade sample-exact** (tidak terdengar sambungannya) + auto-duck saat narasi berbicara.
- Tanpa subtitle secara default; fokus ke teks di layar yang sudah ada di slide.
- Output H.264/AAC MP4, 25 fps.

## Cara kerja

```
naskah (.md / .json)
  └─> naskah_parser.py   -> daftar scene (teks + judul + visual)
        ├─> Edge-TTS     -> audio per scene (.mp3)
        ├─> Pillow       -> slide per scene (.png)
        └─> ffmpeg       -> concat + ducking + loop musik -> MP4
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
# Pakai naskah contoh
python build_video.py

# Naskah Anda sendiri
python build_video.py --naskah /path/naskah-saya.md --output output/video-saya.mp4

# Naskah + musik + suara lain + scene lebih pendek
python build_video.py \
  --naskah /path/naskah-saya.md \
  --music /path/lagu.m4a \
  --voice id-ID-ArdiNeural \
  --words-per-scene 28 \
  --output output/video-saya.mp4
```

### Opsi CLI

| Opsi | Default | Fungsi |
| :--- | :--- | :--- |
| `--naskah` | `examples/naskah-contoh.md` | File `.md` atau `.json` |
| `--output` | `output/video.mp4` | Path MP4 hasil |
| `--voice` | `id-ID-GadisNeural` | Suara Edge-TTS |
| `--music` | *(kosong)* | Lagu background (di-loop otomatis) |
| `--words-per-scene` | `38` | Target kata per scene |

Env variable masih didukung sebagai fallback: `VIDEO_WORK` (folder sementara), dan nilai default untuk `VIDEO_OUT`, `VIDEO_VOICE`, `VIDEO_MUSIC`.

Tanpa `--music` tetap menghasilkan video dengan narasi saja.

## Format naskah

Parser membaca Markdown dengan struktur ini:

```markdown
### [00:00 – 01:00] BAB 1: Judul Bab

**Visual Cue**:
* *Text on Screen*: "JUDUL DI LAYAR"

**Voiceover (Narasi)**:
Kalimat narasi pertama. Kalimat narasi kedua. Kalimat narasi ketiga.

---
```

- Setiap `###` menjadi satu bab (`chapter` + `title`).
- Teks setelah `**Voiceover (Narasi)**:` dipotong menjadi beberapa scene menurut `--words-per-scene`, dengan batas kalimat yang dijaga.
- `*Text on Screen*` dipakai sebagai judul visual. Tanpa itu, judul diambil dari kalimat pertama.
- Naskah tanpa marker `Voiceover` juga tetap jalan: semua paragraf non-metadata dibaca sebagai narasi.

### Visual opsional (directive)

Taruh komentar HTML sebelum sebuah scene untuk mengontrol tampilannya. Komentar ke-*n* berlaku untuk scene ke-*n* dalam bab tersebut:

```markdown
<!-- scene: type=stat big=56 label="Tahun 2022" accent=orange -->
```

Jumlah directive dalam satu bab juga menentukan jumlah scene: kalau ada 3 directive, narasi bab itu dibagi jadi 3 scene. Jenis `type` yang didukung: `hook`, `bullets`, `split`, `stat`, `card`, `quote`, `cta`, `title`, `cards`, `progress`, `chart`. Contoh:

```markdown
<!-- scene: type=split items="RUANG::Jumlah kelas terbatas|WAKTU::Jam guru terbatas" -->
<!-- scene: type=chart subjects="Membaca,Matematika,Sains" groups="Indonesia:teal:359,366,383|Vietnam:orange:462,469,472" -->
<!-- scene: type=progress items="Literasi:58.2:74.3|Numerasi:54.6:71.8" -->
```

Tanpa directive, scene otomatis memakai `bullets` (atau `quote` untuk narasi satu kalimat).

### JSON scene list

Alternatifnya, berikan file JSON berisi array scene:

```json
[
  {
    "text": "Narasi scene ini.",
    "chapter": "BAB 1",
    "title": "Judul Bab",
    "headline": "JUDUL DI LAYAR",
    "accent": "teal",
    "vis": ["stat", {"big": "56", "label": "Tahun 2022", "sub": ""}]
  }
]
```

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

- **Teks & visual:** edit file naskah `.md`/`.json` Anda—tidak perlu menyentuh kode Python.
- **Aturan potong scene:** ubah `--words-per-scene` atau logika `chunk_text()` di `naskah_parser.py`.
- **Jenis visual baru:** tambahkan fungsi `draw_*` di `build_video.py` dan daftarkan di peta `fn` pada `render_slide()`, lalu dukung `type` tersebut di `visual_from_directive()`.
- **Suara:** ganti `--voice` / `VIDEO_VOICE`. Lihat suara Indonesia: `edge-tts --list-voices | grep id-ID`.
- **Warna/tipografi:** ubah dictionary `C` dan fungsi `F()` di `build_video.py`.

## Struktur

```
.
├── build_video.py              # renderer + assembler
├── naskah_parser.py            # parser naskah -> scene (markdown/JSON)
├── requirements.txt
├── examples/
│   ├── naskah-contoh.md        # naskah polos (auto scene)
│   ├── naskah-dengan-visual.md # contoh directive visual
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
