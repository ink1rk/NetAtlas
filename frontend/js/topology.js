/**
 * NetAtlas Cytoscape topology — consumes /api/v1/topology/graph
 */
const Topology = (() => {
  let cy = null;
  let trafficTimer = null;

  const ROLE_COLORS = {
    core: '#00B8FF',
    distribution: '#7C3AED',
    access: '#10B981',
    firewall: '#EF4444',
    server: '#3B82F6',
    vm: '#8B5CF6',
    storage: '#F59E0B',
    unknown: '#64748B',
  };

  function resolveNodeColor(n) {
    const role = String(n.role || '').toLowerCase();
    const type = String(n.type || '').toLowerCase();
    const platform = String(n.platform || n.vendor || '').toLowerCase();
    const combined = `${role} ${type} ${platform}`;

    if (/firewall|ideco/.test(combined)) return ROLE_COLORS.firewall;
    if (/distribution/.test(combined)) return ROLE_COLORS.distribution;
    if (/vm|proxmox|vsphere|esxi|hypervisor/.test(combined)) return ROLE_COLORS.vm;
    if (/storage|nas|san|disk/.test(combined)) return ROLE_COLORS.storage;
    if (/server|linux|host/.test(combined)) return ROLE_COLORS.server;
    if (/core|eltex|router|spine/.test(combined)) return ROLE_COLORS.core;
    if (/access|switch|unifi|mikrotik|edge/.test(combined)) return ROLE_COLORS.access;
    return ROLE_COLORS.unknown;
  }

  const style = [
    {
      selector: 'node',
      style: {
        'background-color': '#111827',
        'background-opacity': 0.95,
        'border-width': 2,
        'border-color': 'data(color)',
        label: 'data(label)',
        color: '#F8FAFC',
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
      style: { shape: 'round-rectangle' },
    },
    {
      selector: 'node[type = "router"]',
      style: { shape: 'diamond' },
    },
    {
      selector: 'node[type = "firewall"]',
      style: { shape: 'hexagon' },
    },
    {
      selector: 'node[type = "server"]',
      style: { shape: 'rectangle', width: 30, height: 30 },
    },
    {
      selector: 'node:selected',
      style: {
        'border-color': '#00B8FF',
        'border-width': 3,
        'background-color': '#1a2332',
      },
    },
    {
      selector: 'edge',
      style: {
        width: 2,
        'line-color': 'rgba(0, 184, 255, 0.28)',
        'target-arrow-color': 'rgba(0, 184, 255, 0.28)',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        'line-style': 'dashed',
        'line-dash-pattern': [6, 4],
        'line-dash-offset': 0,
        label: 'data(label)',
        'font-size': 8,
        color: '#64748B',
        'text-rotation': 'autorotate',
      },
    },
    {
      selector: 'edge:selected',
      style: {
        'line-color': '#00B8FF',
        'target-arrow-color': '#00B8FF',
        width: 3,
        opacity: 1,
      },
    },
    {
      selector: '.highlighted',
      style: { 'border-color': '#00B8FF', 'line-color': '#00B8FF' },
    },
  ];

  function mapGraph(data) {
    const nodes = (data.nodes || []).map((n) => ({
      data: {
        id: n.id || n.device_id,
        label: n.label || n.hostname || n.id,
        type: n.type || n.platform || 'switch',
        color: resolveNodeColor(n),
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

  function startTrafficAnimation() {
    stopTrafficAnimation();
    let offset = 0;
    trafficTimer = setInterval(() => {
      if (!cy) return;
      offset = (offset + 1) % 20;
      cy.edges().style('line-dash-offset', offset);
    }, 120);
  }

  function stopTrafficAnimation() {
    if (trafficTimer) {
      clearInterval(trafficTimer);
      trafficTimer = null;
    }
  }

  async function init(containerId, options = {}) {
    const el = document.getElementById(containerId);
    if (!el) return null;

    if (cy) { cy.destroy(); cy = null; }
    stopTrafficAnimation();

    el.innerHTML = `<div class="empty-state"><p>${(typeof I18n !== 'undefined' && I18n.t('topo.loading')) || 'Loading topology…'}</p></div>`;

    try {
      const graph = options.graph || await Api.topologyGraph();
      el.innerHTML = '';

      cy = cytoscape({
        container: el,
        elements: mapGraph(graph),
        style,
        layout: {
          name: 'cose',
          animate: true,
          padding: options.padding ?? 50,
          nodeRepulsion: 9000,
          idealEdgeLength: 100,
          gravity: 0.25,
        },
        minZoom: 0.15,
        maxZoom: 4,
        wheelSensitivity: 0.3,
      });

      cy.on('tap', 'node', (evt) => {
        const id = evt.target.data('id');
        if (options.onNodeClick) options.onNodeClick(id, evt.target.data());
        else if (!options.compact) window.location.href = `/pages/device-detail.html?id=${id}`;
      });

      cy.ready(() => {
        cy.fit(undefined, options.padding ?? 50);
        startTrafficAnimation();
      });

      return cy;
    } catch (err) {
      el.innerHTML = `<div class="empty-state"><p>${App.escapeHtml((typeof I18n !== 'undefined' && I18n.t('topo.failed', { msg: err.message })) || err.message)}</p></div>`;
      return null;
    }
  }

  function fit() { if (cy) cy.fit(undefined, 50); }
  function relayout() {
    if (cy) cy.layout({ name: 'cose', animate: true, padding: 50, nodeRepulsion: 9000 }).run();
  }
  function destroy() {
    stopTrafficAnimation();
    if (cy) { cy.destroy(); cy = null; }
  }
  function getCy() { return cy; }

  return { init, fit, relayout, destroy, getCy, resolveNodeColor, ROLE_COLORS };
})();
