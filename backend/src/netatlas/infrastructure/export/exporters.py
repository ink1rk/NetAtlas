"""Topology and export exporters."""

from __future__ import annotations

import json
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring


class TopologyExporter:
    """Export topology graph to multiple offline formats."""

    def export(self, *, format: str, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> tuple[bytes, str]:
        fmt = format.lower()
        if fmt == "json":
            body = json.dumps({"nodes": nodes, "edges": edges}, indent=2).encode("utf-8")
            return body, "application/json"
        if fmt == "graphml":
            return self._graphml(nodes, edges), "application/graphml+xml"
        if fmt == "svg":
            return self._svg(nodes, edges), "image/svg+xml"
        if fmt == "drawio":
            return self._drawio(nodes, edges), "application/xml"
        if fmt == "pdf":
            # Minimal valid PDF wrapping SVG text representation (vector listing).
            return self._minimal_pdf(nodes, edges), "application/pdf"
        if fmt == "png":
            # PNG requires rasterization; provide SVG bytes labeled for client conversion fallback.
            # True PNG is generated when cairo/pillow available; otherwise SVG substitute is documented.
            try:
                return self._png_via_svg(nodes, edges), "image/png"
            except Exception:
                return self._svg(nodes, edges), "image/svg+xml"
        if fmt == "vsdx":
            return self._vsdx(nodes, edges), "application/vnd.ms-visio.drawing"
        raise ValueError(f"Unsupported export format: {format}")

    def _graphml(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> bytes:
        root = Element("graphml", xmlns="http://graphml.graphdrawing.org/xmlns")
        graph = SubElement(root, "graph", edgedefault="undirected")
        for n in nodes:
            node = SubElement(graph, "node", id=str(n["id"]))
            data = SubElement(node, "data", key="label")
            data.text = str(n.get("label") or n["id"])
        for e in edges:
            SubElement(
                graph,
                "edge",
                id=str(e["id"]),
                source=str(e["source"]),
                target=str(e["target"]),
            )
        return tostring(root, encoding="utf-8", xml_declaration=True)

    def _svg(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> bytes:
        width, height = 1200, 800
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="#0b1220"/>',
        ]
        positions: dict[str, tuple[float, float]] = {}
        cols = max(1, int(len(nodes) ** 0.5))
        for idx, n in enumerate(nodes):
            x = 80 + (idx % cols) * (width - 160) / max(cols, 1)
            y = 80 + (idx // cols) * (height - 160) / max((len(nodes) // cols) + 1, 1)
            positions[str(n["id"])] = (x, y)
        for e in edges:
            a = positions.get(str(e["source"]))
            b = positions.get(str(e["target"]))
            if not a or not b:
                continue
            parts.append(
                f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="#3dd6c6" stroke-width="2"/>'
            )
        for n in nodes:
            x, y = positions[str(n["id"])]
            label = str(n.get("label") or n["id"]).replace("<", "").replace(">", "")
            parts.append(f'<circle cx="{x}" cy="{y}" r="18" fill="#1b2a41" stroke="#7aa2f7" stroke-width="2"/>')
            parts.append(
                f'<text x="{x}" y="{y + 36}" fill="#e6edf7" font-size="12" text-anchor="middle">{label}</text>'
            )
        parts.append("</svg>")
        return "".join(parts).encode("utf-8")

    def _drawio(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> bytes:
        # Simplified mxGraphModel for draw.io import
        cells = [
            '<mxCell id="0"/>',
            '<mxCell id="1" parent="0"/>',
        ]
        for idx, n in enumerate(nodes):
            x = 40 + (idx % 6) * 160
            y = 40 + (idx // 6) * 100
            label = str(n.get("label") or n["id"])
            cells.append(
                f'<mxCell id="n{n["id"]}" value="{label}" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#1b2a41;strokeColor=#7aa2f7;fontColor=#e6edf7;" vertex="1" parent="1">'
                f'<mxGeometry x="{x}" y="{y}" width="120" height="48" as="geometry"/></mxCell>'
            )
        for e in edges:
            cells.append(
                f'<mxCell id="e{e["id"]}" style="edgeStyle=orthogonalEdgeStyle;strokeColor=#3dd6c6;" edge="1" parent="1" source="n{e["source"]}" target="n{e["target"]}">'
                f'<mxGeometry relative="1" as="geometry"/></mxCell>'
            )
        xml = (
            '<mxfile host="NetAtlas"><diagram name="Topology"><mxGraphModel><root>'
            + "".join(cells)
            + "</root></mxGraphModel></diagram></mxfile>"
        )
        return xml.encode("utf-8")

    def _minimal_pdf(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> bytes:
        lines = [f"NetAtlas Topology Export", f"Nodes: {len(nodes)} Edges: {len(edges)}"]
        for n in nodes[:200]:
            lines.append(f"- {n.get('label') or n['id']}")
        content = "\\n".join(lines)
        # Very small PDF
        objects = []
        objects.append("1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
        objects.append("2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
        objects.append(
            "3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources<< /Font<< /F1 5 0 R >> >> >>endobj\n"
        )
        stream = f"BT /F1 10 Tf 50 750 Td ({content[:1000]}) Tj ET"
        objects.append(f"4 0 obj<< /Length {len(stream)} >>stream\n{stream}\nendstream\nendobj\n")
        objects.append("5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")
        pdf = ["%PDF-1.4\n"]
        offsets = [0]
        for obj in objects:
            offsets.append(sum(len(x.encode()) for x in pdf))
            pdf.append(obj)
        xref_pos = sum(len(x.encode()) for x in pdf)
        pdf.append(f"xref\n0 {len(objects)+1}\n")
        pdf.append("0000000000 65535 f \n")
        for off in offsets[1:]:
            pdf.append(f"{off:010d} 00000 n \n")
        pdf.append(f"trailer<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n")
        return "".join(pdf).encode("latin-1", errors="replace")

    def _png_via_svg(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> bytes:
        # Prefer cairosvg if present; otherwise raise for fallback.
        import cairosvg  # type: ignore[import-untyped]

        svg = self._svg(nodes, edges)
        return cairosvg.svg2png(bytestring=svg)

    def _vsdx(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> bytes:
        # Produce a ZIP-based Visio package with minimal pages.xml content.
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "[Content_Types].xml",
                '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/visio/pages/pages.xml" ContentType="application/vnd.ms-visio.pages+xml"/>'
                "</Types>",
            )
            page_shapes = []
            for idx, n in enumerate(nodes):
                page_shapes.append(
                    f'<Shape ID="{idx+1}" Name="{n.get("label") or n["id"]}" Type="Shape"><Text>{n.get("label") or n["id"]}</Text></Shape>'
                )
            zf.writestr(
                "visio/pages/pages.xml",
                '<?xml version="1.0"?><Pages xmlns="http://schemas.microsoft.com/office/visio/2012/main">'
                f'<Page ID="0" Name="Topology"><Shapes>{"".join(page_shapes)}</Shapes></Page></Pages>',
            )
            zf.writestr(
                "visio/edges.json",
                json.dumps(edges),
            )
        return buf.getvalue()
