# NetAtlas Color System

**Product concept:** Digital atlas of enterprise infrastructure  
**Feel:** control · depth · reliability · technology · security  

Not a “router admin panel” — a **knowledge command center** for the network.

## Core surfaces

| Token | Hex | Use |
|-------|-----|-----|
| `--na-bg-primary` | `#070B14` | Application background |
| `--na-bg-surface` | `#0F172A` | Panels, sidebar, topbar |
| `--na-bg-card` | `#111827` | Cards / glass panels |
| `--na-border` | `#1E293B` | Borders, dividers |

## Accents

| Token | Name | Hex | Use |
|-------|------|-----|-----|
| `--na-accent` | Cyber Blue | `#00B8FF` | Active UI, map links, charts |
| `--na-success` | Network Green | `#00E676` | UP / Online / Healthy |
| `--na-warning` | Amber | `#FFB300` | Warnings, degradation |
| `--na-critical` | Red | `#FF3D71` | Down, errors, incidents |

## Text

| Token | Hex |
|-------|-----|
| `--na-text` | `#F8FAFC` |
| `--na-text-muted` | `#94A3B8` |

## Topology node roles

| Role | Hex |
|------|-----|
| Core | `#00B8FF` |
| Distribution | `#7C3AED` |
| Access | `#10B981` |
| Firewall | `#EF4444` |
| Server | `#3B82F6` |
| VM | `#8B5CF6` |
| Storage | `#F59E0B` |
| Unknown | `#64748B` |

## Rules

1. No purple-on-white SaaS defaults. This product is dark navy by design.  
2. No loud gradients on chrome — subtle mesh background only.  
3. Accent blue is for structure and focus; green/red are semantic only.  
4. Borders stay `#1E293B`; never pure white outlines.  
