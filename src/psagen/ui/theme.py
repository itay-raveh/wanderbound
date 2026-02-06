"""Design system and theme configuration."""

# Color Palette (Polarsteps-inspired warm travel tones)
COLORS = {
    "bg_dark": "#0f0f1a",  # Deep navy background
    "bg_card": "#1a1a2e",  # Card background
    "bg_input": "#252540",  # Input background
    "accent": "#4a9eff",  # Primary blue accent
    "accent_hover": "#6bb3ff",  # Hover state
    "success": "#10b981",  # Green for success states
    "warning": "#f59e0b",  # Amber for warnings
    "text": "#e5e7eb",  # Primary text
    "text_muted": "#9ca3af",  # Secondary text
    "border": "#374151",  # Borders
}

# Typography
FONTS = "'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif"

# CSS Variables Injection
# Only contains :root variables to keep Python/CSS in sync
THEME_VARS = f"""
:root {{
    --bg-dark: {COLORS["bg_dark"]};
    --bg-card: {COLORS["bg_card"]};
    --bg-input: {COLORS["bg_input"]};
    --accent: {COLORS["accent"]};
    --accent-hover: {COLORS["accent_hover"]};
    --success: {COLORS["success"]};
    --text: {COLORS["text"]};
    --text-muted: {COLORS["text_muted"]};
    --border: {COLORS["border"]};
}}
"""
