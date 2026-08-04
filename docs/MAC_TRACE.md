# MAC Trace (Find Device)

Primary operational workflow: locate an endpoint by **MAC**, **IP**, or **hostname** and see where it is attached.

## Result shape

```
Device:   PC-001
MAC/IP:   …
Connected: SW-ACCESS-03
Port:      Gi1/0/24
VLAN:      120
Path:      endpoint → ACCESS → DISTRIBUTION → CORE …
```

## Resolution order

1. Normalize MAC / match IP or hostname
2. Search FDB entries → access switch + port
3. Fall back to ARP / IPAM / device management identity
4. Walk LLDP/link graph upward using role ranks for a readable path

## UI

- NOC workspace **Find Device** (`?ws=find&q=…`)
- Command palette: `trace MAC …`, `find IP …`, Ctrl+K
- Path is highlighted on the Live Network Map

## API

| Method | Path |
|--------|------|
| GET | `/api/v1/trace/mac?q=` |

Requires inventory data (FDB/ARP) from Deep / Topology discovery for best results.
