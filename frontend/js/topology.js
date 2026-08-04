/**
 * NetAtlas Cytoscape topology — consumes /api/v1/topology/graph
 * Supports compact dashboard mode + mini-map overview.
 */
const Topology = (() => {
  let cy = null;
  let miniCy = null;
  let trafficTimer = null;
  let viewportHandler = null;

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

  function themeColors() {
    const dark = (document.documentElement.getAttribute('data-theme') || 'dark') !== 'light';
    return {
      nodeBg: dark ? '#111827' : '#FFFFFF',
      label: dark ? '#F8FAFC' : '#0F172A',
      edge: dark ? 'rgba(0, 184, 255, 0.28)' : 'rgba(2, 132, 199, 0.35)',
      edgeLabel: dark ? '#64748B' : '#64748B',
      selectedBg: dark ? '#1a2332' : '#E8EEF6',
      miniBg: dark ? 'rgba(7, 11, 20, 0.2)' : 'rgba(241, 245, 249, 0.2)',
    };
  }

  function buildStyle() {
    const c = themeColors();
    return [
      {
        selector: 'node',
        style: {
          'background-color': c.nodeBg,
          'background-opacity': 0.95,
          'border-width': 2,
          'border-color': 'data(color)',
          label: 'data(label)',
          color: c.label,
          'font-size': 10,
          'font-family': 'IBM Plex Sans, sans-serif',
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
          'background-color': c.selectedBg,
        },
      },
      {
        selector: 'edge',
        style: {
          width: 2,
          'line-color': c.edge,
          'target-arrow-color': c.edge,
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
          'line-style': 'dashed',
          'line-dash-pattern': [6, 4],
          'line-dash-offset': 0,
          label: 'data(label)',
          'font-size': 8,
          color: c.edgeLabel,
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
  }

  function miniStyle() {
    return [
      {
        selector: 'node',
        style: {
          'background-color': 'data(color)',
          width: 6,
          height: 6,
          label: '',
          'border-width': 0,
        },
      },
      {
        selector: 'edge',
        style: {
          width: 1,
          'line-color': 'rgba(0, 184, 255, 0.35)',
          'curve-style': 'haystack',
          'haystack-radius': 0,
          'target-arrow-shape': 'none',
          label: '',
        },
      },
    ];
  }

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

  function destroyMiniMap() {
    if (viewportHandler && cy) {
      cy.off('viewport', viewportHandler);
      viewportHandler = null;
    }
    if (miniCy) {
      miniCy.destroy();
      miniCy = null;
    }
  }

  function ensureMiniMapHost(mainEl, options) {
    const stage = mainEl.parentElement;
    if (!stage) return null;
    let host = stage.querySelector('.topo-minimap');
    if (!options.minimap) {
      host?.remove();
      return null;
    }
    if (!host) {
      host = document.createElement('div');
      host.className = 'topo-minimap';
      host.innerHTML = `
        <div class="topo-minimap__label">${(typeof I18n !== 'undefined' && I18n.t('topo.minimap')) || 'Mini map'}</div>
        <div class="topo-minimap__canvas" id="${options.minimapId || 'topo-minimap-cy'}"></div>
      `;
      stage.appendChild(host);
    }
    return host.querySelector('.topo-minimap__canvas') || host;
  }

  function syncMiniViewport() {
    if (!cy || !miniCy) return;
    const ext = cy.extent();
    miniCy.$('.na-viewport').remove();
    miniCy.add({
      group: 'nodes',
      data: { id: '__viewport__' },
      classes: 'na-viewport',
      selectable: false,
      grabbable: false,
    });
    // Approximate viewport rectangle via a node positioned/sized in model coords
    const w = Math.max(40, ext.x2 - ext.x1);
    const h = Math.max(40, ext.y2 - ext.y1);
    const cx = (ext.x1 + ext.x2) / 2;
    const cyPos = (ext.y1 + ext.y2) / 2;
    miniCy.$('#__viewport__').style({
      shape: 'rectangle',
      width: w,
      height: h,
      'background-opacity': 0.08,
      'background-color': '#00B8FF',
      'border-width': 1,
      'border-color': '#00B8FF',
      'border-opacity': 0.7,
      label: '',
      events: 'no',
    });
    miniCy.$('#__viewport__').position({ x: cx, y: cyPos });
  }

  function initMiniMap(mainEl, elements, options) {
    destroyMiniMap();
    const miniEl = ensureMiniMapHost(mainEl, options);
    if (!miniEl || typeof cytoscape === 'undefined') return;

    miniEl.innerHTML = '';
    miniCy = cytoscape({
      container: miniEl,
      elements: elements.filter((el) => el.data?.id !== '__viewport__'),
      style: miniStyle(),
      layout: { name: 'preset' },
      userZoomingEnabled: false,
      userPanningEnabled: false,
      boxSelectionEnabled: false,
      autoungrabify: true,
      autounselectify: true,
    });

    // Copy positions from main graph after layout
    const copyPositions = () => {
      if (!cy || !miniCy) return;
      cy.nodes().forEach((n) => {
        const m = miniCy.$id(n.id());
        if (m.nonempty()) m.position(n.position());
      });
      miniCy.fit(undefined, 8);
      syncMiniViewport();
    };

    // Click minimap to pan main
    miniCy.on('tap', (evt) => {
      if (!cy) return;
      const pos = evt.position || evt.cyPosition;
      if (!pos) return;
      cy.animate({ center: { eles: cy.nodes().length ? undefined : undefined }, duration: 0 });
      cy.pan({
        x: cy.width() / 2 - pos.x * cy.zoom(),
        y: cy.height() / 2 - pos.y * cy.zoom(),
      });
      // Better: center on model position
      cy.center();
      const zp = cy.zoom();
      const pan = {
        x: cy.width() / 2 - zp * pos.x,
        y: cy.height() / 2 - zp * pos.y,
      };
      cy.pan(pan);
      syncMiniViewport();
    });

    viewportHandler = () => syncMiniViewport();
    cy.on('viewport', viewportHandler);
    cy.on('dragfree', 'node', copyPositions);

    // Initial sync after layout
    setTimeout(copyPositions, 50);
    cy.one('layoutstop', copyPositions);
  }

  async function init(containerId, options = {}) {
    const el = document.getElementById(containerId);
    if (!el) return null;

    if (cy) { cy.destroy(); cy = null; }
    destroyMiniMap();
    stopTrafficAnimation();

    el.innerHTML = `<div class="empty-state"><p>${(typeof I18n !== 'undefined' && I18n.t('topo.loading')) || 'Loading topology…'}</p></div>`;

    try {
      const graph = options.graph || await Api.topologyGraph();
      el.innerHTML = '';
      const elements = mapGraph(graph);

      cy = cytoscape({
        container: el,
        elements,
        style: buildStyle(),
        layout: {
          name: 'cose',
          animate: !options.compact,
          animationDuration: options.compact ? 0 : 400,
          padding: options.padding ?? (options.compact ? 30 : 50),
          nodeRepulsion: options.compact ? 7000 : 9000,
          idealEdgeLength: options.compact ? 80 : 100,
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
        cy.fit(undefined, options.padding ?? (options.compact ? 30 : 50));
        startTrafficAnimation();
        if (options.minimap !== false && (options.minimap || options.compact)) {
          initMiniMap(el, elements, { ...options, minimap: true });
        }
      });

      return cy;
    } catch (err) {
      el.innerHTML = `<div class="empty-state"><p>${App.escapeHtml((typeof I18n !== 'undefined' && I18n.t('topo.failed', { msg: err.message })) || err.message)}</p></div>`;
      return null;
    }
  }

  function fit() { if (cy) cy.fit(undefined, 50); }
  function relayout() {
    if (cy) {
      cy.layout({ name: 'cose', animate: true, padding: 50, nodeRepulsion: 9000 }).run();
      cy.one('layoutstop', () => {
        if (miniCy) {
          cy.nodes().forEach((n) => {
            const m = miniCy.$id(n.id());
            if (m.nonempty()) m.position(n.position());
          });
          miniCy.fit(undefined, 8);
          syncMiniViewport();
        }
      });
    }
  }
  function destroy() {
    stopTrafficAnimation();
    destroyMiniMap();
    if (cy) { cy.destroy(); cy = null; }
  }
  function getCy() { return cy; }

  return { init, fit, relayout, destroy, getCy, resolveNodeColor, ROLE_COLORS };
})();
