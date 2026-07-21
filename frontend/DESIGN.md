---
name: Wanderbound
description: A quiet print studio for turning Polarsteps trips into editable, print-ready albums.
colors:
  primary: "#0063D1"
  primary-deep: "#0558B8"
  binding-violet: "#2D254C"
  night-ink: "#1E1E2E"
  night-surface: "#252540"
  night-text: "#E5E7EB"
  cool-paper: "#F3F4F6"
  paper-white: "#FFFFFF"
  daylight-ink: "#1F2937"
  rule-line: "#D1D5DB"
  danger: "#DC2626"
typography:
  display:
    fontFamily: "Assistant, system-ui, -apple-system, sans-serif"
    fontSize: "3.75rem"
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Assistant, system-ui, -apple-system, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Assistant, system-ui, -apple-system, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Assistant, system-ui, -apple-system, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
    lineHeight: 1.3
  album-body:
    fontFamily: "Frank Ruhl Libre, Georgia, serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.45
rounded:
  xs: "0.125rem"
  sm: "0.375rem"
  md: "0.5rem"
  lg: "0.75rem"
  xl: "1rem"
  full: "999px"
spacing:
  xs: "0.125rem"
  sm: "0.25rem"
  sm-md: "0.375rem"
  md: "0.5rem"
  md-lg: "0.75rem"
  lg: "1rem"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.paper-white}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: "0.5rem 0.75rem"
    height: "2.75rem"
  button-outline:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.primary}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "0.25rem 0.75rem"
    height: "2.75rem"
  card-light:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.daylight-ink}"
    rounded: "{rounded.xl}"
    padding: "1.75rem"
  card-dark:
    backgroundColor: "{colors.night-surface}"
    textColor: "{colors.night-text}"
    rounded: "{rounded.xl}"
    padding: "1.75rem"
  input-light:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.daylight-ink}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "0.5rem 0.75rem"
    height: "2.75rem"
  editor-header:
    backgroundColor: "{colors.night-surface}"
    textColor: "{colors.night-text}"
    typography: "{typography.body}"
    padding: "0.5rem 0.75rem"
---

# Design System: Wanderbound

## 1. Overview

**Creative North Star: "The Quiet Print Studio"**

Wanderbound feels like a calm workspace built around a physical result. The
interface is cool-toned, precise, and dependable, but the user's photographs,
maps, and travel story supply the emotion. Product chrome stays restrained so
the album remains the most visually important object on screen.

The system combines compact application controls with generous album surfaces.
It supports light and dark themes without changing the hierarchy, uses motion
for feedback and orientation, and treats the browser preview as an honest
representation of the printed page. It rejects both decorative scrapbook
software and dense professional design tools.

**Key Characteristics:**

- Cool neutral work surfaces with one clear blue action color.
- Compact, familiar controls surrounding large photographic page previews.
- Precise print geometry with A4 landscape pages and millimeter-based gaps.
- Responsive state feedback without decorative choreography.
- Full English, Hebrew, RTL, light-theme, and dark-theme support.

**The Album Leads Rule.** If application chrome competes with a photograph or
map, reduce the chrome.

## 2. Colors

The palette pairs Atlas Blue with cool paper and ink neutrals. Binding Violet
supports the identity without becoming a second action color.

### Primary

- **Atlas Blue** (`primary`): primary actions, selected states, focus rings,
  progress, and the open-book logo.
- **Deep Atlas** (`primary-deep`): the shaded half of the logo and rare depth
  within brand artwork.

### Secondary

- **Binding Violet** (`binding-violet`): a restrained supporting brand tone.
  It is not interchangeable with the primary action color.

### Neutral

- **Night Ink** and **Night Surface** (`night-ink`, `night-surface`): dark-theme
  workspace and raised editor chrome.
- **Cool Paper** and **Paper White** (`cool-paper`, `paper-white`): light-theme
  workspace and raised surfaces.
- **Night Text** and **Daylight Ink** (`night-text`, `daylight-ink`): primary
  readable text for their respective themes.
- **Rule Line** (`rule-line`): light-theme borders, dividers, and field edges.

### Semantic

- **Proofing Red** (`danger`): destructive actions and errors only.

**The One Signal Rule.** Atlas Blue identifies interaction. Do not spend it on
decoration.

**The Theme Parity Rule.** Light and dark themes may change values, never
meaning, hierarchy, or available functionality.

## 3. Typography

- **Display Font:** Assistant, with system sans-serif fallbacks
- **Body Font:** Assistant, with system sans-serif fallbacks
- **Album Body Font:** Frank Ruhl Libre, with Georgia and serif fallbacks

