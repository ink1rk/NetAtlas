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
    const role = String(n.role || n.network_role || '').toLowerCase();
    if (ROLE_COLORS[role]) return ROLE_COLORS[role];
    const type = String(n.type || '').toLowerCase();
    const platform = String(n.platform || n.vendor || '').toLowerCase();
    const combined = `${role} ${type} ${platform}`;

    if (/firewall|ideco/.test(combined)) return ROLE_COLORS.firewall;
    if (/distribution/.test(combined)) return ROLE_COLORS.distribution;
    if (/wireless|wifi|uap/.test(combined)) return ROLE_COLORS.access;
    if (/vm|proxmox|vsphere|esxi|hypervisor/.test(combined)) return ROLE_COLORS.vm;
    if (/storage|nas|san|disk/.test(combined)) return ROLE_COLORS.storage;
    if (/server|linux|host/.test(combined)) return ROLE_COLORS.server;
    if (/core|spine/.test(combined)) return ROLE_COLORS.core;
    if (/router/.test(combined)) return ROLE_COLORS.core;
    if (/access|switch|unifi|mikrotik|edge|eltex/.test(combined)) return ROLE_COLORS.access;
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
          opacity: 1,
          'transition-property': 'opacity, border-width',
          'transition-duration': 0.2,
        },
      },
      {
        selector: 'node.dimmed',
        style: { opacity: 0.15, 'text-opacity': 0.15 },
      },
      {
        selector: 'node.focus-root, node.focus-neighbor',
        style: {
          opacity: 1,
          'border-width': 3,
          'border-color': '#00B8FF',
          'z-index': 10,
        },
      },
      {
        selector: 'node.role-group',
        style: {
          'background-color': '#0B1220',
          'background-opacity': 0.2,
          'border-width': 1,
          'border-color': '#334155',
          'border-style': 'dashed',
          label: 'data(label)',
          'font-size': 11,
          color: '#94A3B8',
          'text-valign': 'top',
          'text-margin-y': -8,
          padding: 18,
          shape: 'roundrectangle',
        },
      },
      {
        selector: 'node.filtered-out',
        style: { display: 'none' },
      },
      {
        selector: 'edge.dimmed',
        style: { opacity: 0.08 },
      },
      {
        selector: 'edge.focus-edge, edge.path-edge',
        style: {
          opacity: 1,
          width: 3,
          'line-color': '#00B8FF',
          'target-arrow-color': '#00B8FF',
          'line-style': 'solid',
          'z-index': 9,
        },
      },
      {
        selector: 'node.filtered-out',
        style: { display: 'none' },
      },
      {
        selector: 'edge.filtered-out',
        style: { display: 'none' },
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
    const nodes = (data.nodes || []).map((n) => {
      const payload = n.data || n;
      const role = n.role || payload.network_role || payload.role || '';
      return {
        data: {
          id: n.id || payload.id || payload.device_id,
          label: n.label || payload.hostname || payload.label || n.id,
          type: n.type || payload.platform || payload.type || 'switch',
          role,
          network_role: role,
          color: resolveNodeColor({ ...payload, role }),
          layout: payload.layout || n.layout,
          ...payload,
          ...n,
        },
      };
    });
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

  function hierarchicalLayoutConfig(elements, options = {}) {
    // Prefer role-hierarchy positions from API layout metadata when present
    const nodes = elements.filter((e) => e.data && e.data.id && !e.data.source);
    const hasLayout = nodes.some((n) => n.data?.layout || n.data?.data?.layout);
    if (hasLayout && !options.forceCose) {
      const byRank = {};
      nodes.forEach((n) => {
        const meta = n.data.layout || n.data.data?.layout || {};
        const rank = meta.rank ?? 5;
        byRank[rank] = byRank[rank] || [];
        byRank[rank].push(n);
      });
      // Mutate element positions for preset layout
      Object.keys(byRank).forEach((rankKey) => {
        const rank = Number(rankKey);
        const list = byRank[rankKey];
        const width = Math.max(list.length, 1);
        list.forEach((n, col) => {
          const meta = n.data.layout || n.data.data?.layout || {};
          const c = meta.column != null ? meta.column : col;
          n.position = {
            x: (c - (width - 1) / 2) * 160,
            y: rank * 140,
          };
        });
      });
      return {
        name: 'preset',
        animate: !options.compact,
        padding: options.padding ?? 40,
        fit: true,
      };
    }
    return {
      name: 'cose',
      animate: !options.compact,
      animationDuration: options.compact ? 0 : 400,
      padding: options.padding ?? (options.compact ? 30 : 50),
      nodeRepulsion: options.compact ? 7000 : 9000,
      idealEdgeLength: options.compact ? 80 : 100,
      gravity: 0.25,
    };
  }

  function applyHierarchy(layoutNodes) {
    if (!cy || !layoutNodes) return;
    Object.entries(layoutNodes).forEach(([id, meta]) => {
      const n = cy.$id(String(id));
      if (n.empty()) return;
      const width = meta.columns_in_layer || 1;
      const col = meta.column || 0;
      const rank = meta.rank ?? 5;
      n.position({
        x: (col - (width - 1) / 2) * 160,
        y: rank * 140,
      });
      n.data('role', meta.layer || n.data('role'));
    });
    cy.fit(undefined, 40);
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
      // Attach layout metadata onto node data for preset layout
      if (graph.layout?.nodes) {
        elements.forEach((el) => {
          if (el.data && !el.data.source && graph.layout.nodes[el.data.id]) {
            el.data.layout = graph.layout.nodes[el.data.id];
            el.data.role = el.data.role || el.data.network_role || graph.layout.nodes[el.data.id].layer;
          }
        });
      }

      cy = cytoscape({
        container: el,
        elements,
        style: buildStyle(),
        layout: hierarchicalLayoutConfig(elements, options),
        minZoom: 0.15,
        maxZoom: 4,
        wheelSensitivity: 0.3,
      });

      cy.on('tap', 'node', (evt) => {
        const id = evt.target.data('id');
        if (options.onNodeClick) options.onNodeClick(id, evt.target.data());
        else if (!options.compact) window.location.href = `/pages/device-detail.html?id=${id}`;
      });

      cy.on('tap', 'edge', (evt) => {
        if (options.onEdgeClick) {
          options.onEdgeClick(evt.target.data('id'), evt.target.data());
        }
      });

      cy.on('tap', (evt) => {
        if (evt.target === cy && options.onBackgroundClick) options.onBackgroundClick();
      });

      cy.on('cxttap', 'node', (evt) => {
        evt.originalEvent?.preventDefault?.();
        const id = evt.target.data('id');
        if (options.onNodeContext) options.onNodeContext(id, evt.target.data(), evt);
      });

      // Prevent browser menu on canvas when using context actions
      el.addEventListener('contextmenu', (e) => {
        if (options.onNodeContext) e.preventDefault();
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

  function fitTo(nodeId) {
    if (!cy || !nodeId) return;
    const n = cy.$id(String(nodeId));
    if (n.empty()) return;
    cy.animate({ fit: { eles: n.closedNeighborhood(), padding: 80 }, duration: 280 });
    n.select();
  }

  function setFocus(nodeId) {
    if (!cy || !nodeId) return;
    clearFocus();
    const root = cy.$id(String(nodeId));
    if (root.empty()) return;
    const neighborhood = root.closedNeighborhood();
    cy.elements().addClass('dimmed');
    neighborhood.removeClass('dimmed');
    root.addClass('focus-root');
    neighborhood.nodes().difference(root).addClass('focus-neighbor');
    neighborhood.edges().addClass('focus-edge');
  }

  function clearFocus() {
    if (!cy) return;
    cy.elements().removeClass('dimmed focus-root focus-neighbor focus-edge path-edge');
  }

  function filterNodes(idSet) {
    if (!cy) return;
    if (idSet == null) {
      cy.elements().removeClass('filtered-out');
      return;
    }
    cy.nodes().forEach((n) => {
      if (idSet.has(String(n.id()))) n.removeClass('filtered-out');
      else n.addClass('filtered-out');
    });
    cy.edges().forEach((e) => {
      const s = String(e.data('source'));
      const t = String(e.data('target'));
      if (idSet.has(s) && idSet.has(t)) e.removeClass('filtered-out');
      else e.addClass('filtered-out');
    });
  }

  function highlightPath(path) {
    if (!cy) return;
    clearFocus();
    const ids = [];
    if (Array.isArray(path)) {
      path.forEach((h) => ids.push(String(h.id || h.device_id || h)));
    } else if (path?.nodes) {
      path.nodes.forEach((h) => ids.push(String(h.id || h.device_id || h)));
    } else if (path?.hops) {
      path.hops.forEach((h) => ids.push(String(h.id || h.device_id || h)));
    }
    if (!ids.length) return;
    cy.elements().addClass('dimmed');
    ids.forEach((id) => {
      const n = cy.$id(id);
      n.removeClass('dimmed').addClass('focus-neighbor');
    });
    for (let i = 0; i < ids.length - 1; i += 1) {
      const edge = cy.edges().filter((e) => {
        const s = String(e.data('source'));
        const t = String(e.data('target'));
        return (s === ids[i] && t === ids[i + 1]) || (s === ids[i + 1] && t === ids[i]);
      });
      edge.removeClass('dimmed').addClass('path-edge');
    }
    const eles = cy.collection(ids.map((id) => cy.$id(id)));
    if (eles.nonempty()) cy.animate({ fit: { eles: eles.union(eles.connectedEdges()), padding: 60 }, duration: 280 });
  }

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

  function applyHierarchicalLayout() {
    if (!cy) return;
    const byRank = {};
    cy.nodes().forEach((n) => {
      if (n.data('isCompound')) return;
      const role = String(n.data('role') || n.data('network_role') || 'unknown').toLowerCase();
      const rankMap = {
        firewall: 0, router: 1, core: 2, distribution: 3,
        access: 4, wireless: 5, server: 6, storage: 6, unknown: 5,
      };
      const rank = rankMap[role] ?? 5;
      byRank[rank] = byRank[rank] || [];
      byRank[rank].push(n);
    });
    Object.keys(byRank).forEach((rankKey) => {
      const rank = Number(rankKey);
      const list = byRank[rankKey];
      const width = Math.max(list.length, 1);
      list.forEach((n, col) => {
        n.position({ x: (col - (width - 1) / 2) * 160, y: rank * 140 });
      });
    });
    cy.fit(undefined, 40);
  }

  function groupByRole() {
    if (!cy) return;
    // Remove previous compound groups
    cy.nodes('.role-group').forEach((n) => {
      n.children().move({ parent: null });
      n.remove();
    });
    const roles = {};
    cy.nodes().forEach((n) => {
      if (n.isParent()) return;
      const role = String(n.data('role') || n.data('network_role') || 'unknown').toLowerCase() || 'unknown';
      roles[role] = roles[role] || [];
      roles[role].push(n);
    });
    Object.entries(roles).forEach(([role, nodes]) => {
      if (nodes.length < 2) return;
      const parentId = `group-${role}`;
      cy.add({
        group: 'nodes',
        data: { id: parentId, label: role.toUpperCase(), isCompound: true, role },
        classes: 'role-group',
      });
      nodes.forEach((n) => n.move({ parent: parentId }));
    });
    applyHierarchicalLayout();
  }

  function collapseRole(role) {
    if (!cy || !role) return;
    const parent = cy.$id(`group-${String(role).toLowerCase()}`);
    if (parent.nonempty()) {
      parent.children().style('display', 'none');
      parent.style({ 'background-opacity': 0.35, label: `${String(role).toUpperCase()} (${parent.children().length})` });
    } else {
      // Without compound parent: dim nodes of that role
      cy.nodes().forEach((n) => {
        const r = String(n.data('role') || n.data('network_role') || '').toLowerCase();
        if (r === String(role).toLowerCase()) n.addClass('filtered-out');
      });
    }
  }

  function expandRole(role) {
    if (!cy) return;
    if (role) {
      const parent = cy.$id(`group-${String(role).toLowerCase()}`);
      if (parent.nonempty()) {
        parent.children().style('display', 'element');
        parent.style({ 'background-opacity': 0.15, label: String(role).toUpperCase() });
      }
      cy.nodes().forEach((n) => {
        const r = String(n.data('role') || n.data('network_role') || '').toLowerCase();
        if (r === String(role).toLowerCase()) n.removeClass('filtered-out');
      });
      return;
    }
    cy.nodes('.role-group').forEach((p) => {
      p.children().style('display', 'element');
    });
    cy.elements().removeClass('filtered-out');
  }

  function destroy() {
    stopTrafficAnimation();
    destroyMiniMap();
    if (cy) { cy.destroy(); cy = null; }
  }
  function getCy() { return cy; }

  return {
    init, fit, fitTo, relayout, destroy, getCy, resolveNodeColor, ROLE_COLORS,
    setFocus, clearFocus, filterNodes, highlightPath, applyHierarchy,
    applyHierarchicalLayout, groupByRole, collapseRole, expandRole,
  };
})();
