# Daily Beltway — Instagram Graphics System

A professional, template-driven system for generating Instagram posts and Reels for the Daily Beltway political news brand. Renders are deterministic, brand-locked, and production-quality.

---

## Architecture

```
daily-beltway/
├── config/              Brand + template configs (YAML)
├── src/
│   ├── cli.py           CLI entrypoint (Click)
│   ├── renderer/        FFmpeg filtergraph + image/video renderers
│   ├── templates/       Config loader + validator
│   ├── exporter/        Dropbox API uploader + local package writer
│   └── utils/           Color, text escaping, slugs, font validation
├── assets/              Fonts, logos, gradient overlays, backgrounds
├── stories/             Story JSON input files
├── scripts/             One-time setup scripts
└── output/              Rendered output (READY_TO_REVIEW/)
```

**Rendering engine:** FFmpeg only. No Pillow in the production pipeline.
**Compositing:** Programmatic filtergraph builder — no raw string concatenation.
**Font failure:** System hard-exits if any required font file is missing.

---

## Server Setup (Ubuntu/Debian)

### 1. Install system dependencies

```bash
sudo apt update
sudo apt install -y ffmpeg python3 python3-pip git
```

### 2. Clone the project

```bash
git clone <your-repo-url> daily-beltway
cd daily-beltway
```

### 3. Install Python dependencies

```bash
pip3 install -r requirements.txt
```

### 4. Download fonts

Download the **Barlow** font family from Google Fonts:

```bash
mkdir -p assets/fonts
cd /tmp

# Barlow Condensed ExtraBold (headline)
wget "https://fonts.gstatic.com/s/barlowcondensed/v12/HTxwL3I-JCGChYJ8VI-L6OO_au7B4-Lz.ttf" \
  -O ~/daily-beltway/assets/fonts/BarlowCondensed-ExtraBold.ttf

# Barlow SemiBold (body)
wget "https://fonts.gstatic.com/s/barlow/v12/7cHqv4kjgoGqM7E_Ccs8yn4.ttf" \
  -O ~/daily-beltway/assets/fonts/Barlow-SemiBold.ttf

# Barlow Bold (labels)
wget "https://fonts.gstatic.com/s/barlow/v12/7cHqv4kjgoGqM7E_A-s8yn4.ttf" \
  -O ~/daily-beltway/assets/fonts/Barlow-Bold.ttf
```

