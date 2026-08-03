# NetAtlas Frontend Guidelines

## Product identity

**NetAtlas** = digital atlas of enterprise infrastructure.

UI must feel like a NOC / SOC knowledge center (Cisco DNA Center, Palo Alto Panorama, Grafana Enterprise, VMware Aria) — calm, dense with meaning, never playful.

## Mandatory references

Always read before UI work:

1. [`colors.md`](colors.md)  
2. [`logo/README.md`](logo/README.md)  
3. [`backgrounds/README.md`](backgrounds/README.md)  
4. [`icons/README.md`](icons/README.md)  

CSS source of truth: `frontend/css/app.css` (`:root` tokens).

## Typography

| Role | Font | Notes |
|------|------|-------|
| UI | Inter | Regular / Medium / SemiBold |
| IP, MAC, serials, logs, CLI | JetBrains Mono | Never Inter for identifiers |

Offline-vendored only. No Google Fonts CDN.

## Layout principles

1. **One composition** per viewport — dashboard is an atlas, not a widget collage.  
2. **Brand-first** on login: NetAtlas mark + name dominate.  
3. **Live map is the hero** of the main console.  
4. Cards/panels use dark glass (`--na-bg-card` + border). No white cards.  
5. Prefer tables and map over badge clouds / pill clusters.  
6. Motion: fade-in nodes, subtle packet flow on edges, smooth zoom. No spin/neon/game FX.

## Page set

| Page | Purpose |
|------|---------|
| Login | Brand + auth |
| Dashboard | KPI strip + live map + health |
| Topology | Full-bleed interactive atlas |
| Devices / Device detail | Inventory truth |
| Interfaces / VLANs | L2 detail |
| IPAM | Address space |
| Snapshots / Diff | Change intelligence |
| Observability | Syslog / triggers / SIEM |
| Settings | Local system config |

## Do / Don’t

**Do:** dark navy, cyber blue links, semantic green/red, mono for IPs, Cytoscape atlas.  
**Don’t:** emoji icons, rainbow charts, heavy glassmorphism blur, gradients on buttons, rotating 3D globes.

## Consistency check (every PR)

- [ ] Uses CSS variables from `app.css`  
- [ ] No hardcoded competing accent colors  
- [ ] Topology roles match `colors.md`  
- [ ] Assets loaded from `/static/...` only (offline)  
