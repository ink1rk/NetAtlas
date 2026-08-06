/**
 * NetAtlas NOC — Digital Twin workspace controller
 * Map-centric ops: inspector, focus mode, context menu, timeline, status bar.
 * No backend changes — composes existing Api.* endpoints.
 */
const Noc = (() => {
  const FUTURE = {
    rack: { id: 'rack', titleKey: 'noc.future.rack', descKey: 'noc.future.rack_desc' },
    visio: { id: 'visio', titleKey: 'noc.future.visio', descKey: 'noc.future.visio_desc' },
    ai: { id: 'ai', titleKey: 'noc.future.ai', descKey: 'noc.future.ai_desc' },
    backup: { id: 'backup', titleKey: 'noc.future.backup', descKey: 'noc.future.backup_desc' },
    diff: { id: 'diff', titleKey: 'noc.future.diff', descKey: 'noc.future.diff_desc' },
  };

  let state = {
    workspace: 'network',
    selected: null, // { type, id, data }
    focusMode: false,
    bottomTab: 'all',
    inspectorTab: 'overview',
    graph: null,
    devices: [],
    events: [],
    status: {
      discoveryProgress: 0,
      devicesOnline: 0,
      devicesTotal: 0,
      lastScan: null,
      activeTasks: 0,
      wsStatus: 'idle', // idle | live | offline
    },
    filters: { q: '', vendor: '', status: '' },
    bottomCollapsed: false,
  };

  const listeners = new Set();

  function workspaces() {
    return [
      { id: 'network', label: I18n.t('ws.network'), icon: 'share', map: true },
      { id: 'cable', label: I18n.t('ws.cable'), icon: 'cable', map: true },
      { id: 'inventory', label: I18n.t('ws.inventory'), icon: 'server', map: true },
      { id: 'find', label: I18n.t('ws.find'), icon: 'search', map: true },
      { id: 'vlans', label: I18n.t('ws.vlans'), icon: 'layers', map: true },
      { id: 'ipam', label: I18n.t('ws.ipam'), icon: 'network', map: true },
      { id: 'monitoring', label: I18n.t('ws.monitoring'), icon: 'activity', map: true },
      { id: 'snapshots', label: I18n.t('ws.snapshots'), icon: 'layers', map: true },
      { id: 'backups', label: I18n.t('ws.backups'), icon: 'archive', map: true, future: true },
    ];
  }

  function emit() {
    listeners.forEach((fn) => {
      try { fn(state); } catch { /* ignore */ }
    });
  }

  function onChange(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  }

  function getState() {
    return state;
  }

  function setWorkspace(id) {
    const ws = workspaces().find((w) => w.id === id);
    if (!ws) return;
    state.workspace = id;
    const url = new URL(window.location.href);
    url.searchParams.set('ws', id);
    window.history.replaceState({}, '', url.toString());
    renderLeftPanel();
    updateWorkspaceChrome();
    if (id === 'cable' && state.selected?.type === 'device') {
      // cable mode ready for path pick
      Ui.toast(I18n.t('noc.cable_hint'), 'info', { title: I18n.t('ws.cable') });
    }
    emit();
  }

  function updateWorkspaceChrome() {
    document.querySelectorAll('.noc-rail__item[data-ws]').forEach((el) => {
      el.classList.toggle('is-active', el.dataset.ws === state.workspace);
    });
    const title = document.getElementById('noc-left-title');
    const ws = workspaces().find((w) => w.id === state.workspace);
    if (title && ws) title.textContent = ws.label;
    const badge = document.getElementById('noc-ws-badge');
    if (badge && ws) badge.textContent = ws.label;
  }

  /* ── Selection / Inspector ─────────────────────────────── */

  async function selectObject(obj, { silent = false } = {}) {
    state.selected = obj;
    state.inspectorTab = 'overview';
    openInspector(true);
    if (obj?.type === 'device' && obj.id) {
      applyFocusMode(obj.id);
      try {
        const device = await Api.getDevice(obj.id);
        state.selected = { type: 'device', id: obj.id, data: { ...obj.data, ...device } };
      } catch { /* keep graph data */ }
    } else if (obj?.type === 'link') {
      clearFocusMode();
    }
    renderInspector();
    highlightListSelection();
    if (!silent) emit();
  }

  function clearSelection() {
    state.selected = null;
    clearFocusMode();
    openInspector(false);
    renderInspector();
    highlightListSelection();
    const cy = Topology.getCy?.();
    cy?.elements().unselect();
    emit();
  }

  function openInspector(open) {
    document.getElementById('noc-workspace')?.classList.toggle('is-inspector-open', !!open);
  }

  function applyFocusMode(deviceId) {
    state.focusMode = true;
    document.getElementById('noc-map')?.classList.add('is-focus-mode');
    Topology.setFocus?.(deviceId);
  }

  function clearFocusMode() {
    state.focusMode = false;
    document.getElementById('noc-map')?.classList.remove('is-focus-mode');
    Topology.clearFocus?.();
  }

  function toggleFocusMode() {
    if (!state.selected?.id) {
      Ui.toast(I18n.t('noc.select_first'), 'warning');
      return;
    }
    if (state.focusMode) clearFocusMode();
    else applyFocusMode(state.selected.id);
    emit();
  }

  /* ── Context menu ──────────────────────────────────────── */

  function hideContextMenu() {
    document.getElementById('noc-ctx')?.classList.remove('is-open');
  }

  function showContextMenu(x, y, target) {
    let menu = document.getElementById('noc-ctx');
    if (!menu) {
      menu = document.createElement('div');
      menu.id = 'noc-ctx';
      menu.className = 'noc-ctx';
      document.body.appendChild(menu);
      document.addEventListener('click', hideContextMenu);
      window.addEventListener('blur', hideContextMenu);
    }

    const label = target?.data?.label || target?.data?.hostname || target?.id || '—';
    menu.innerHTML = `
      <div class="noc-ctx__label">${App.escapeHtml(String(label))}</div>
      <button type="button" class="noc-ctx__item" data-act="open">${I18n.t('noc.ctx.open')}</button>
      <button type="button" class="noc-ctx__item" data-act="locate">${I18n.t('noc.ctx.locate')}</button>
      <button type="button" class="noc-ctx__item" data-act="trace" ${target?.type !== 'device' ? 'disabled' : ''}>${I18n.t('noc.ctx.trace')}</button>
      <button type="button" class="noc-ctx__item" data-act="interfaces" ${target?.type !== 'device' ? 'disabled' : ''}>${I18n.t('noc.ctx.interfaces')}</button>
      <button type="button" class="noc-ctx__item" data-act="history">${I18n.t('noc.ctx.history')}</button>
      <div class="noc-ctx__sep"></div>
      <button type="button" class="noc-ctx__item" data-act="export">${I18n.t('noc.ctx.export')}</button>
      <div class="noc-ctx__sep"></div>
      <button type="button" class="noc-ctx__item" data-act="future-rack">${I18n.t('noc.future.rack')}</button>
      <button type="button" class="noc-ctx__item" data-act="future-visio">${I18n.t('noc.future.visio')}</button>
    `;

    menu.querySelectorAll('[data-act]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        hideContextMenu();
        runContextAction(btn.dataset.act, target);
      });
    });

    const pad = 8;
    const mw = 220;
    const mh = 320;
    const left = Math.min(x, window.innerWidth - mw - pad);
    const top = Math.min(y, window.innerHeight - mh - pad);
    menu.style.left = `${Math.max(pad, left)}px`;
    menu.style.top = `${Math.max(pad, top)}px`;
    menu.classList.add('is-open');
  }

  async function runContextAction(act, target) {
    if (!target) return;
    switch (act) {
      case 'open':
        await selectObject(target);
        break;
      case 'locate':
        await selectObject(target);
        Topology.fitTo?.(target.id);
        break;
      case 'trace':
        await startTracePath(target.id);
        break;
      case 'interfaces':
        await selectObject(target);
        state.inspectorTab = 'interfaces';
        renderInspector();
        break;
      case 'history':
        await selectObject(target);
        state.inspectorTab = 'history';
        renderInspector();
        state.bottomTab = 'changes';
        renderTimeline();
        break;
      case 'export':
        exportSelection(target);
        break;
      case 'future-rack':
        showFuture('rack');
        break;
      case 'future-visio':
        showFuture('visio');
        break;
      default:
        break;
    }
  }

  function exportSelection(target) {
    const payload = {
      exported_at: new Date().toISOString(),
      type: target.type,
      id: target.id,
      data: target.data || {},
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `netatlas-${target.type}-${target.id}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
    Ui.toast(I18n.t('noc.exported'), 'success');
  }

  function showFuture(key) {
    const f = FUTURE[key];
    if (!f) return;
    Ui.toast(I18n.t(f.descKey), 'info', { title: I18n.t(f.titleKey) });
    state.inspectorTab = 'future';
    openInspector(true);
    renderInspector();
  }

  let traceFrom = null;
  async function startTracePath(fromId) {
    if (!traceFrom) {
      traceFrom = fromId;
      Ui.toast(I18n.t('noc.trace_pick'), 'info', { title: I18n.t('noc.ctx.trace') });
      return;
    }
    const toId = fromId;
    const from = traceFrom;
    traceFrom = null;
    if (from === toId) {
      Ui.toast(I18n.t('noc.trace_same'), 'warning');
      return;
    }
    try {
      state.status.wsStatus = 'live';
      renderStatusBar();
      const path = await Api.cablePath(from, toId);
      Topology.highlightPath?.(path);
      Ui.toast(I18n.t('noc.trace_done'), 'success', { title: I18n.t('noc.ctx.trace') });
      await selectObject({
        type: 'path',
        id: `${from}-${toId}`,
        data: { from, to: toId, path },
      });
    } catch (err) {
      Ui.toast(err.message || I18n.t('noc.trace_fail'), 'error');
    } finally {
      state.status.wsStatus = 'idle';
      renderStatusBar();
    }
  }

  /* ── Renderers ─────────────────────────────────────────── */

  function renderLeftPanel() {
    const body = document.getElementById('noc-left-body');
    if (!body) return;
    const ws = state.workspace;

    if (ws === 'ipam') {
      renderIpamLeft(body);
      return;
    }
    if (ws === 'find') {
      renderFindLeft(body);
      return;
    }
    if (ws === 'vlans') {
      renderVlansLeft(body);
      return;
    }
    if (ws === 'cable') {
      renderCableLeft(body);
      return;
    }
    if (ws === 'snapshots') {
      renderSnapshotsLeft(body);
      return;
    }
    if (ws === 'backups') {
      body.innerHTML = futurePanelHtml();
      body.querySelector('#noc-backup-stub')?.addEventListener('click', () => showFuture('backup'));
      return;
    }
    if (ws === 'monitoring') {
      renderMonitoringLeft(body);
      return;
    }

    // network / cable / inventory — filters + device list
    const vendors = [...new Set(state.devices.map((d) => d.vendor).filter(Boolean))].slice(0, 12);
    body.innerHTML = `
      <div class="noc-filter-group">
        <div class="noc-filter-group__label">${I18n.t('noc.filters')}</div>
        <input type="search" class="form-control form-control-sm mb-2" id="noc-filter-q" placeholder="${I18n.t('shell.global_search')}" value="${App.escapeHtml(state.filters.q)}" />
        <select class="form-select form-select-sm mb-2" id="noc-filter-vendor">
          <option value="">${I18n.t('devices.vendor_ph')}</option>
          ${vendors.map((v) => `<option value="${App.escapeHtml(v)}" ${state.filters.vendor === v ? 'selected' : ''}>${App.escapeHtml(v)}</option>`).join('')}
        </select>
        <select class="form-select form-select-sm" id="noc-filter-status">
          <option value="">${I18n.t('devices.status_ph')}</option>
          <option value="up" ${state.filters.status === 'up' ? 'selected' : ''}>up</option>
          <option value="down" ${state.filters.status === 'down' ? 'selected' : ''}>down</option>
        </select>
      </div>
      <div class="noc-filter-group">
        <div class="noc-filter-group__label">${I18n.t('ws.inventory')} (${filteredDevices().length})</div>
        <div class="noc-device-list" id="noc-device-list"></div>
      </div>
      ${ws === 'cable' ? `<div class="na-hint">${I18n.t('noc.cable_hint')}</div>` : ''}
      <div class="noc-filter-group" style="margin-top:auto">
        <div class="noc-filter-group__label">${I18n.t('noc.future_ready')}</div>
        ${Object.values(FUTURE).slice(0, 3).map((f) => `
          <button type="button" class="na-quick-action" style="width:100%;margin-bottom:6px;justify-content:flex-start" data-future="${f.id}">
            ${I18n.t(f.titleKey)}
          </button>
        `).join('')}
      </div>
    `;

    body.querySelector('#noc-filter-q')?.addEventListener('input', Ui.debounce((e) => {
      state.filters.q = e.target.value;
      renderDeviceList();
      applyMapFilters();
    }, 180));
    body.querySelector('#noc-filter-vendor')?.addEventListener('change', (e) => {
      state.filters.vendor = e.target.value;
      renderDeviceList();
      applyMapFilters();
    });
    body.querySelector('#noc-filter-status')?.addEventListener('change', (e) => {
      state.filters.status = e.target.value;
      renderDeviceList();
      applyMapFilters();
    });
    body.querySelectorAll('[data-future]').forEach((btn) => {
      btn.addEventListener('click', () => showFuture(btn.dataset.future));
    });
    renderDeviceList();
  }

  function filteredDevices() {
    const q = state.filters.q.trim().toLowerCase();
    return state.devices.filter((d) => {
      if (state.filters.vendor && d.vendor !== state.filters.vendor) return false;
      if (state.filters.status && String(d.status || '').toLowerCase() !== state.filters.status) return false;
      if (!q) return true;
      const hay = `${d.hostname || ''} ${d.management_ip || ''} ${d.vendor || ''} ${d.model || ''}`.toLowerCase();
      return hay.includes(q);
    });
  }

  function renderDeviceList() {
    const list = document.getElementById('noc-device-list');
    if (!list) return;
    const items = filteredDevices().slice(0, 80);
    if (!items.length) {
      list.innerHTML = `<div class="na-empty" style="padding:1rem"><div class="na-empty__desc">${I18n.t('noc.no_devices')}</div></div>`;
      return;
    }
    list.innerHTML = items.map((d) => `
      <button type="button" class="noc-device-list__item${state.selected?.id === d.id ? ' is-active' : ''}" data-id="${App.escapeHtml(d.id)}">
        <span class="na-status ${String(d.status).toLowerCase() === 'up' ? 'na-status--up' : 'na-status--down'}"><span class="na-status__dot"></span></span>
        <span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${App.escapeHtml(d.hostname || d.id)}</span>
        <span class="noc-device-list__meta">${App.escapeHtml(d.management_ip || '')}</span>
      </button>
    `).join('');
    list.querySelectorAll('[data-id]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const d = state.devices.find((x) => String(x.id) === btn.dataset.id);
        selectObject({ type: 'device', id: d.id, data: d });
        Topology.fitTo?.(d.id);
      });
      btn.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        const d = state.devices.find((x) => String(x.id) === btn.dataset.id);
        showContextMenu(e.clientX, e.clientY, { type: 'device', id: d.id, data: d });
      });
    });
  }

  function highlightListSelection() {
    document.querySelectorAll('.noc-device-list__item').forEach((el) => {
      el.classList.toggle('is-active', el.dataset.id === String(state.selected?.id || ''));
    });
  }

  function applyMapFilters() {
    const active = state.filters.q || state.filters.vendor || state.filters.status;
    if (!active) {
      Topology.filterNodes?.(null);
      return;
    }
    Topology.filterNodes?.(new Set(filteredDevices().map((d) => String(d.id))));
  }

  function renderFindLeft(body) {
    body.innerHTML = `
      <div class="noc-filter-group">
        <div class="noc-filter-group__label">${I18n.t('noc.find_device')}</div>
        <p class="na-hint mb-2">${I18n.t('noc.find_hint')}</p>
        <input type="search" class="form-control form-control-sm mb-2" id="noc-find-q" placeholder="MAC / IP / hostname" />
        <button type="button" class="na-btn na-btn--primary na-btn--sm" style="width:100%" id="noc-find-btn">${I18n.t('noc.find_run')}</button>
      </div>
      <div id="noc-find-result"></div>
    `;
    const run = async () => {
      const q = document.getElementById('noc-find-q')?.value?.trim();
      const box = document.getElementById('noc-find-result');
      if (!q || !box) return;
      box.innerHTML = `<div class="na-empty"><div class="na-spinner"></div></div>`;
      try {
        const res = await Api.traceMac(q);
        if (!res.found) {
          box.innerHTML = `<div class="na-hint">${I18n.t('noc.find_empty')}</div>`;
          return;
        }
        box.innerHTML = `
          <div class="noc-kv">
            <div class="noc-kv__k">Device</div><div class="noc-kv__v">${App.escapeHtml(res.hostname || '—')}</div>
            <div class="noc-kv__k">MAC</div><div class="noc-kv__v">${App.escapeHtml(res.mac || '—')}</div>
            <div class="noc-kv__k">IP</div><div class="noc-kv__v">${App.escapeHtml(res.ip || '—')}</div>
            <div class="noc-kv__k">Connected</div><div class="noc-kv__v">${App.escapeHtml(res.connected_hostname || '—')}</div>
            <div class="noc-kv__k">Port</div><div class="noc-kv__v">${App.escapeHtml(res.port || '—')}</div>
            <div class="noc-kv__k">VLAN</div><div class="noc-kv__v">${App.escapeHtml(String(res.vlan_id ?? '—'))}</div>
          </div>
          <div class="na-timeline">
            ${(res.path || []).map((h, i) => `
              <div class="na-timeline__item">
                <div class="na-timeline__time">#${i + 1}</div>
                <div class="na-timeline__title">${App.escapeHtml(h.hostname || h.device_id)}</div>
                <div class="na-timeline__desc">${App.escapeHtml([h.role, h.interface].filter(Boolean).join(' · '))}</div>
              </div>
            `).join('')}
          </div>
          <button type="button" class="na-btn na-btn--secondary na-btn--sm" style="width:100%;margin-top:8px" id="noc-find-locate">${I18n.t('noc.ctx.locate')}</button>
        `;
        const focusId = res.connected_device_id || res.endpoint_device_id;
        if (focusId) {
          Topology.highlightPath?.({ hops: (res.path || []).map((h) => ({ id: h.device_id })) });
          document.getElementById('noc-find-locate')?.addEventListener('click', () => {
            selectObject({ type: 'device', id: focusId, data: { id: focusId, hostname: res.connected_hostname || res.hostname } });
            Topology.fitTo?.(focusId);
          });
        }
      } catch (err) {
        box.innerHTML = `<div class="alert-na error">${App.escapeHtml(err.message)}</div>`;
      }
    };
    document.getElementById('noc-find-btn')?.addEventListener('click', run);
    document.getElementById('noc-find-q')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') run();
    });
  }

  async function renderVlansLeft(body) {
    body.innerHTML = `<div class="na-empty"><div class="na-spinner"></div></div>`;
    try {
      const data = await Api.listVlans();
      const items = data.items || [];
      body.innerHTML = `
        <div class="noc-filter-group">
          <div class="noc-filter-group__label">${I18n.t('ws.vlans')} (${items.length})</div>
          <div class="na-tree">
            ${items.slice(0, 60).map((v) => `
              <button type="button" class="na-tree__item" data-vlan="${v.vlan_id}" style="width:100%">
                <span class="mono" style="color:var(--na-accent)">VLAN ${v.vlan_id}</span>
                <span style="margin-left:auto;font-size:10px;color:var(--na-text-muted)">${v.device_count || 0}</span>
              </button>
            `).join('') || `<div class="na-hint">${I18n.t('noc.empty')}</div>`}
          </div>
        </div>
        <div id="noc-vlan-detail"></div>
      `;
      body.querySelectorAll('[data-vlan]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const detail = document.getElementById('noc-vlan-detail');
          const vlan = items.find((x) => String(x.vlan_id) === btn.dataset.vlan);
          if (!detail || !vlan) return;
          detail.innerHTML = `
            <div class="noc-filter-group">
              <div class="noc-filter-group__label">${App.escapeHtml(vlan.name || '')}</div>
              <div class="noc-kv">
                <div class="noc-kv__k">ID</div><div class="noc-kv__v">${vlan.vlan_id}</div>
                <div class="noc-kv__k">Devices</div><div class="noc-kv__v">${vlan.device_count}</div>
                <div class="noc-kv__k">Path</div><div class="noc-kv__v">${App.escapeHtml((vlan.topology_path || []).join(' → ') || '—')}</div>
              </div>
              ${(vlan.devices || []).slice(0, 12).map((d) => `
                <button type="button" class="noc-device-list__item" data-id="${App.escapeHtml(d.id)}">
                  <span>${App.escapeHtml(d.hostname || d.id)}</span>
                  <span class="noc-device-list__meta">${App.escapeHtml(d.role || '')}</span>
                </button>
              `).join('')}
            </div>
          `;
          detail.querySelectorAll('[data-id]').forEach((b) => {
            b.addEventListener('click', () => {
              selectObject({ type: 'device', id: b.dataset.id, data: { id: b.dataset.id } });
              Topology.fitTo?.(b.dataset.id);
            });
          });
        });
      });
    } catch (err) {
      body.innerHTML = `<div class="alert-na error">${App.escapeHtml(err.message)}</div>`;
    }
  }

  async function renderCableLeft(body) {
    body.innerHTML = `<div class="na-empty"><div class="na-spinner"></div></div>`;
    try {
      const data = await Api.cableMap();
      body.innerHTML = `
        <div class="noc-filter-group">
          <div class="noc-filter-group__label">${I18n.t('ws.cable')}</div>
          <p class="na-hint mb-2">${I18n.t('noc.cable_model_hint')}</p>
          <div class="na-metric">
            <div class="na-metric__label">Inferred paths</div>
            <div class="na-metric__value" style="font-size:1.25rem">${(data.inferred_paths || []).length}</div>
          </div>
          <div class="na-metric" style="margin-top:8px">
            <div class="na-metric__label">Patch panels</div>
            <div class="na-metric__value" style="font-size:1.25rem">${(data.panels || []).length}</div>
          </div>
          <div class="na-hint" style="margin-top:12px">${I18n.t('noc.cable_hint')}</div>
        </div>
      `;
    } catch (err) {
      body.innerHTML = `<div class="alert-na error">${App.escapeHtml(err.message)}</div>`;
    }
  }

  async function renderIpamLeft(body) {
    body.innerHTML = `<div class="na-empty"><div class="na-spinner"></div></div>`;
    try {
      const prefixes = await Api.listPrefixes().catch(() => []);
      const conflicts = await Api.listConflicts().catch(() => []);
      body.innerHTML = `
        <div class="noc-filter-group">
          <div class="noc-filter-group__label">${I18n.t('ws.ipam')}</div>
          <div class="na-metric na-metric--accent" style="margin-bottom:8px">
            <div class="na-metric__label">${I18n.t('dash.prefixes')}</div>
            <div class="na-metric__value" style="font-size:1.25rem">${Array.isArray(prefixes) ? prefixes.length : 0}</div>
          </div>
          <div class="na-metric ${conflicts?.length ? 'na-metric--danger' : 'na-metric--success'}" style="margin-bottom:12px">
            <div class="na-metric__label">${I18n.t('noc.ipam_conflicts')}</div>
            <div class="na-metric__value" style="font-size:1.25rem">${Array.isArray(conflicts) ? conflicts.length : 0}</div>
          </div>
          <div class="na-tree">
            ${(Array.isArray(prefixes) ? prefixes : []).slice(0, 40).map((p) => `
              <div class="na-tree__item" data-prefix="${App.escapeHtml(p.id || p.cidr)}">
                <span class="mono" style="color:var(--na-accent)">${App.escapeHtml(p.cidr || p.prefix || p.id)}</span>
              </div>
            `).join('') || `<div class="na-hint">${I18n.t('noc.empty')}</div>`}
          </div>
          <a class="na-btn na-btn--secondary na-btn--sm" style="margin-top:12px;width:100%" href="/pages/ipam.html">${I18n.t('noc.open_full')}</a>
        </div>
      `;
    } catch (err) {
      body.innerHTML = `<div class="alert-na error">${App.escapeHtml(err.message)}</div>`;
    }
  }

  async function renderSnapshotsLeft(body) {
    body.innerHTML = `<div class="na-empty"><div class="na-spinner"></div></div>`;
    try {
      const snaps = await Api.listSnapshots().catch(() => []);
      const list = Array.isArray(snaps) ? snaps : (snaps.items || []);
      body.innerHTML = `
        <div class="noc-filter-group">
          <div class="noc-filter-group__label">${I18n.t('ws.snapshots')}</div>
          <div class="na-timeline">
            ${list.slice(0, 12).map((s) => `
              <div class="na-timeline__item">
                <div class="na-timeline__time">${App.formatDate(s.created_at || s.ts)}</div>
                <div class="na-timeline__title">${App.escapeHtml(s.label || s.name || s.id || 'snapshot')}</div>
                <div class="na-timeline__desc">${App.escapeHtml(
                  s.summary ? JSON.stringify(s.summary).slice(0, 80) : (s.description || '')
                )}</div>
              </div>
            `).join('') || `<div class="na-hint">${I18n.t('noc.empty')}</div>`}
          </div>
          <button type="button" class="na-btn na-btn--secondary na-btn--sm" style="margin-top:12px;width:100%" id="noc-snap-diff">${I18n.t('noc.compare_snaps')}</button>
          <div id="noc-snap-diff-result" style="margin-top:8px"></div>
          <a class="na-btn na-btn--ghost na-btn--sm" style="margin-top:8px;width:100%" href="/pages/snapshots.html">${I18n.t('noc.open_full')}</a>
        </div>
      `;
      document.getElementById('noc-snap-diff')?.addEventListener('click', async () => {
        const box = document.getElementById('noc-snap-diff-result');
        if (!box || list.length < 2) {
          Ui.toast(I18n.t('snap.select_two'), 'info');
          return;
        }
        box.innerHTML = `<div class="na-hint">${I18n.t('snap.computing')}</div>`;
        try {
          const diff = await Api.diffSnapshots(list[1].id, list[0].id);
          box.innerHTML = `
            <div class="noc-kv">
              <div class="noc-kv__k">ADDED</div><div class="noc-kv__v">${(diff.added || []).length}</div>
              <div class="noc-kv__k">REMOVED</div><div class="noc-kv__v">${(diff.removed || []).length}</div>
              <div class="noc-kv__k">CHANGED</div><div class="noc-kv__v">${(diff.changed || []).length}</div>
            </div>
          `;
        } catch (err) {
          box.innerHTML = `<div class="alert-na error">${App.escapeHtml(err.message)}</div>`;
        }
      });
    } catch (err) {
      body.innerHTML = `<div class="alert-na error">${App.escapeHtml(err.message)}</div>`;
    }
  }

  function renderMonitoringLeft(body) {
    body.innerHTML = `
      <div class="noc-filter-group">
        <div class="noc-filter-group__label">${I18n.t('ws.monitoring')}</div>
        <div class="na-metric na-metric--success" style="margin-bottom:8px">
          <div class="na-metric__label">${I18n.t('noc.devices_online')}</div>
          <div class="na-metric__value" style="font-size:1.25rem" id="noc-mon-online">${state.status.devicesOnline}</div>
        </div>
        <div class="na-metric na-metric--danger" style="margin-bottom:8px">
          <div class="na-metric__label">${I18n.t('dash.alerts')}</div>
          <div class="na-metric__value" style="font-size:1.25rem" id="noc-mon-alerts">—</div>
        </div>
        <p class="na-hint">${I18n.t('noc.monitoring_hint')}</p>
        <a class="na-btn na-btn--secondary na-btn--sm" style="width:100%;margin-top:8px" href="/pages/monitoring.html">${I18n.t('noc.open_full')}</a>
        <a class="na-btn na-btn--ghost na-btn--sm" style="width:100%;margin-top:8px" href="/pages/observability.html">${I18n.t('nav.observability')}</a>
      </div>
    `;
    Api.get('/observability/status').then((s) => {
      const el = document.getElementById('noc-mon-alerts');
      if (el) el.textContent = s?.triggers_in_problem ?? 0;
    }).catch(() => {});
  }

  function futurePanelHtml() {
    return `
      <div class="noc-filter-group">
        <div class="noc-filter-group__label">${I18n.t('ws.backups')}</div>
        <div class="noc-future-card">
          <div class="noc-future-card__title">${I18n.t('noc.future.backup')}</div>
          <div class="noc-future-card__desc">${I18n.t('noc.future.backup_desc')}</div>
        </div>
        <div class="noc-future-card">
          <div class="noc-future-card__title">${I18n.t('noc.future.diff')}</div>
          <div class="noc-future-card__desc">${I18n.t('noc.future.diff_desc')}</div>
        </div>
        <button type="button" class="na-btn na-btn--primary na-btn--sm" style="width:100%" id="noc-backup-stub">${I18n.t('noc.future.backup')}</button>
      </div>
    `;
  }

  async function renderInspector() {
    const body = document.getElementById('noc-inspector-body');
    const title = document.getElementById('noc-inspector-title');
    const sub = document.getElementById('noc-inspector-sub');
    const eyebrow = document.getElementById('noc-inspector-eyebrow');
    if (!body) return;

    if (!state.selected) {
      if (title) title.textContent = I18n.t('noc.inspector');
      if (sub) sub.textContent = I18n.t('noc.inspector_empty');
      if (eyebrow) eyebrow.textContent = I18n.t('noc.selection');
      body.innerHTML = `<div class="noc-inspector__empty">${I18n.t('noc.inspector_empty')}</div>`;
      return;
    }

    const sel = state.selected;
    const d = sel.data || {};
    if (eyebrow) eyebrow.textContent = sel.type;
    if (title) title.textContent = d.hostname || d.label || d.name || sel.id;
    if (sub) sub.textContent = d.management_ip || d.mgmt_ip || d.id || sel.id;

    const tabs = ['overview', 'interfaces', 'neighbors', 'history', 'future'];
    document.querySelectorAll('.noc-inspector__tab').forEach((t) => {
      t.classList.toggle('is-active', t.dataset.tab === state.inspectorTab);
    });

    if (state.inspectorTab === 'future' || sel.type === 'path' && state.inspectorTab === 'overview' && false) {
      /* fallthrough */
    }

    if (state.inspectorTab === 'future') {
      body.innerHTML = Object.values(FUTURE).map((f) => `
        <div class="noc-future-card">
          <div class="noc-future-card__title">${I18n.t(f.titleKey)}</div>
          <div class="noc-future-card__desc">${I18n.t(f.descKey)}</div>
        </div>
      `).join('');
      return;
    }

    if (sel.type === 'link') {
      body.innerHTML = `
        <div class="noc-kv">
          <div class="noc-kv__k">Source</div><div class="noc-kv__v">${App.escapeHtml(d.source || d.from || '—')}</div>
          <div class="noc-kv__k">Target</div><div class="noc-kv__v">${App.escapeHtml(d.target || d.to || '—')}</div>
          <div class="noc-kv__k">Label</div><div class="noc-kv__v">${App.escapeHtml(d.label || d.interface || '—')}</div>
        </div>
        <div class="noc-inspector__actions">
          <button type="button" class="na-btn na-btn--secondary na-btn--sm" data-act="export">${I18n.t('noc.ctx.export')}</button>
        </div>
      `;
      body.querySelector('[data-act="export"]')?.addEventListener('click', () => exportSelection(sel));
      return;
    }

    if (sel.type === 'path') {
      const hops = sel.data?.path?.hops || sel.data?.path?.nodes || sel.data?.path || [];
      body.innerHTML = `
        <div class="noc-kv">
          <div class="noc-kv__k">From</div><div class="noc-kv__v">${App.escapeHtml(sel.data.from)}</div>
          <div class="noc-kv__k">To</div><div class="noc-kv__v">${App.escapeHtml(sel.data.to)}</div>
        </div>
        <div class="na-timeline">
          ${(Array.isArray(hops) ? hops : []).map((h, i) => `
            <div class="na-timeline__item">
              <div class="na-timeline__time">#${i + 1}</div>
              <div class="na-timeline__title">${App.escapeHtml(h.hostname || h.id || h.device_id || JSON.stringify(h))}</div>
            </div>
          `).join('') || `<div class="na-hint">${I18n.t('noc.trace_done')}</div>`}
        </div>
      `;
      return;
    }

    if (state.inspectorTab === 'overview') {
      body.innerHTML = `<div class="na-empty"><div class="na-spinner"></div></div>`;
      let intel = null;
      let metrics = null;
      try { intel = await Api.deviceIntelligence(sel.id); } catch { /* fallback to basic */ }
      try { metrics = await Api.getDeviceMetrics(sel.id); } catch { /* telemetry optional */ }
      const role = intel?.role || {
        role: d.network_role || d.role || 'unknown',
        confidence: d.role_confidence || 0,
        reasons: d.role_reasons || [],
      };
      const meta = intel?.metadata || {};
      const identity = intel?.identity || d;
      const rel = intel?.relationships || {};
      const vlans = rel.vlans || [];
      const neighbors = rel.neighbors || [];
      const linkStats = rel.links || {};
      const latest = metrics?.latest || (metrics?.history || [])[metrics?.history?.length - 1] || null;
      const confidencePct = Math.round(role.confidence || 0);
      const statusOk = String(identity.status || d.status || '').toLowerCase() === 'up';

      const gauge = (label, value, unit, tone) => `
        <div class="noc-gauge noc-gauge--${tone}">
          <div class="noc-gauge__ring" style="--gauge-pct:${Math.max(0, Math.min(100, Number(value) || 0))}">
            <span>${value != null ? Math.round(value) : '—'}${value != null ? unit : ''}</span>
          </div>
          <div class="noc-gauge__label">${label}</div>
        </div>
      `;

      body.innerHTML = `
        <div class="noc-device-hero">
          <div class="noc-device-hero__icon na-card-icon" style="--na-card-accent:var(--na-card-device);width:44px;height:44px">${App.ICONS.server}</div>
          <div class="noc-device-hero__meta">
            <div class="noc-device-hero__role">
              <span class="na-status na-status--${statusOk ? 'up' : 'down'}"><span class="na-status__dot"></span>${App.escapeHtml(I18n.statusLabel(identity.status || d.status))}</span>
              <span class="na-badge na-badge--info">${App.escapeHtml(String(role.role || 'unknown'))} · ${confidencePct}%</span>
            </div>
            <div class="noc-hint-row">${(role.reasons || []).slice(0, 3).map((r) => App.escapeHtml(r)).join(' · ') || I18n.t('noc.role_auto')}</div>
          </div>
        </div>

        <div class="noc-gauge-row">
          ${gauge(I18n.t('device.cpu') || 'CPU', latest?.cpu_percent, '%', (latest?.cpu_percent || 0) > 85 ? 'danger' : (latest?.cpu_percent || 0) > 65 ? 'warning' : 'success')}
          ${gauge(I18n.t('device.memory') || 'RAM', latest?.memory_percent, '%', (latest?.memory_percent || 0) > 85 ? 'danger' : (latest?.memory_percent || 0) > 65 ? 'warning' : 'success')}
          ${gauge('°C', latest?.temperature_c, '°', (latest?.temperature_c || 0) > 70 ? 'danger' : (latest?.temperature_c || 0) > 55 ? 'warning' : 'accent')}
        </div>
        ${!latest ? `<div class="na-hint" style="margin:-6px 0 12px">${I18n.t('device.no_metrics') || 'No telemetry yet'}</div>` : ''}

        <div class="noc-kv">
          <div class="noc-kv__k">${I18n.t('common.vendor')}</div><div class="noc-kv__v">${App.escapeHtml(identity.vendor || d.vendor || '—')}</div>
          <div class="noc-kv__k">${I18n.t('common.model')}</div><div class="noc-kv__v">${App.escapeHtml(identity.model || d.model || '—')}</div>
          <div class="noc-kv__k">${I18n.t('devices.mgmt_ip')}</div><div class="noc-kv__v">${App.escapeHtml(identity.management_ip || d.management_ip || '—')}</div>
          <div class="noc-kv__k">MAC</div><div class="noc-kv__v">${App.escapeHtml(identity.management_mac || d.management_mac || '—')}</div>
          <div class="noc-kv__k">${I18n.t('device.serial')}</div><div class="noc-kv__v">${App.escapeHtml(identity.serial || d.serial || '—')}</div>
          <div class="noc-kv__k">${I18n.t('device.firmware')}</div><div class="noc-kv__v">${App.escapeHtml(identity.firmware || d.firmware || '—')}</div>
          <div class="noc-kv__k">Location</div><div class="noc-kv__v">${App.escapeHtml(meta.location || '—')}</div>
          <div class="noc-kv__k">Rack</div><div class="noc-kv__v">${App.escapeHtml(meta.rack || '—')}</div>
          <div class="noc-kv__k">Owner</div><div class="noc-kv__v">${App.escapeHtml(meta.owner || '—')}</div>
          <div class="noc-kv__k">${I18n.t('device.last_seen')}</div><div class="noc-kv__v">${App.formatDate(intel?.lifecycle?.last_seen_at || d.last_seen_at)}</div>
        </div>

        <div class="noc-section-card na-card--interface">
          <div class="noc-section-card__head"><span class="na-card-icon" style="--na-card-accent:var(--na-card-interface);width:24px;height:24px">${App.ICONS.layers}</span>${I18n.t('ws.vlans')} (${vlans.length})</div>
          <div class="noc-vlan-chips">
            ${vlans.slice(0, 10).map((v) => `<span class="na-chip">VLAN ${App.escapeHtml(String(v.vlan_id))}${v.name ? ' · ' + App.escapeHtml(v.name) : ''}</span>`).join('') || `<span class="na-hint">${I18n.t('noc.empty')}</span>`}
          </div>
        </div>

        <div class="noc-section-card na-card--link">
          <div class="noc-section-card__head"><span class="na-card-icon" style="--na-card-accent:var(--na-card-link);width:24px;height:24px">${App.ICONS.share}</span>${I18n.t('noc.tab.neighbors')} · ${I18n.t('noc.mini_topo') || 'Mini Topology'}</div>
          <div class="noc-mini-topo">
            <div class="noc-mini-topo__center" title="${App.escapeHtml(identity.hostname || d.hostname || '')}">${App.ICONS.server}</div>
            <div class="noc-mini-topo__links">
              ${neighbors.slice(0, 6).map(() => `<span class="noc-mini-topo__line"></span>`).join('')}
            </div>
            <div class="noc-mini-topo__nodes">
              ${neighbors.slice(0, 6).map((n) => `<span class="noc-mini-topo__node" title="${App.escapeHtml(n.remote_hostname || n.protocol || 'neighbor')}"></span>`).join('') || `<span class="na-hint">${I18n.t('noc.empty')}</span>`}
            </div>
          </div>
          <div class="na-hint" style="margin-top:8px">${neighbors.length} ${I18n.t('noc.tab.neighbors').toLowerCase()} · ${linkStats.links || 0} links · ${linkStats.trunk_links || 0} trunk</div>
        </div>

        <div class="noc-inspector__actions">
          <button type="button" class="na-btn na-btn--primary na-btn--sm" data-act="focus">${state.focusMode ? I18n.t('noc.clear_focus') : I18n.t('noc.focus_mode')}</button>
          <button type="button" class="na-btn na-btn--secondary na-btn--sm" data-act="detect">${I18n.t('noc.detect_role')}</button>
          <button type="button" class="na-btn na-btn--secondary na-btn--sm" data-act="trace">${I18n.t('noc.ctx.trace')}</button>
          <button type="button" class="na-btn na-btn--secondary na-btn--sm" data-act="export">${I18n.t('noc.ctx.export')}</button>
          <button type="button" class="na-btn na-btn--ghost na-btn--sm" data-act="full">${I18n.t('noc.open_full')}</button>
        </div>
      `;
      body.querySelector('[data-act="focus"]')?.addEventListener('click', toggleFocusMode);
      body.querySelector('[data-act="detect"]')?.addEventListener('click', async () => {
        try {
          const r = await Api.detectDeviceRole(sel.id);
          Ui.toast(`${r.auto_detected_role} · ${r.confidence}%`, 'success', { title: I18n.t('noc.detect_role') });
          renderInspector();
        } catch (err) { Ui.toast(err.message, 'error'); }
      });
      body.querySelector('[data-act="trace"]')?.addEventListener('click', () => startTracePath(sel.id));
      body.querySelector('[data-act="export"]')?.addEventListener('click', () => exportSelection(sel));
      body.querySelector('[data-act="full"]')?.addEventListener('click', () => {
        window.location.href = `/pages/device-detail.html?id=${encodeURIComponent(sel.id)}`;
      });
      return;
    }

    if (state.inspectorTab === 'interfaces') {
      body.innerHTML = `<div class="na-empty"><div class="na-spinner"></div></div>`;
      try {
        const ifaces = await Api.getDeviceInterfaces(sel.id);
        const items = Array.isArray(ifaces) ? ifaces : (ifaces.items || []);
        body.innerHTML = items.length ? `
          <div class="na-table-wrap"><table class="na-table">
            <thead><tr><th>Name</th><th>Status</th><th>Speed</th></tr></thead>
            <tbody>
              ${items.slice(0, 40).map((i) => `
                <tr>
                  <td class="mono">${App.escapeHtml(i.name || i.if_name || '—')}</td>
                  <td>${App.statusBadge(i.oper_status || i.status || 'unknown')}</td>
                  <td class="mono">${App.escapeHtml(String(i.speed || i.speed_mbps || '—'))}</td>
                </tr>
              `).join('')}
            </tbody>
          </table></div>
        ` : `<div class="na-hint">${I18n.t('noc.empty')}</div>`;
      } catch (err) {
        body.innerHTML = `<div class="alert-na error">${App.escapeHtml(err.message)}</div>`;
      }
      return;
    }

    if (state.inspectorTab === 'neighbors') {
      body.innerHTML = `<div class="na-empty"><div class="na-spinner"></div></div>`;
      try {
        const neigh = await Api.getDeviceNeighbors(sel.id);
        const items = Array.isArray(neigh) ? neigh : (neigh.items || []);
        body.innerHTML = items.length ? items.map((n) => `
          <button type="button" class="noc-device-list__item" data-nid="${App.escapeHtml(n.remote_device_id || n.device_id || '')}">
            <span>${App.escapeHtml(n.remote_hostname || n.hostname || n.remote_id || 'neighbor')}</span>
            <span class="noc-device-list__meta">${App.escapeHtml(n.local_interface || n.interface || '')}</span>
          </button>
        `).join('') : `<div class="na-hint">${I18n.t('noc.empty')}</div>`;
        body.querySelectorAll('[data-nid]').forEach((btn) => {
          if (!btn.dataset.nid) return;
          btn.addEventListener('click', () => {
            selectObject({ type: 'device', id: btn.dataset.nid, data: { id: btn.dataset.nid } });
            Topology.fitTo?.(btn.dataset.nid);
          });
        });
      } catch (err) {
        body.innerHTML = `<div class="alert-na error">${App.escapeHtml(err.message)}</div>`;
      }
      return;
    }

    if (state.inspectorTab === 'history') {
      body.innerHTML = `<div class="na-empty"><div class="na-spinner"></div></div>`;
      try {
        const hist = await Api.objectHistory('device', sel.id);
        const life = hist.lifecycle || {};
        const changes = hist.changes || [];
        body.innerHTML = `
          <div class="noc-kv">
            <div class="noc-kv__k">Created</div><div class="noc-kv__v">${App.formatDate(life.created_at)}</div>
            <div class="noc-kv__k">First seen</div><div class="noc-kv__v">${App.formatDate(life.first_seen_at)}</div>
            <div class="noc-kv__k">Last seen</div><div class="noc-kv__v">${App.formatDate(life.last_seen_at)}</div>
            <div class="noc-kv__k">Firmware</div><div class="noc-kv__v">${App.escapeHtml(life.firmware || '—')}</div>
          </div>
          ${changes.length ? changes.map((c) => `
            <div class="noc-event-row">
              <div class="noc-event-row__time">${App.escapeHtml(formatTime(c.ts))}</div>
              <div class="noc-event-row__kind noc-event-row__kind--change">${App.escapeHtml(c.action || 'change')}</div>
              <div class="noc-event-row__msg">${App.escapeHtml(JSON.stringify(c.details || {}))}</div>
              <div></div>
            </div>
          `).join('') : `<div class="na-hint">${I18n.t('noc.history_placeholder')}</div>`}
        `;
      } catch {
        body.innerHTML = `<div class="na-hint">${I18n.t('noc.history_placeholder')}</div>`;
      }
    }
  }

  function eventRowHtml(e) {
    const kind = e.kind || 'change';
    return `
      <div class="noc-event-row" data-device="${App.escapeHtml(e.device_id || '')}">
        <div class="noc-event-row__time">${App.escapeHtml(formatTime(e.ts || e.created_at))}</div>
        <div class="noc-event-row__kind noc-event-row__kind--${App.escapeHtml(kind)}">${App.escapeHtml(kind)}</div>
        <div class="noc-event-row__msg">${App.escapeHtml(e.message || e.title || e.name || '—')}</div>
        <div>${e.severity ? App.statusBadge(e.severity) : ''}</div>
      </div>
    `;
  }

  function formatTime(iso) {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleTimeString(I18n.locale(), { hour: '2-digit', minute: '2-digit' });
    } catch { return '—'; }
  }

  function renderTimeline() {
    const body = document.getElementById('noc-bottom-body');
    if (!body) return;
    document.querySelectorAll('.noc-bottom__tab').forEach((t) => {
      t.classList.toggle('is-active', t.dataset.tab === state.bottomTab);
    });
    let items = state.events;
    if (state.bottomTab !== 'all') {
      items = items.filter((e) => e.kind === state.bottomTab);
    }
    if (!items.length) {
      body.innerHTML = `<div class="na-empty" style="padding:1rem"><div class="na-empty__desc">${I18n.t('noc.empty')}</div></div>`;
      return;
    }
    body.innerHTML = items.slice(0, 60).map(eventRowHtml).join('');
    body.querySelectorAll('.noc-event-row[data-device]').forEach((row) => {
      row.addEventListener('click', () => {
        if (!row.dataset.device) return;
        selectObject({ type: 'device', id: row.dataset.device, data: { id: row.dataset.device } });
        Topology.fitTo?.(row.dataset.device);
      });
    });
  }

  function renderStatusBar() {
    const el = document.getElementById('noc-status-bar');
    if (!el) return;
    const s = state.status;
    const wsCls = s.wsStatus === 'live' ? 'is-live' : s.wsStatus === 'offline' ? 'is-err' : 'is-ok';
    el.innerHTML = `
      <span class="noc-status-bar__item">
        <span class="noc-status-bar__dot ${s.discoveryProgress > 0 && s.discoveryProgress < 100 ? 'is-live' : 'is-ok'}"></span>
        ${I18n.t('noc.status.discovery')}
        <div class="noc-progress" title="${s.discoveryProgress}%"><div class="noc-progress__bar" style="width:${Math.min(100, s.discoveryProgress)}%"></div></div>
        <strong>${s.discoveryProgress}%</strong>
      </span>
      <span class="noc-status-bar__item">
        <span class="noc-status-bar__dot is-ok"></span>
        ${I18n.t('noc.status.online')}
        <strong>${s.devicesOnline}/${s.devicesTotal}</strong>
      </span>
      <span class="noc-status-bar__item">
        ${I18n.t('noc.status.last_scan')}
        <strong>${s.lastScan ? App.formatDate(s.lastScan) : '—'}</strong>
      </span>
      <span class="noc-status-bar__item">
        ${I18n.t('noc.status.tasks')}
        <strong>${s.activeTasks}</strong>
      </span>
      <span class="noc-status-bar__spacer"></span>
      <span class="noc-status-bar__item">
        <span class="noc-status-bar__dot ${wsCls}"></span>
        ${I18n.t('noc.status.ws')}
        <strong>${I18n.t(`noc.ws_${s.wsStatus}`)}</strong>
      </span>
    `;
  }

  /* ── Data load ─────────────────────────────────────────── */

  async function refreshData() {
    state.status.wsStatus = 'live';
    renderStatusBar();
    try {
      const [devicesPage, graph, jobs, alerts, snaps, obs, audit] = await Promise.all([
        Api.listDevices({ page_size: 200 }).catch(() => ({ items: [], total: 0 })),
        Api.topologyGraph().catch(() => ({ nodes: [], edges: [] })),
        Api.listJobs().catch(() => []),
        Api.get('/observability/alerts', { page_size: 20 }).catch(() => null),
        Api.listSnapshots().catch(() => []),
        Api.get('/observability/status').catch(() => null),
        Api.auditTimeline({ limit: 30 }).catch(() => ({ items: [] })),
      ]);

      state.devices = devicesPage.items || [];
      state.graph = graph;
      state.status.devicesTotal = devicesPage.total ?? state.devices.length;
      state.status.devicesOnline = state.devices.filter((d) => String(d.status).toLowerCase() === 'up').length;

      const jobList = Array.isArray(jobs) ? jobs : (jobs.items || []);
      const running = jobList.filter((j) => ['running', 'pending', 'queued'].includes(String(j.status).toLowerCase()));
      state.status.activeTasks = running.length;
      const latest = jobList[0];
      if (latest) {
        state.status.lastScan = latest.finished_at || latest.started_at || latest.created_at;
        const st = String(latest.status || '').toLowerCase();
        if (st === 'running') state.status.discoveryProgress = Number(latest.progress ?? 45);
        else if (st === 'completed') state.status.discoveryProgress = 100;
        else if (st === 'pending' || st === 'queued') state.status.discoveryProgress = 10;
        else state.status.discoveryProgress = latest.progress != null ? Number(latest.progress) : 0;
      }

      const alertItems = alerts?.items || alerts?.alerts || [];
      const snapList = Array.isArray(snaps) ? snaps : (snaps.items || []);

      const auditItems = audit?.items || audit?.events || (Array.isArray(audit) ? audit : []);
      state.events = [
        ...jobList.slice(0, 15).map((j) => ({
          kind: 'discovery',
          ts: j.finished_at || j.started_at || j.created_at,
          message: `${j.status || 'job'} — ${j.config?.scan_mode || j.seed_cidr || j.name || j.id || 'discovery'}`,
          device_id: null,
        })),
        ...snapList.slice(0, 10).map((s) => ({
          kind: 'snapshot',
          ts: s.created_at || s.ts,
          message: s.label || s.name || s.id || 'snapshot',
          device_id: null,
        })),
        ...alertItems.slice(0, 15).map((a) => ({
          kind: 'alert',
          ts: a.created_at || a.ts,
          message: a.name || a.title || a.message || 'alert',
          device_id: a.device_id,
          severity: a.severity,
        })),
        ...auditItems.slice(0, 20).map((e) => ({
          kind: e.kind === 'snapshot' ? 'snapshot' : 'change',
          ts: e.ts || e.created_at,
          message: e.message || e.action || e.summary || 'change',
          device_id: e.resource_type === 'device' ? e.resource_id : (e.object_id || e.device_id || null),
        })),
        ...state.devices.filter((d) => d.updated_at || d.last_seen_at).slice(0, 10).map((d) => ({
          kind: 'change',
          ts: d.updated_at || d.last_seen_at,
          message: `${d.hostname || d.id} — ${d.status || 'updated'}`,
          device_id: d.id,
        })),
        {
          kind: 'backup',
          ts: null,
          message: I18n.t('noc.future.backup_desc'),
          device_id: null,
        },
      ].sort((a, b) => new Date(b.ts || 0) - new Date(a.ts || 0));

      if (obs?.triggers_in_problem != null) {
        /* status already covered */
      }

      renderLeftPanel();
      renderTimeline();
      state.status.wsStatus = 'idle';
      renderStatusBar();
      return { graph, devices: state.devices };
    } catch (err) {
      state.status.wsStatus = 'offline';
      renderStatusBar();
      throw err;
    }
  }

  /* ── Mount NOC workspace into page content ─────────────── */

  function workspaceHtml() {
    return `
      <div class="noc-workspace" id="noc-workspace">
        <aside class="noc-left" id="noc-left">
          <div class="noc-left__header">
            <h2 class="noc-left__title" id="noc-left-title">${I18n.t('ws.network')}</h2>
            <button type="button" class="topbar-icon-btn" id="noc-left-close" title="${I18n.t('cmd.close')}" aria-label="${I18n.t('cmd.close')}">×</button>
          </div>
          <div class="noc-left__body" id="noc-left-body"></div>
        </aside>

        <section class="noc-map" id="noc-map" aria-label="${I18n.t('dash.live_map')}">
          <div class="noc-map__toolbar">
            <div class="noc-map__badge"><span class="live-dot"></span> ${I18n.t('dash.live_map')}</div>
            <span class="noc-map__badge" id="noc-ws-badge">${I18n.t('ws.network')}</span>
            <button type="button" class="na-btn na-btn--secondary na-btn--sm" id="noc-btn-fit">${I18n.t('topo.fit')}</button>
            <button type="button" class="na-btn na-btn--secondary na-btn--sm" id="noc-btn-hierarchy">${I18n.t('topo.hierarchy')}</button>
            <button type="button" class="na-btn na-btn--secondary na-btn--sm" id="noc-btn-group">${I18n.t('topo.group')}</button>
            <button type="button" class="na-btn na-btn--secondary na-btn--sm" id="noc-btn-relayout">${I18n.t('topo.relayout')}</button>
            <button type="button" class="na-btn na-btn--ghost na-btn--sm" id="noc-btn-focus">${I18n.t('noc.focus_mode')}</button>
            <button type="button" class="na-btn na-btn--ghost na-btn--sm" id="noc-btn-filters">${I18n.t('noc.filters')}</button>
          </div>
          <div id="noc-cy" class="noc-map__canvas"></div>
          <div class="noc-map__hint">${I18n.t('noc.map_hint')}</div>
        </section>

        <aside class="noc-inspector" id="noc-inspector" aria-label="${I18n.t('noc.inspector')}">
          <div class="noc-inspector__header">
            <div>
              <div class="noc-inspector__eyebrow" id="noc-inspector-eyebrow">${I18n.t('noc.selection')}</div>
              <h2 class="noc-inspector__title" id="noc-inspector-title">${I18n.t('noc.inspector')}</h2>
              <div class="noc-inspector__sub" id="noc-inspector-sub">${I18n.t('noc.inspector_empty')}</div>
            </div>
            <button type="button" class="topbar-icon-btn" id="noc-inspector-close" aria-label="${I18n.t('cmd.close')}">×</button>
          </div>
          <div class="noc-inspector__tabs">
            <button type="button" class="noc-inspector__tab is-active" data-tab="overview">${I18n.t('noc.tab.overview')}</button>
            <button type="button" class="noc-inspector__tab" data-tab="interfaces">${I18n.t('noc.tab.interfaces')}</button>
            <button type="button" class="noc-inspector__tab" data-tab="neighbors">${I18n.t('noc.tab.neighbors')}</button>
            <button type="button" class="noc-inspector__tab" data-tab="history">${I18n.t('noc.tab.history')}</button>
            <button type="button" class="noc-inspector__tab" data-tab="future">${I18n.t('noc.tab.more')}</button>
          </div>
          <div class="noc-inspector__body" id="noc-inspector-body">
            <div class="noc-inspector__empty">${I18n.t('noc.inspector_empty')}</div>
          </div>
        </aside>

        <section class="noc-bottom" id="noc-bottom">
          <div class="noc-bottom__header">
            <div class="noc-bottom__tabs">
              <button type="button" class="noc-bottom__tab is-active" data-tab="all">${I18n.t('noc.tl.all')}</button>
              <button type="button" class="noc-bottom__tab" data-tab="discovery">${I18n.t('noc.tl.discovery')}</button>
              <button type="button" class="noc-bottom__tab" data-tab="snapshot">${I18n.t('noc.tl.snapshot')}</button>
              <button type="button" class="noc-bottom__tab" data-tab="change">${I18n.t('noc.tl.changes')}</button>
              <button type="button" class="noc-bottom__tab" data-tab="alert">${I18n.t('noc.tl.alerts')}</button>
              <button type="button" class="noc-bottom__tab" data-tab="backup">${I18n.t('noc.tl.backups')}</button>
            </div>
            <button type="button" class="na-btn na-btn--ghost na-btn--sm" id="noc-bottom-toggle">${I18n.t('noc.collapse')}</button>
          </div>
          <div class="noc-bottom__body" id="noc-bottom-body"></div>
        </section>
      </div>
    `;
  }

  function bindWorkspaceUi() {
    document.querySelectorAll('.noc-rail__item[data-ws]').forEach((el) => {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        setWorkspace(el.dataset.ws);
      });
    });

    document.getElementById('noc-inspector-close')?.addEventListener('click', clearSelection);
    document.getElementById('noc-left-close')?.addEventListener('click', () => {
      document.getElementById('noc-workspace')?.classList.remove('is-left-open-mobile');
    });
    document.getElementById('noc-btn-filters')?.addEventListener('click', () => {
      document.getElementById('noc-workspace')?.classList.toggle('is-left-open-mobile');
    });
    document.getElementById('noc-btn-fit')?.addEventListener('click', () => Topology.fit());
    document.getElementById('noc-btn-hierarchy')?.addEventListener('click', () => {
      Topology.expandRole?.();
      Topology.applyHierarchicalLayout?.();
    });
    document.getElementById('noc-btn-group')?.addEventListener('click', () => Topology.groupByRole?.());
    document.getElementById('noc-btn-relayout')?.addEventListener('click', () => Topology.relayout());
    document.getElementById('noc-btn-focus')?.addEventListener('click', toggleFocusMode);
    document.getElementById('noc-bottom-toggle')?.addEventListener('click', () => {
      state.bottomCollapsed = !state.bottomCollapsed;
      document.getElementById('noc-workspace')?.classList.toggle('is-bottom-collapsed', state.bottomCollapsed);
    });

    document.querySelectorAll('.noc-inspector__tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        state.inspectorTab = tab.dataset.tab;
        renderInspector();
      });
    });
    document.querySelectorAll('.noc-bottom__tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        state.bottomTab = tab.dataset.tab;
        renderTimeline();
      });
    });

    // Esc clears selection / focus
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        hideContextMenu();
        if (state.focusMode) clearFocusMode();
      }
    });
  }

  async function applyDeepLinks() {
    const q = App.queryParam('q');
    const vlan = App.queryParam('vlan');
    const device = App.queryParam('device');
    if (device) {
      await selectObject({ type: 'device', id: device, data: { id: device } });
      Topology.fitTo?.(device);
    }
    if (state.workspace === 'find' && q) {
      const input = document.getElementById('noc-find-q');
      if (input) {
        input.value = q;
        document.getElementById('noc-find-btn')?.click();
      }
    }
    if (state.workspace === 'vlans' && vlan) {
      const btn = document.querySelector(`[data-vlan="${CSS.escape(vlan)}"]`);
      btn?.click();
    }
  }

  async function mount(container, options = {}) {
    const wsParam = App.queryParam('ws') || options.workspace || 'network';
    state.workspace = workspaces().some((w) => w.id === wsParam) ? wsParam : 'network';

    container.innerHTML = workspaceHtml();
    // status bar lives in shell
    bindWorkspaceUi();
    updateWorkspaceChrome();
    renderStatusBar();
    renderInspector();

    // Best-effort role enrichment for hierarchical map
    try { await Api.detectAllRoles(); } catch { /* optional */ }
    const data = await refreshData();
    await Topology.init('noc-cy', {
      graph: data.graph,
      compact: false,
      minimap: true,
      padding: 40,
      onNodeClick: (id, dataNode) => {
        if (state.workspace === 'cable' && traceFrom) {
          startTracePath(id);
          return;
        }
        if (state.workspace === 'cable' && !traceFrom) {
          startTracePath(id);
          return;
        }
        selectObject({ type: 'device', id, data: dataNode });
      },
      onEdgeClick: (id, dataEdge) => {
        selectObject({ type: 'link', id, data: dataEdge });
      },
      onNodeContext: (id, dataNode, evt) => {
        const oe = evt?.originalEvent;
        showContextMenu(oe?.clientX || 0, oe?.clientY || 0, { type: 'device', id, data: dataNode });
      },
      onBackgroundClick: () => clearSelection(),
    });

    await applyDeepLinks();

    // Poll status periodically (no websocket backend — simulate ops status)
    setInterval(() => {
      refreshData().catch(() => {});
    }, 60000);

    return state;
  }

  function railHtml(activeWs) {
    return `
      <div class="noc-rail" role="navigation" aria-label="Workspaces">
        ${workspaces().map((w) => `
          <a href="/pages/dashboard.html?ws=${w.id}" class="noc-rail__item${w.id === activeWs ? ' is-active' : ''}${w.future ? ' is-future' : ''}" data-ws="${w.id}" title="${App.escapeHtml(w.label)}" aria-label="${App.escapeHtml(w.label)}">
            ${App.ICONS[w.icon] || App.ICONS.share}
          </a>
        `).join('')}
        <div class="noc-rail__sep"></div>
        <a href="/pages/discovery.html" class="noc-rail__item" title="${I18n.t('nav.discovery')}" aria-label="${I18n.t('nav.discovery')}">${App.ICONS.radar}</a>
        <a href="/pages/search.html" class="noc-rail__item" title="${I18n.t('nav.search')}" aria-label="${I18n.t('nav.search')}">${App.ICONS.search}</a>
      </div>
    `;
  }

  return {
    FUTURE, workspaces, mount, railHtml, setWorkspace, selectObject, clearSelection,
    toggleFocusMode, showContextMenu, showFuture, refreshData, getState, onChange,
    renderStatusBar,
  };
})();