> **Note:** Font URLs may change. If wget fails, download from [fonts.google.com/specimen/Barlow+Condensed](https://fonts.google.com/specimen/Barlow+Condensed) and [fonts.google.com/specimen/Barlow](https://fonts.google.com/specimen/Barlow), then place the TTF files in `assets/fonts/`.

### 5. Place the logo

```bash
# Copy the Daily Beltway logo to:
cp /path/to/daily_beltway_logo.png assets/logos/daily_beltway_logo.png
```

The logo must be a PNG with a transparent or white background. The renderer scales it to 15% of the canvas width (≈162px at 1080px wide).

### 6. Configure environment

```bash
cp .env.example .env
nano .env
```

Fill in:
- `DROPBOX_ACCESS_TOKEN` — from your Dropbox App (see Dropbox setup below)
- `DROPBOX_DEST_PATH` — destination folder in Dropbox (default: `/Daily Beltway/READY_TO_REVIEW`)

### 7. Generate gradient overlay assets

```bash
python3 scripts/generate_overlays.py
```

This creates the pre-baked gradient PNG overlays and the navy fallback background.

### 8. Validate configuration

```bash
python3 -m daily_beltway validate-config
```

All lines should show `[OK]`. Fix any `[FAIL]` items before rendering.

---

## Dropbox App Setup

1. Go to [dropbox.com/developers/apps](https://www.dropbox.com/developers/apps)
2. Click **Create app**
3. Choose **Scoped access** → **Full Dropbox**
4. Name your app (e.g. `daily-beltway-publisher`)
5. In the **Permissions** tab, enable:
   - `files.content.write`
   - `files.content.read`
6. In the **Settings** tab, scroll to **OAuth 2** → **Generated access token** → click **Generate**
7. Copy the token into your `.env` as `DROPBOX_ACCESS_TOKEN`

> Use a long-lived token for production. For automated server use, generate an offline token via the OAuth flow.

---

## Usage

### List available templates

```bash
python3 -m daily_beltway list-templates
```

### Generate a story package

```bash
python3 -m daily_beltway generate --story stories/sample_story.json
```

Output is written to `output/READY_TO_REVIEW/{date}_{slug}/` and uploaded to Dropbox if configured.

### Quick preview (no Dropbox upload)

```bash
python3 -m daily_beltway preview \
  --story stories/sample_story.json \
  --template breaking_news \
  --open
```

The `--open` flag opens the rendered JPEG in Preview.app (macOS) or default image viewer.

### Dry run (print FFmpeg command without rendering)

```bash
python3 -m daily_beltway generate \
  --story stories/sample_story.json \
  --dry-run
```

### Validate configs

```bash
python3 -m daily_beltway validate-config
```

---

## Story JSON Schema

Create a JSON file in `stories/` with:

```json
{
  "title": "Full story title (used for slug + caption fallback)",
  "short_headline": "HEADLINE FOR GRAPHIC (ALL CAPS RECOMMENDED)",
  "subheadline": "Supporting detail line (optional)",
  "caption": "Full Instagram caption text (optional, defaults to title)",
  "source_url": "https://...",
  "category": "breaking | politics | economy | opinion | world | culture",
  "image_path": "/absolute/path/to/image.jpg or null",
  "video_path": "/absolute/path/to/video.mp4 or null",
  "quote_text": "Quote text for quote_card template (required for quote_card)",
  "attribution": "— Speaker Name, Title (for quote cards)",
  "template_type": "breaking_news | engagement_bait | quote_card | reel_cover | carousel_slide | video_reel",
  "slide_number": 2,
  "total_slides": 5
}
```

**Required fields:** `title`, `short_headline`, `template_type`
**Required for `quote_card`:** `quote_text`
**Required for `video_reel`:** `video_path`

---

## Template Reference

| Template | Canvas | Format | Description |
|---|---|---|---|
| `breaking_news` | 1080×1080 | JPEG | Red BREAKING NEWS band, headline, subheadline |
| `engagement_bait` | 1080×1080 | JPEG | Bold question headline with YES/NO poll boxes |
| `quote_card` | 1080×1080 | JPEG | Red accent bar, centered quote, red attribution |
| `reel_cover` | 1080×1920 | JPEG | Vertical blur-pad, WATCH NOW band, headline |
| `carousel_slide` | 1080×1080 | JPEG | Like breaking news + slide number indicator |
| `video_reel` | 1080×1920 | MP4 | Blur-pad video, lower-third strip, subtitle burn-in |

---

## Output Package Structure

Each rendered story produces:

```
output/READY_TO_REVIEW/2026-04-08_senate-passes-budget-resolution/
├── post.jpg           Final rendered image (or reel.mp4 for video)
├── reel_cover.jpg     Cover frame extracted from video (video_reel only)
├── caption.txt        Ready-to-paste Instagram caption
├── manifest.json      Render metadata (template, timestamp, FFmpeg version)
└── internal_notes.txt Full FFmpeg command for debugging
```

---

## Running Tests

```bash
pytest tests/ -v
```

Tests cover: text escaping, filtergraph builder, slug generation, config validation.
No FFmpeg required to run tests (all tests are unit-level).

---

## Customizing Brand

All visual values are in `config/brand.yaml`:
- `colors` — hex values for navy, red, white
- `fonts` — paths to TTF files
- `logo` — size, position, padding
- `gradient` — overlay opacity and height
- `export` — JPEG quality, video CRF, codec settings

Per-template values are in `config/templates/{name}.yaml`.
Template values override brand defaults where both exist.

To change a headline font size for breaking news only:
```yaml
# config/templates/breaking_news.yaml
headline_box:
  font_size: 92  # override brand default
```

---

## Troubleshooting

**`[FONT ERROR] Required font 'headline_font' not found`**
→ Download Barlow fonts and place in `assets/fonts/`. See step 4 above.

**`[LOGO ERROR] Logo file not found`**
→ Place `daily_beltway_logo.png` in `assets/logos/`.

**`[FFMPEG NOT FOUND]`**
→ Install FFmpeg: `sudo apt install ffmpeg` or `brew install ffmpeg`.

**`Dropbox authentication failed`**
→ Regenerate your access token at dropbox.com/developers/apps.

**Output looks blurry**
→ Check that source image is at least 1080×1080px. The renderer uses `lanczos` scaling but cannot upscale low-res inputs without quality loss.
