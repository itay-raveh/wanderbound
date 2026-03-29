---
paths:
  - "**/*.py"
  - "**/*.ts"
  - "**/*.vue"
---

# Semantic Naming

On every change, reconsider ALL names in the affected scope:

- **Variables/constants**: describe the value, not the type (`tripDays` not `num`, `segmentKind` not `type`)
- **Functions**: verb + noun describing the action (`buildStepLayout`, `parseGpsEdges`)
- **Files**: match the primary export (`useAlbum.ts` exports `useAlbum`, `segments.py` contains `Segment`)
- **Folders**: plural nouns for collections (`routes/`, `models/`), singular for domains (`layout/`, `spatial/`)
- **Components**: PascalCase matching the component name (`StepPhotoPage.vue`)
- **CSS vars**: semantic purpose, not visual value (`--text-muted` not `--gray-400`)
- **Routes/endpoints**: RESTful nouns (`GET /albums/{aid}`, not `GET /getAlbum`)
- **DB columns**: snake_case, descriptive, no abbreviations (`start_time` not `st`)

When renaming, update ALL references. No orphaned old names.
