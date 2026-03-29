---
paths:
  - "frontend/src/components/album/**"
  - "frontend/src/pages/PrintView.vue"
---

# Print-Safe CSS

Album components render in Chromium's PDF backend via Playwright. These CSS features do not render correctly in PDF output:

- box-shadow → use border or outline instead
- filter: blur() or any CSS filter → skip or use a flat fallback
- backdrop-filter → not supported
- mix-blend-mode / background-blend-mode → use solid colors
- position: fixed → use absolute or static
- opacity < 1 on large areas → small icons are fine
- CSS gradients with many stops → simple 2-stop gradients are fine
- transform: scale() on containers → use explicit width/height

Use `print-color-adjust: exact` on elements that need color fidelity.
Test PDF output after any visual changes to album components.
