#!/usr/bin/env python3
"""Build a narrated explainer MP4 from naskah-youtube-pendidikan.md.

Pipeline: Edge-TTS (id-ID) -> Pillow slides -> ffmpeg concat.
Inspired by open-source script-to-video pipelines (faceless-video-pipeline,
Automated-Explainer-Video-Generator) but tailored for Indonesian content.
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
# Source sentences (verbatim from the naskah)
# ---------------------------------------------------------------------------
SECTIONS = [
    [  # 0 INTRO
        "Belakangan ini, dunia pendidikan Indonesia kembali dihangatkan oleh perdebatan yang membuat gelisah banyak pihak: apakah penjurusan kaku IPA, IPS, dan Bahasa di SMA perlu dikembalikan seperti dulu?",
        "Di satu sisi, banyak siswa dan orang tua merasa kebingungan saat menentukan mata pelajaran pilihan di Kurikulum Merdeka, ditambah sekolah yang pusing mengurus jadwal kelas.",
        "Di sisi lain, mengembalikan penjurusan kaku berisiko membuat kita melangkah mundur ke era pengkotakan siswa.",
        "Lantas, mengapa kegelisahan ini muncul?",
        "Bagaimana data PISA memetakan kemampuan siswa kita dibanding Singapura dan Vietnam?",
        "Dan apa solusi kompromi yang bisa menyelesaikan masalah operasional sekolah?",
        "Mari kita bedah data dan faktanya!",
    ],
    [  # 1 BAB 1
        "Secara resmi, Kemendikbudristek menghapuskan penjurusan kaku IPA, IPS, dan Bahasa melalui Kepmendikbudristek Nomor 56 Tahun 2022.",
        "Tujuannya mulia: memberikan kebebasan bagi siswa untuk memilih kombinasi mata pelajaran sesuai minat dan cita-cita karirnya.",
        "Namun, dalam praktik di lapangan, kebebasan tanpa batas ini menabrak dua tembok besar:",
        "Pertama, keterbatasan operasional sekolah.",
        "Ketika setiap siswa dalam satu angkatan memiliki kombinasi pilihan mata pelajaran yang berbeda-beda, sekolah harus mengelola puluhan variasi jadwal individu atau moving class.",
        "Hal ini berbenturan langsung dengan keterbatasan jumlah ruang kelas paralel serta alokasi jam mengajar harian guru.",
        "Kedua, ketidakpastian rute perguruan tinggi.",
        "Tanpa arahan yang terstruktur, siswa dan orang tua khawatir kombinasi mata pelajaran pilihan yang diambil di kelas 11 dan 12 justru tidak linier dengan kualifikasi pendaftaran jalur Seleksi Nasional Berdasarkan Prestasi (SNBP) maupun SNBT di perguruan tinggi negeri.",
    ],
    [  # 2 BAB 2
        "Apakah mengembalikan Ujian Nasional dan penjurusan kaku otomatis menyelesaikan masalah?",
        "Mari kita lihat data capaian internasional.",
        "Berdasarkan hasil PISA 2022 yang dirilis OECD, skor literasi membaca Indonesia berada pada angka 359, matematika 366, dan sains 383.",
        "Meskipun skor numerik mengalami penurunan akibat dampak pandemi, peringkat internasional Indonesia justru naik 5 hingga 6 posisi karena penurunan skor rerata global jauh lebih tajam.",
        "Direktur Pendidikan OECD, Andreas Schleicher, bahkan memuji daya tahan sistem pendidikan Indonesia selama pandemi.",
        "Namun, tantangan nyata terlihat jika kita membandingkan dengan negara tetangga.",
        "Vietnam pada PISA 2022 mencatatkan skor sains 472, matematika 469, dan membaca 462.",
        "Bahkan pada PISA 2018, skor sains Vietnam sempat menembus 543 poin.",
        "Sementara itu, Singapura kokoh berada di peringkat pertama dunia dengan skor sains 560, matematika 563, dan membaca 535.",
        "Data Harmonized Learning Outcomes dari Bank Dunia mempertegas selisih ini, di mana skor Indonesia berada di angka 383 sementara Vietnam mencapai 485.",
        "Riset ilmiah menunjukkan bahwa kunci peningkatan mutu bukanlah ujian hafalan kaku.",
        "Studi lembaga riset INOVASI membuktikan bahwa sekolah yang menerapkan penyederhanaan kurikulum berbasis materi esensial mengalami pemulihan hasil belajar dua hingga tiga bulan lebih cepat pasca-pandemi.",
        "Pada sekolah dasar, rerata skor literasi meningkat dari 58,2 menjadi 74,3 dan numerasi dari 54,6 menjadi 71,8 setelah satu tahun implementasi kurikulum berfokus materi esensial.",
    ],
    [  # 3 BAB 3
        "Guna menjembatani dilema antara kebebasan siswa dan keterbatasan fasilitas sekolah, banyak tim pengembang kurikulum SMA di Indonesia mengambil solusi kompromi jalan tengah: menyederhanakan pilihan mata pelajaran menjadi 3 Paket Menu Terarah:",
        "Paket pertama adalah Paket STEM (Science, Technology, Engineering, & Mathematics).",
        "Paket ini menggabungkan Fisika, Kimia, Biologi, Matematika Lanjut, dan Informatika untuk menyiapkan siswa ke jurusan Teknik, Kedokteran, dan Data Science.",
        "Istilah STEM ini pertama kali dicetuskan secara resmi oleh Dr. Judith Ramaley di National Science Foundation Amerika Serikat pada tahun 2001.",
        "Paket kedua adalah Paket Sosio-Teknologi.",
        "Paket hybrid ini memadukan ilmu komputasi dan matematika dengan Ekonomi serta Sosiologi.",
        "Paket ini menjawab kebutuhan bidang Fintech, Business Analytics, dan Digital Marketing.",
        "Akar konsep Sosio-Teknis ini berasal dari riset klasik Eric Trist dan Ken Bamforth di Tavistock Institute pada tahun 1951.",
        "Paket ketiga adalah Paket Humaniora, Sosial, & Budaya.",
        "Berfokus pada Sosiologi, Geografi, Antropologi, dan Bahasa Lanjut untuk rute Hukum, Hubungan Internasional, dan Komunikasi.",
        "Konsep ini berakar dari tradisi filsafat studia humanitatis sejak zaman Cicero dan era Renaisans.",
        "Dengan mengelompokkan pilihan ke dalam 3 paket terarah ini, sekolah dapat menghemat penggunaan ruang kelas dan mengatur jam mengajar guru secara efisien, sementara siswa mendapatkan kepastian rute menuju perguruan tinggi.",
    ],
    [  # 4 BAB 4
        "Bagaimana dengan jam sekolah dan sistem di negara tetangga?",
        "Di Singapura, sekolah menerapkan 5 hari sekolah (Senin sampai Jumat) dengan jam masuk paling awal pukul 07.30 pagi.",
        "Durasi belajar SD sekitar 5 jam dan SMP/SMA 6 jam per hari.",
        "Namun, siswa sekolah menengah di Singapura memiliki kegiatan ekstrakurikuler wajib atau CCA yang membuat mereka sering berada di sekolah hingga pukul 17.00 sore.",
        "Di tingkat prapengurusan tinggi (Junior College), Singapura tidak membagi siswa ke jurusan IPA/IPS kaku, melainkan menggunakan sistem kedalaman subjek H1, H2, dan H3.",
        "Yang menarik, Singapura menerapkan aturan contrasting subject: siswa yang mengambil mayoritas subjek Sains wajib mengambil minimal satu subjek dari rumpun Humaniora atau Ekonomi (dan sebaliknya).",
        "Hal ini memastikan lulusan memiliki keseimbangan logika sains dan pemahaman sosial.",
        "Di Indonesia, kebijakan hari sekolah sangat dinamis.",
        "Di Jawa Tengah, jenjang SMA/SMK Negeri umumnya menerapkan 5 hari sekolah.",
        "Namun, untuk jenjang SD dan SMP di Kota Salatiga, Pemerintah Kota menetapkan kembali sistem 6 hari sekolah mulai tahun 2026.",
        "Langkah ini diambil agar jam belajar harian siswa selesai lebih awal di siang hari, sehingga siswa dapat mengikuti kegiatan pendidikan karakter sore seperti TPQ atau Madrasah Diniyah sekaligus mengurangi penggunaan gawai pada hari Sabtu.",
    ],
    [  # 5 OUTRO
        "Kesimpulannya, daripada kita terjebak dalam perdebatan ekstrem antara kembali ke penjurusan kaku IPA/IPS lama atau bebas tanpa aturan yang membingungkan, penerapan 3 Paket Pilihan Terarah adalah langkah kompromi paling rasional bagi SMA di Indonesia saat ini.",
        "Langkah ini menjaga semangat Kurikulum Merdeka dalam mengasah nalar kritis, sekaligus menyelesaikan hambatan nyata operasional sekolah di lapangan.",
        "Bagaimana dengan sekolah kalian?",
        "Apakah tempat kalian belajar sudah menerapkan sistem paket terarah, atau masih kebingungan mengatur jadwal?",
        "Dan menurut kalian, lebih efektif 5 hari atau 6 hari sekolah?",
        "Tuliskan pendapat dan pengalaman kalian di kolom komentar!",
        "Jangan lupa klik like, share, dan subscribe agar tidak ketinggalan pembahasan edukasi berbasis data berikutnya.",
        "Sampai jumpa di video selanjutnya!",
    ],
]


def S(sec, sents, chapter, title, headline, vis, sub=None, accent="teal"):
    text = " ".join(SECTIONS[sec][i] for i in sents)
    return dict(sec=sec, text=text, chapter=chapter, title=title,
                headline=headline, sub=sub, accent=accent, vis=vis)


SCENES = [
    S(0, [0], "INTRO", "Kegelisahan Penjurusan SMA", "IPA, IPS & BAHASA\nDIKEMBALIKAN?",
      ("hook", {"chips": ["IPA", "IPS", "BAHASA"]}), "Kurikulum Merdeka dalam dilema"),
    S(0, [1], "INTRO", "Kegelisahan Penjurusan SMA", "SISWA BINGUNG,\nSEKOLAH PUSING",
      ("split", {"items": [("SISWA & ORANG TUA", "Bingung memilih\nkombinasi mapel"),
                           ("SEKOLAH", "Pusing mengatur\njadwal kelas")]}), accent="orange"),
    S(0, [2], "INTRO", "Kegelisahan Penjurusan SMA", "RISIKO:\nPENGKOTAKAN SISWA",
      ("card", {"tag": "DI SISI LAIN", "title": "Langkah Mundur?",
                "bullets": ["Penjurusan kaku mengembalikan era pengkotakan siswa"]}), accent="red"),
    S(0, [3, 4, 5, 6], "INTRO", "Kegelisahan Penjurusan SMA", "3 PERTANYAAN\nBESAR",
      ("bullets", {"items": ["Mengapa kegelisahan ini muncul?",
                             "Bagaimana data PISA memetakan kita vs Singapura & Vietnam?",
                             "Apa solusi kompromi untuk sekolah?"]}),
      "Mari kita bedah data dan faktanya!"),

    S(1, [0, 1], "BAB 1", "Pengembalian IPA, IPS & Bahasa", "KEPMENDIKBUD\nNo. 56 / 2022",
      ("stat", {"big": "56", "label": "Tahun 2022 · Penjurusan kaku dihapus",
                "sub": "Kebebasan memilih kombinasi mapel sesuai minat & cita-cita"})),
    S(1, [2], "BAB 1", "Pengembalian IPA, IPS & Bahasa", "DUA TEMBOK\nBESAR",
      ("split", {"items": [("01", "Keterbatasan operasional sekolah"),
                           ("02", "Ketidakpastian rute PTN")]}), accent="orange"),
    S(1, [3, 4], "BAB 1", "Pengembalian IPA, IPS & Bahasa", "PULUHAN JADWAL\nINDIVIDU",
      ("card", {"tag": "TEMBOK 1", "title": "Moving Class",
                "bullets": ["Setiap siswa punya kombinasi mapel berbeda",
                            "Sekolah kelola puluhan jadwal individu"]}), accent="orange"),
    S(1, [5], "BAB 1", "Pengembalian IPA, IPS & Bahasa", "SUMBER DAYA\nTERBATAS",
      ("split", {"items": [("RUANG", "Jumlah ruang kelas\nparalel terbatas"),
                           ("WAKTU", "Alokasi jam mengajar\nharian guru terbatas")]}), accent="orange"),
    S(1, [6, 7], "BAB 1", "Pengembalian IPA, IPS & Bahasa", "RUTE PTN\nTAK PASTI",
      ("card", {"tag": "TEMBOK 2", "title": "SNBP / SNBT",
                "bullets": ["Mapel kelas 11–12 belum tentu linier",
                            "Siswa & orang tua khawatir"],
                "foot": "Tanpa arahan yang terstruktur"}), accent="orange"),

    S(2, [0, 1], "BAB 2", "Data PISA & INOVASI", "APAKAH UN, IPA, IPS & BAHASA\nMEMBERESKAN MASALAH?",
      ("title", {"big": "?"}), "Mari kita lihat data capaian internasional", accent="blue"),
    S(2, [2], "BAB 2", "Data PISA & INOVASI", "PISA 2022:\nINDONESIA",
      ("chart", {"groups": [("Indonesia", "teal", [("Membaca", 359), ("Matematika", 366), ("Sains", 383)])],
                 "foot": "Sumber: OECD, PISA 2022"}), accent="teal"),
    S(2, [3], "BAB 2", "Data PISA & INOVASI", "PERINGKAT NAIK\n5–6 POSISI",
      ("stat", {"big": "+5–6", "label": "posisi di peringkat internasional",
                "sub": "Rerata skor global turun lebih tajam akibat pandemi"}), accent="teal"),
    S(2, [4], "BAB 2", "Data PISA & INOVASI", "DAYA TAHAN SISTEM\nPENDIDIKAN",
      ("quote", {"text": "Daya tahan sistem pendidikan Indonesia selama pandemi.",
                 "by": "Andreas Schleicher · Direktur Pendidikan OECD"}), accent="teal"),
    S(2, [5, 6, 7], "BAB 2", "Data PISA & INOVASI", "BANDINGKAN DENGAN\nNEGARA TETANGGA",
      ("chart", {"groups": [("Indonesia", "teal", [("Membaca", 359), ("Matematika", 366), ("Sains", 383)]),
                            ("Vietnam", "orange", [("Membaca", 462), ("Matematika", 469), ("Sains", 472)])],
                 "foot": "Catatan: skor sains Vietnam PISA 2018 menembus 543 poin"}), accent="orange"),
    S(2, [8, 9], "BAB 2", "Data PISA & INOVASI", "SINGAPURA KOKOH\nDI PERINGKAT #1",
      ("chart", {"groups": [("Indonesia", "teal", [("Membaca", 359), ("Matematika", 366), ("Sains", 383)]),
                            ("Vietnam", "orange", [("Membaca", 462), ("Matematika", 469), ("Sains", 472)]),
                            ("Singapura", "blue", [("Membaca", 535), ("Matematika", 563), ("Sains", 560)])],
                 "foot": "Harmonized Learning Outcomes (Bank Dunia): Indonesia 383 · Vietnam 485"}), accent="blue"),
    S(2, [10, 11], "BAB 2", "Data PISA & INOVASI", "KUNCINYA BUKAN\nUJIAN HAFALAN",
      ("card", {"tag": "TEMUAN INOVASI", "title": "Materi Esensial",
                "bullets": ["Pemulihan hasil belajar 2–3 bulan lebih cepat",
                            "Penyederhanaan kurikulum pasca-pandemi"],
                "foot": "Riset lembaga INOVASI"}), accent="purple"),
    S(2, [12], "BAB 2", "Data PISA & INOVASI", "LITERASI & NUMERASI\nSD MENINGKAT",
      ("progress", {"rows": [("Literasi", 58.2, 74.3), ("Numerasi", 54.6, 71.8)],
                    "foot": "Setelah 1 tahun kurikulum berfokus materi esensial"}), accent="purple"),

    S(3, [0], "BAB 3", "Solusi Kompromi", "3 PAKET PILIHAN\nTERARAH",
      ("cards", {"items": [("01", "STEM", "Sains & Teknologi", "blue"),
                           ("02", "Sosio-Teknologi", "Komputasi + Ekonomi", "orange"),
                           ("03", "Humaniora", "Sosial & Budaya", "purple")]}),
      "Jalan tengah: kebebasan siswa + efisiensi sekolah"),
    S(3, [1, 2], "BAB 3", "Solusi Kompromi", "PAKET STEM",
      ("card", {"tag": "PAKET 01", "title": "STEM",
                "bullets": ["Fisika · Kimia · Biologi", "Matematika Lanjut · Informatika",
                            "Teknik · Kedokteran · Data Science"],
                "foot": "Science · Technology · Engineering · Mathematics"}),
      "Science · Technology · Engineering · Mathematics", accent="blue"),
    S(3, [3], "BAB 3", "Solusi Kompromi", "RAMALEY · NSF · 2001",
      ("stat", {"big": "2001", "label": "Istilah STEM dicetuskan resmi",
                "sub": "Dr. Judith Ramaley · National Science Foundation, AS"}), accent="blue"),
    S(3, [4, 5, 6], "BAB 3", "Solusi Kompromi", "PAKET SOSIO-\nTEKNOLOGI",
      ("card", {"tag": "PAKET 02", "title": "Sosio-Teknologi",
                "bullets": ["Komputasi + matematika", "Ekonomi + Sosiologi",
                            "Fintech · Business Analytics · Digital Marketing"],
                "foot": "Model hybrid"}), accent="orange"),
    S(3, [7], "BAB 3", "Solusi Kompromi", "TRIST & BAMFORTH\n· 1951",
      ("stat", {"big": "1951", "label": "Akar konsep Sosio-Teknis",
                "sub": "Eric Trist & Ken Bamforth · Tavistock Institute"}), accent="orange"),
    S(3, [8, 9], "BAB 3", "Solusi Kompromi", "PAKET HUMANIORA,\nSOSIAL & BUDAYA",
      ("card", {"tag": "PAKET 03", "title": "Humaniora",
                "bullets": ["Sosiologi · Geografi · Antropologi", "Bahasa Lanjut",
                            "Hukum · Hubungan Internasional · Komunikasi"],
                "foot": "Tradisi studia humanitatis sejak Cicero"}), accent="purple"),
    S(3, [10, 11], "BAB 3", "Solusi Kompromi", "EFISIEN +\nKEPASTIAN RUTE",
      ("split", {"items": [("SEKOLAH", "Hemat ruang kelas\n& jam mengajar guru"),
                           ("SISWA", "Rute pasti menuju\nperguruan tinggi")]}), accent="teal"),

    S(4, [0], "BAB 4", "Singapura & Jawa Tengah", "BAGAIMANA DENGAN\nJAM SEKOLAH?",
      ("title", {"big": "?"}), "Singapura vs Indonesia", accent="blue"),
    S(4, [1, 2], "BAB 4", "Singapura & Jawa Tengah", "SINGAPURA:\n5 HARI SEKOLAH",
      ("card", {"tag": "SINGAPURA", "title": "Jadwal Belajar",
                "bullets": ["Senin–Jumat, masuk dari pukul 07.30",
                            "SD ±5 jam · SMP/SMA ±6 jam per hari"]}), accent="blue"),
    S(4, [3], "BAB 4", "Singapura & Jawa Tengah", "CCA SAMPAI\nPUKUL 17.00",
      ("stat", {"big": "17.00", "label": "Ekstrakurikuler wajib (CCA)",
                "sub": "Siswa menengah sering di sekolah sampai sore"}), accent="blue"),
    S(4, [4], "BAB 4", "Singapura & Jawa Tengah", "H1 · H2 · H3",
      ("cards", {"items": [("H1", "Kedalaman dasar", "", "blue"),
                           ("H2", "Kedalaman utama", "", "teal"),
                           ("H3", "Kedalaman lanjut", "", "purple")]}),
      "Junior College: tanpa jurusan IPA/IPS kaku", accent="blue"),
    S(4, [5], "BAB 4", "Singapura & Jawa Tengah", "CONTRASTING\nSUBJECT",
      ("split", {"items": [("MAYORITAS SAINS", "Wajib ambil minimal 1 mapel\nHumaniora atau Ekonomi"),
                           ("MAYORITAS HUMANIORA", "Wajib ambil minimal 1 mapel\nSains (dan sebaliknya)")]}), accent="blue"),
    S(4, [6], "BAB 4", "Singapura & Jawa Tengah", "SEIMBANG: LOGIKA\n+ PEMAHAMAN SOSIAL",
      ("bullets", {"items": ["Nalar sains yang tajam", "Pemahaman sosial yang luas"]}), accent="teal"),
    S(4, [7, 8], "BAB 4", "Singapura & Jawa Tengah", "JAWA TENGAH:\n5 HARI",
      ("stat", {"big": "5", "label": "hari sekolah SMA/SMK Negeri",
                "sub": "Kebijakan Pemprov Jawa Tengah"}), accent="teal"),
    S(4, [9], "BAB 4", "Singapura & Jawa Tengah", "SALATIGA:\n6 HARI (2026)",
      ("stat", {"big": "6", "label": "hari sekolah SD/SMP",
                "sub": "Kebijakan Pemkot Salatiga mulai 2026"}), accent="orange"),
    S(4, [10], "BAB 4", "Singapura & Jawa Tengah", "MADIN/TPQ SORE\n+ BATASI GAWAI",
      ("bullets", {"items": ["Jam belajar selesai lebih awal di siang hari",
                             "Kegiatan karakter sore: TPQ / Madrasah Diniyah",
                             "Kurangi penggunaan gawai di hari Sabtu"]}), accent="orange"),

    S(5, [0], "OUTRO", "Kesimpulan", "3 PAKET = JALAN TENGAH\nPALING RASIONAL",
      ("bullets", {"items": ["Bukan kembali ke IPA, IPS & Bahasa kaku", "Bukan bebas tanpa aturan",
                             "Solusi kompromi untuk SMA Indonesia"]}), accent="teal"),
    S(5, [1], "OUTRO", "Kesimpulan", "NALAR KRITIS +\nOPERASIONAL",
      ("split", {"items": [("KURIKULUM MERDEKA", "Asah nalar kritis siswa"),
                           ("PRAKTIK SEKOLAH", "Selesaikan hambatan operasional")]}), accent="teal"),
    S(5, [2, 3, 4], "OUTRO", "Kesimpulan", "5 ATAU 6 HARI?\nPAKET ATAU BEBAS?",
      ("cta", {"chips": ["5 HARI", "6 HARI", "3 PAKET", "BEBAS"]}), accent="orange"),
    S(5, [5, 6, 7], "OUTRO", "Kesimpulan", "SAMPAI JUMPA DI\nVIDEO SELANJUTNYA!",
      ("cta", {"chips": ["KOMENTAR", "LIKE", "SHARE", "SUBSCRIBE"]}), accent="teal"),
]


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
    draw.text((72, H - 54), "DILEMA PENJURUSAN SMA · Video Edukasi", font=F(22), fill=C["dim"])


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


def render_slide(scene, idx, total, path):
    img = background(scene["accent"])
    d = ImageDraw.Draw(img)
    draw_header(d, scene, idx, total)
    y = draw_headline(d, scene)
    typ = scene["vis"][0]
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
