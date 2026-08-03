# NetAtlas Design System

**Concept:** Digital atlas of enterprise infrastructure.

This folder is the visual source of truth. Frontend work must follow it so the UI stays coherent over time.

## Contents

| Path | Purpose |
|------|---------|
| [`colors.md`](colors.md) | Palette + topology role colors |
| [`frontend-guidelines.md`](frontend-guidelines.md) | Layout, typography, do/don’t |
| [`logo/`](logo/) | Mark SVG/PNG + generation prompt |
| [`backgrounds/`](backgrounds/) | Mesh background assets |
| [`icons/`](icons/) | Icon style rules |

## Runtime mapping

Tokens live in `frontend/css/app.css` (`:root`).  
Brand files are mirrored to `frontend/static/brand/` for offline serving.
