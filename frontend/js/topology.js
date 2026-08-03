/**
 * NetAtlas Cytoscape topology — consumes /api/v1/topology/graph
 */
const Topology = (() => {
  let cy = null;

  const style = [
    {
      selector: 'node',
      style: {
        'background-color': '#1c2636',
        'border-width': 2,
        'border-color': '#00c9a7',
        label: 'data(label)',
        color: '#e4eaf2',
        'font-size': 10,
        'font-family': 'JetBrains Mono, monospace',
        'text-valign': 'bottom',
        'text-margin-y': 6,
        width: 36,
        height: 36,
        'text-wrap': 'ellipsis',
        'text-max-width': 80,
      },
    },
    {
      selector: 'node[type = "switch"]',
      style: { shape: 'round-rectangle', 'background-color': '#243044' },
    },
    {
      selector: 'node[type = "router"]',
      style: { shape: 'diamond', 'border-color': '#3b9eff' },
    },
    {
      selector: 'node[type = "firewall"]',
      style: { shape: 'hexagon', 'border-color': '#f05252' },
    },
    {
      selector: 'node[type = "server"]',
      style: { shape: 'rectangle', 'border-color': '#f0a030', width: 30, height: 30 },
    },
    {
      selector: 'node:selected',
      style: {
        'border-color': '#2ee8c5',
        'border-width': 3,
        'background-color': '#2a384c',
      },
    },
    {
      selector: 'edge',
      style: {
        width: 2,
        'line-color': '#3a4d66',
        'target-arrow-color': '#3a4d66',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        label: 'data(label)',
        'font-size': 8,
        color: '#556275',
        'text-rotation': 'autorotate',
      },
    },
    {
      selector: 'edge:selected',
      style: { 'line-color': '#00c9a7', 'target-arrow-color': '#00c9a7', width: 3 },
    },
    {
      selector: '.highlighted',
      style: { 'border-color': '#2ee8c5', 'line-color': '#00c9a7' },
    },
  ];

  function mapGraph(data) {
    const nodes = (data.nodes || []).map((n) => ({
      data: {
        id: n.id || n.device_id,
        label: n.label || n.hostname || n.id,
        type: n.type || n.platform || 'switch',
        ...n,
      },
    }));
    const edges = (data.edges || []).map((e, i) => ({
      data: {
        id: e.id || `e${i}`,
        source: e.source || e.from,
        target: e.target || e.to,
        label: e.label || e.interface || '',
        ...e,
      },
    }));
    return [...nodes, ...edges];
  }

  async function init(containerId, options = {}) {
    const el = document.getElementById(containerId);
    if (!el) return null;

    if (cy) { cy.destroy(); cy = null; }

    el.innerHTML = '<div class="empty-state"><p>Loading topology…</p></div>';

    try {
      const graph = await Api.topologyGraph();
      el.innerHTML = '';

      cy = cytoscape({
        container: el,
        elements: mapGraph(graph),
        style,
        layout: { name: 'cose', animate: true, padding: 40, nodeRepulsion: 8000 },
        minZoom: 0.2,
        maxZoom: 4,
        wheelSensitivity: 0.3,
      });

      cy.on('tap', 'node', (evt) => {
        const id = evt.target.data('id');
        if (options.onNodeClick) options.onNodeClick(id, evt.target.data());
        else window.location.href = `/pages/device-detail.html?id=${id}`;
      });

      return cy;
    } catch (err) {
      el.innerHTML = `<div class="empty-state"><p>Failed to load topology: ${App.escapeHtml(err.message)}</p></div>`;
      return null;
    }
  }

  function fit() { if (cy) cy.fit(undefined, 40); }
  function relayout() { if (cy) cy.layout({ name: 'cose', animate: true, padding: 40 }).run(); }
  function destroy() { if (cy) { cy.destroy(); cy = null; } }
  function getCy() { return cy; }

  return { init, fit, relayout, destroy, getCy };
})();
