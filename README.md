# Polarsteps Album Generator

Generate beautiful HTML photo albums from Polarsteps trip data, matching the design of the official Polarsteps online editor.

## Features

- Generate a single HTML page with all steps in a column (A4 landscape format)
- Intelligent automatic image selection with layout optimization
- External API integration for altitude data, country maps, flags, and weather
- RTL support for Hebrew descriptions
- Step range filtering (e.g., generate only steps 99-110)
- Optional PDF generation using Playwright
- Beautiful design matching the official Polarsteps editor
- Concurrent API fetching for improved performance
- Comprehensive caching system for external data

## Installation

1. Ensure you have Python 3.10+ installed
2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install the package and dependencies:

   ```bash
   pip install -e .
   ```

4. (Optional) For PDF generation, install Playwright browsers:

   ```bash
   playwright install chromium
   ```

## Usage

After installation, you can use the `polarsteps-album` command:

```bash
polarsteps-album --steps 99-110
```

Or use Python directly:

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
polarsteps-album --steps 1-10
```

Generate a single step:

```bash
polarsteps-album --steps 99
```

Generate all steps:

```bash
polarsteps-album
```

Generate with PDF output:

```bash
polarsteps-album --steps 99-110 --pdf
```

Custom output directory:

```bash
polarsteps-album --steps 99-110 --output my_album
```

## Viewing the Album

1. Open `output/album.html` (or your custom output directory) in your web browser
2. Scroll through all steps in a single page
3. Use `--pdf` flag to generate a PDF automatically, or use your browser's "Print to PDF" feature

## Project Structure

```text
.
├── src/                 # Main source code
│   ├── main.py          # CLI entry point
│   ├── cli.py           # Command-line argument parsing
│   ├── models.py        # Pydantic data models
│   ├── settings.py      # Application settings and configuration
│   ├── exceptions.py    # Custom exception classes
│   ├── logger.py        # Logging configuration
│   ├── types.py         # Type aliases and TypedDicts
│   ├── data_loader.py   # Load and parse trip data
│   ├── photo_processor.py # Photo processing logic
│   ├── image_selector.py # Image selection wrapper
│   ├── html_generator.py # HTML generation orchestrator
│   ├── template_renderer.py # Jinja2 template rendering
│   ├── apis/            # External API integrations
│   │   ├── altitude.py  # Altitude/elevation API
│   │   ├── flags.py     # Country flag API
│   │   ├── maps.py      # Country map API
│   │   ├── weather.py   # Weather API (sync)
│   │   ├── async_weather.py # Weather API (async)
│   │   ├── async_flags.py # Flag API (async)
│   │   ├── async_maps.py # Map API (async)
│   │   ├── helpers.py   # API helper functions
│   │   ├── async_helpers.py # Async API helpers
│   │   ├── cache.py     # Caching utilities
│   │   └── rate_limit.py # Rate limiting
│   ├── formatters/     # Data formatting utilities
│   │   ├── date.py      # Date formatting
│   │   ├── coordinates.py # Coordinate formatting
│   │   └── weather.py   # Weather condition formatting
│   ├── html/            # HTML generation modules
│   │   ├── asset_management.py # Asset copying
│   │   ├── step_data_preparation.py # Step data preparation
│   │   ├── batch_fetching.py # Batch API fetching
│   │   └── photo_pages.py # Photo page processing
│   ├── photo/           # Photo processing modules
│   │   ├── ratio.py     # Aspect ratio detection
│   │   ├── loader.py    # Photo loading and metadata
│   │   ├── cover.py     # Cover photo selection
│   │   ├── layout.py    # Layout detection
│   │   └── scorer.py    # Photo scoring and bin-packing
│   ├── output/          # Output generation
│   │   └── pdf_generator.py # PDF generation
│   ├── utils/           # Utility functions
│   │   ├── files.py     # File utilities
│   │   ├── paths.py     # Path utilities
│   │   ├── dates.py     # Date utilities
│   │   └── steps.py     # Step utilities
│   ├── templates/       # Jinja2 templates
│   │   └── album.html
│   └── static/          # Static assets
│       ├── css/         # CSS stylesheets
│       └── Renner.ttf   # Font file for titles
├── trip/                # Your trip data directory (gitignored)
│   ├── trip.json        # Trip metadata
│   └── [step_folders]/  # Step photo directories
├── main.py              # Top-level entry point
├── pyproject.toml       # Python package configuration and dependencies
├── LICENSE              # MIT License
└── README.md            # This file
```

## Configuration

The application uses Pydantic settings for configuration. Settings can be customized via environment variables or by modifying `src/settings.py`. Key settings include:

- API keys for external services (Visual Crossing weather API, etc.)
- File paths and directory names
- Photo selection preferences
- Layout and styling thresholds

## Caching

External API data (altitude, maps, flags, weather) is cached locally in `~/.polarsteps_album_cache/` to improve performance and reduce API calls. The cache persists between runs.

## Notes

- Images are embedded as base64 data URIs in the HTML, so files may be large
- Altitude data, country maps, flags, and weather are fetched from external APIs and cached locally
- Intelligent photo selection uses scoring algorithms to optimize layout coverage
- Hebrew descriptions are automatically detected and rendered RTL
- Country maps and flags are fetched from public APIs (flagcdn.com, etc.)
- The Renner font is bundled with the package and used automatically
- The project uses modern Python packaging with `pyproject.toml`
- All code follows strict type checking with mypy and comprehensive linting

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
