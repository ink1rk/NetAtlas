# NetAtlas Enterprise Design System

Design system for the NetAtlas operator console. Inspired by Cisco DNA Center, VMware Aria, Grafana Enterprise, Datadog, and Palo Alto Panorama — strict, minimal, and technical.

**Default theme:** Dark  
**Light theme:** `[data-theme="light"]` on `<html>`  
**Assets:** local only (no CDN)  
**Entry CSS:** `frontend/css/app.css` → imports `tokens.css`, `components.css`, `layout.css`, `noc.css`  
**Primary UX:** Digital Twin NOC — Live Network Map is the main workspace (`App.initNocShell`)

---

## 1. Design Tokens

Defined in `frontend/css/tokens.css`.

### Colors

| Token | Role |
|-------|------|
| `--na-bg-canvas` / `--na-bg-primary` | Page background |
| `--na-bg-surface` / `--na-bg-card` / `--na-bg-elevated` | Panels & cards |
| `--na-bg-hover` / `--na-bg-active` | Interactive surfaces |
| `--na-border` / `--na-border-strong` / `--na-border-focus` | Borders & focus |
| `--na-text` / `--na-text-secondary` / `--na-text-muted` / `--na-text-dim` | Text hierarchy |
| `--na-accent` (`#00B8FF`) | Brand / primary actions |
| `--na-success` / `--na-warning` / `--na-danger` / `--na-info` | Semantic status |
| `--na-role-*` | Topology node roles |

Component aliases: `--na-color-surface-*`, `--na-color-accent`, `--na-color-text`, etc.

### Typography

| Token | Value |
|-------|--------|
| `--na-font-sans` / `--na-font-display` | IBM Plex Sans (local) |
| `--na-font-mono` | JetBrains Mono (local) |
| `--na-text-xs` … `--na-text-3xl` | Type scale |
| `--na-weight-*` | 400 / 500 / 600 / 700 |
| `--na-leading-*` | tight / normal / relaxed |

### Spacing

4px base scale: `--na-space-1` (4px) … `--na-space-16` (64px).

### Radius

`--na-radius-xs` → `--na-radius-xl`, plus `--na-radius-full`.

### Shadows

`--na-shadow-xs` … `--na-shadow-xl`, `--na-shadow-glow`, `--na-focus-ring`.

### Motion

| Token | Use |
|-------|-----|
| `--na-duration-fast` (120ms) | Hover / focus |
| `--na-duration-base` (180ms) | Panels / toasts |
| `--na-duration-slow` (280ms) | Shell / drawers |
| `--na-ease-out` / `--na-ease-spring` | Enterprise easing |

Keyframes: `na-spin`, `na-fade-in`, `na-fade-out`, `na-slide-in-right`, `na-slide-up`, `na-shimmer`, `na-pulse-dot`.  
Respects `prefers-reduced-motion`.

### Z-index

`base` → `sticky` → `dropdown` → `sidebar` → `overlay` → `modal` → `toast` → `command` → `tooltip`.

### Grid / layout

`--na-sidebar-w` (264px), `--na-sidebar-w-collapsed` (72px), `--na-topbar-h` (56px), `--na-grid-gap`, `--na-dash-map-ratio` (~70% map).

### Breakpoints

640 / 768 / 1024 / 1280 / 1536 (use literals in `@media`).

---

## 2. Themes

```html
<html data-theme="dark">  <!-- default -->
<html data-theme="light">
```

- Persisted in `localStorage.netatlas_theme`
- Toggle via topbar or Command Palette
- Early boot script on pages prevents FOUC

---

## 3. Components

Styles: `frontend/css/components.css`  
Behavior: `frontend/js/ui.js`, shell in `frontend/js/app.js`

### Button — `.na-btn`

Variants: `--primary`, `--secondary`, `--ghost`, `--danger`, `--success`  
Sizes: `--sm`, `--lg`, `--icon`, `--block`  
States: `:hover`, `:active`, `:focus-visible`, `:disabled`, `.is-loading`

Legacy: `.btn-na`, `.btn-na-primary`, `.btn-na-secondary`.

### Input / Select — `.na-input`, `.na-select`, `.form-control`, `.form-select`

States: hover, focus (focus ring), disabled, `.is-invalid`.  
Field layout: `.na-field`, `.na-label`, `.na-hint`, `.na-error`.

### Search — `.na-search`

Global: `.na-search--global` with icon + `⌘K` hint.  
Uses autocomplete from `Ui.attachAutocomplete`.

### Badge / Chip / Status

- `.na-badge--neutral|info|success|warning|danger`
- `.na-chip` (+ `.is-active`)
- `.na-status--up|down|degraded|unknown` + `.na-status__dot`

### Cards

| Class | Purpose |
|-------|---------|
| `.na-card` / `.panel` | Generic panel |
| `.na-metric` | KPI metric card |
| `.na-device-card` | Device summary |
| `.na-alert-card` | Alert row (`--critical|--warning|--info`) |

### Modal / Drawer

- `.na-overlay` + `.na-modal` (`.is-open`)
- `.na-drawer` (right sheet, `.is-open`)
- Bootstrap `.modal-*` polished to tokens

### Toast — `.na-toast`

Host: `#na-toasts.na-toaster`  
API: `Ui.toast(message, kind, { title, duration })`  
Kinds: `info`, `success`/`ok`, `warning`, `error`/`danger`.

### Tooltip — `.na-tooltip.is-visible`

### Table — `.na-table` / `.table` in `.na-table-wrap`

Sticky header, hover rows, semantic borders.

