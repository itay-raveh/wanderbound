# Polarsteps Album Generator

Generate beautiful HTML photo albums from Polarsteps trip data, matching the design of the official Polarsteps online editor.

## Features

- Generate a single HTML page with all steps in a column (A4 landscape format)
- Automatic image selection (prefers 5:4 horizontal, falls back to portrait)
- External API integration for altitude data, country maps, and flags
- RTL support for Hebrew descriptions
- Step range filtering (e.g., generate only steps 99-110)
- Optional PDF generation using Playwright
- Beautiful design matching the official Polarsteps editor

## Installation

1. Ensure you have Python 3.13+ and a virtual environment activated
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. (Optional) For PDF generation, install Playwright browsers:
   ```bash
   playwright install chromium
   ```

## Usage

Basic usage:
```bash
python main.py --steps 99-110
```

This will:
- Load trip data from `trip/trip.json`
- Generate a single HTML file (`album.html`) with all steps
- Output to `output/` directory

### Command Line Options

- `--trip-dir PATH`: Directory containing trip.json and step folders (default: `trip`)
- `--steps RANGE`: Step range to include, e.g., `"99-110"` or `"99"` (default: all steps)
- `--output PATH`: Output directory for HTML/PDF files (default: `output`)
- `--pdf`: Generate PDF file using Playwright (requires `playwright install chromium`)

### Examples

Generate steps 1-10:
```bash
python main.py --steps 1-10
```

Generate a single step:
```bash
python main.py --steps 99
```

Generate all steps:
```bash
python main.py
```

Generate with PDF output:
```bash
python main.py --steps 99-110 --pdf
```

Custom output directory:
```bash
python main.py --steps 99-110 --output my_album
```

## Viewing the Album

1. Open `output/album.html` (or your custom output directory) in your web browser
2. Scroll through all steps in a single page
3. Use `--pdf` flag to generate a PDF automatically, or use your browser's "Print to PDF" feature

## Project Structure

```
.
├── album_generator/
│   ├── __init__.py
│   ├── main.py          # CLI entry point
│   ├── models.py        # Pydantic data models
│   ├── data_loader.py   # Load and parse trip data
│   ├── image_selector.py # Select appropriate images
│   ├── apis.py          # External API integrations
│   ├── html_generator.py # Generate HTML pages
│   ├── templates/       # Jinja2 templates
│   │   └── album.html
│   └── static/          # Static assets
│       └── Renner.ttf   # Font file for titles
├── trip/                # Your trip data directory
│   ├── trip.json        # Trip metadata
│   └── [step_folders]/  # Step photo directories
├── main.py              # Entry point
└── requirements.txt     # Python dependencies
```

## Notes

- Images are embedded as base64 data URIs in the HTML, so files may be large
- Altitude data, country maps, and flags are fetched from external APIs and cached locally in `~/.polarsteps_album_cache/`
- The first image with 5:4 horizontal aspect ratio is selected, or the first portrait image if none found
- Hebrew descriptions are automatically detected and rendered RTL
- Country maps and flags are fetched from public APIs (flagcdn.com, etc.)
- The Renner font is bundled with the package and used automatically