**Character:** Assistant keeps application controls direct, compact, and
legible in both English and Hebrew. Frank Ruhl Libre adds a measured editorial
voice inside album descriptions without leaking display typography into the
tool chrome.

### Hierarchy

- **Display** (800, `display`): landing-page identity and rare large album
  statements.
- **Headline** (700, `title`): page and feature headings that need clear
  hierarchy without oversized product typography.
- **Title** (600 to 700, `title`): dialogs, panels, and album section titles.
- **Body** (400, `body`): instructions, descriptions, and longer interface
  copy. Keep prose near 65 to 75 characters per line.
- **Label** (500 to 700, `label`): buttons, compact controls, navigation, and
  metadata.
- **Album Body** (400, `album-body`): narrative text printed inside the album.

**The Two Rooms Rule.** Assistant owns the application. Frank Ruhl Libre is
reserved for album narrative content.

## 4. Elevation

The system is flat by default and uses tonal layering plus hairline borders to
separate persistent editor regions. Shadows are structural: small shadows mark
selected controls, medium shadows lift album previews, and large shadows are
reserved for temporary menus and dialogs.

### Shadow Vocabulary

- **Selection Lift** (`--shadow-sm`): selected segmented controls and compact
  interactive surfaces.
- **Page Lift** (`--shadow-md`): album previews and landing-page page imagery.
- **Overlay Lift** (`--shadow-lg`): menus, dialogs, and temporary surfaces that
  must sit above the workspace.

**The Earned Elevation Rule.** Persistent cards use a border or a tonal shift.
Only pages, selected controls, and temporary overlays earn a shadow.

## 5. Components

Components are familiar, compact, and quietly responsive. Every control keeps
its meaning across themes and directions.

### Buttons

- **Shape:** gently rounded for product actions (`rounded.md`), compactly
  rounded for outlined editor actions (`rounded.sm`), and fully rounded only
  for provider sign-in or avatar controls (`rounded.full`).
- **Primary:** Atlas Blue background, light text, and a minimum control height
  of 2.75rem.
- **Hover / Focus:** short 150ms color changes and a visible 0.125rem Atlas Blue
  focus outline. Pressed provider buttons may compress to 98% scale.
- **Secondary:** transparent or surface-colored with a one-pixel border. Hover
  can fill with Atlas Blue when that change preserves contrast.

### Segmented Controls

- **Style:** a quiet tinted track with equal-width options and compact spacing.
- **State:** the active segment sits on the raised surface with a small
  structural shadow. Inactive labels remain muted but readable.

### Cards / Containers

- **Corner Style:** one-rem corners (`rounded.xl`) for Quasar cards.
- **Background:** the raised theme surface, distinct from the workspace.
- **Shadow Strategy:** no resting shadow. Use a one-pixel rule line instead.
- **Internal Padding:** 1.25rem on narrow screens and 1.75rem on larger ones.

### Inputs / Fields

- **Style:** outlined controls with compact 0.375rem corners (`rounded.sm`),
  theme-aware text, and a quiet border.
- **Focus:** the border changes to Atlas Blue without increasing layout size.
- **Error / Disabled:** errors use Proofing Red. Disabled controls retain their
  shape and label while reducing emphasis.

### Navigation

Editor navigation uses fixed side drawers, hairline separators, compact labels,
and restrained selected states. The header stays shallow so the album receives
the vertical space. Directional icons mirror in RTL while text and control
meaning remain unchanged.

### Album Page

The A4 landscape page is Wanderbound's signature component. Preview and print
must remain visually identical. Page dimensions use CSS millimeters, photo gaps
use the 2mm to 5mm scale, and application-only chrome disappears without
changing album layout.

## 6. Do's and Don'ts

### Do:

- **Do** make the album page, photograph, or map the dominant object.
- **Do** use Atlas Blue for primary actions, current selection, progress, and
  focus.
- **Do** keep application controls in Assistant and album narrative text in
  Frank Ruhl Libre.
- **Do** preserve identical album visuals between preview and print.
- **Do** preserve control meaning and hierarchy across light, dark, LTR, and
  RTL modes.
- **Do** provide visible focus and reduced-motion behavior for core workflows.

### Don't:

- **Don't** make Wanderbound resemble a scrapbook editor.
- **Don't** make Wanderbound resemble a template marketplace.
- **Don't** make Wanderbound resemble a playful travel app filled with stickers
  and decorative effects.
- **Don't** make Wanderbound resemble dense professional design software that
  exposes every possible control.
- **Don't** use Binding Violet as a competing action color.
- **Don't** add shadows to persistent cards merely for decoration.
- **Don't** alter album content, spacing, or pagination only for print mode.