### Tree — `.na-tree`, `.na-tree__item.is-active`

### Tabs — `.na-tabs` / `.na-tab.is-active` (also Bootstrap `.nav-tabs`)

### Breadcrumbs — `.na-breadcrumbs`

### Timeline — `.na-timeline` / `.na-timeline__item`

### Charts — `.na-chart` (+ Chart.js local vendor)

### Command Palette — `.na-cmd`

- Open: `Ctrl/Cmd+K`, topbar button, or `App.openCommandPalette()`
- Groups: Actions + Navigation
- Keyboard: ↑↓ Enter Esc

### Autocomplete — `.ac-list` / `.ac-item`

### Quick actions — `.na-quick-action`

### Notifications

- Bell in topbar, badge unread count
- Panel: `.na-notif-panel`
- API: `Ui.pushNotification`, `Ui.initNotifications`

---

## 4. Shell layout

### Sidebar

- Brand mark + **NetAtlas** product name
- Grouped nav (Overview / Inventory / Operations)
- Active indicator + accent rail
- User block + logout
- Collapsible on desktop; drawer on mobile

### Topbar

- Page title
- Global search (center)
- Command palette, quick actions, notifications, theme toggle, language, clock

### Dashboard

- **~70%** Network Map (Cytoscape) with live indicator
- Mini map overlay
- **~30%** analytics rail: metrics, health, alerts, activity timeline
- Quick actions on the map header

---

## 5. Interaction states (standard)

| State | Pattern |
|-------|---------|
| Default | Surface + border |
| Hover | Elevated surface / accent border |
| Active / pressed | Darker surface, slight translateY |
| Focus | `--na-focus-ring` (never outline:none without replacement) |
| Disabled | `opacity: 0.45`, `pointer-events: none` |
| Loading | Spinner overlay / skeleton `.na-skeleton` |

---

## 6. Accessibility

- Prefer buttons for actions; links for navigation
- Icon-only controls need `aria-label` / `title`
- Command palette and modals: `role="dialog"`, `aria-modal="true"`
- Toasts: `aria-live="polite"`
- Focus rings visible in both themes
- Do not rely on color alone for status — use labels + dots
- Respect `prefers-reduced-motion`
- Language switcher exposes `aria-label`

---

## 7. Usage examples

### Primary button

```html
<button class="na-btn na-btn--primary">Discover</button>
```

### Metric card

```html
<div class="na-metric na-metric--accent">
  <div class="na-metric__label">Devices</div>
  <div class="na-metric__value">128</div>
</div>
```

### Toast

```js
Ui.toast('Discovery job queued', 'success', { title: 'Discovery' });
```

### Command palette

```js
App.openCommandPalette();        // all
App.openCommandPalette('actions'); // quick actions only
```

### Theme

```js
App.applyTheme('light');
App.toggleTheme();
```

---

## 8. Rules of use

1. **Tokens first** — no hard-coded brand colors in page CSS; use variables.
2. **Reuse components** — prefer `.na-*` over one-off styles.
3. **One job per section** — dashboard map vs analytics stay separated.
4. **Local assets only** — fonts, Bootstrap, Cytoscape, Chart.js from `/static`.
5. **Dark default** — light is opt-in, not the primary look.
6. **Do not change API/backend** for UI work; compose existing endpoints.
7. **Motion with purpose** — entrance, hierarchy, feedback — not decoration noise.
8. **Map is the product** — on Dashboard, the network map owns the workspace.

---

## 9. NOC Digital Twin workspace

NetAtlas operator UX is map-centric (`frontend/js/noc.js`, `frontend/css/noc.css`).

| Zone | Role |
|------|------|
| Workspace rail (left) | Network, Cable Map, Inventory, IPAM, Monitoring, Snapshots, Backups |
| Left panel | Filters / workspace tools |
| Center (70–80%) | Live Network Map + mini-map |
| Inspector (right) | Selection details without page navigation |
| Bottom timeline | Discovery, Snapshot, Changes, Alerts, Backups |
| Status bar | Discovery progress, online devices, last scan, tasks, realtime status |

### Key APIs

```js
App.initNocShell('network', 'ws.network');
Noc.selectObject({ type: 'device', id, data });
Noc.toggleFocusMode();
Noc.showContextMenu(x, y, target);
Noc.showFuture('rack' | 'visio' | 'ai' | 'backup' | 'diff');
Topology.setFocus(id); Topology.clearFocus();
Topology.highlightPath(path); Topology.fitTo(id);
```

Context menu: Open, Locate, Trace Path, Show Interfaces, View History, Export.  
Future stubs (architecture only, no backend): Rack View, Visio Export, AI Assistant, Configuration Backup, Diff Viewer.

---

## 10. File map

| Path | Role |
|------|------|
| `frontend/css/tokens.css` | Design tokens + themes + keyframes |
| `frontend/css/components.css` | Component library |
| `frontend/css/layout.css` | Shell, sidebar, topbar |
| `frontend/css/noc.css` | NOC workspace layout |
| `frontend/css/app.css` | Entry + page utilities |
| `frontend/js/app.js` | Shell, theme, command palette, `initNocShell` |
| `frontend/js/noc.js` | NOC controller (inspector, timeline, status) |
| `frontend/js/ui.js` | Toasts, autocomplete, notifications |
| `frontend/js/topology.js` | Cytoscape map, mini-map, focus, path |
| `frontend/static/fonts/*` | IBM Plex Sans, JetBrains Mono |
| `frontend/static/vendor/*` | Bootstrap, Cytoscape, Chart.js |
