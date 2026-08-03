/**
 * NetAtlas shared application utilities
 */
const App = (() => {
  const NAV = [
    { section: 'Overview', items: [
      { id: 'dashboard', label: 'Dashboard', href: '/pages/dashboard.html', icon: 'grid' },
      { id: 'topology', label: 'Topology', href: '/pages/topology.html', icon: 'share' },
      { id: 'monitoring', label: 'Monitoring', href: '/pages/monitoring.html', icon: 'activity' },
      { id: 'observability', label: 'Observability', href: '/pages/observability.html', icon: 'shield' },
    ]},
    { section: 'Inventory', items: [
      { id: 'devices', label: 'Devices', href: '/pages/devices.html', icon: 'server' },
      { id: 'search', label: 'Search', href: '/pages/search.html', icon: 'search' },
      { id: 'ipam', label: 'IPAM', href: '/pages/ipam.html', icon: 'network' },
    ]},
    { section: 'Operations', items: [
      { id: 'discovery', label: 'Discovery', href: '/pages/discovery.html', icon: 'radar' },
      { id: 'snapshots', label: 'Snapshots', href: '/pages/snapshots.html', icon: 'layers' },
    ]},
  ];

  const ICONS = {
    grid: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>',
    share: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>',
    activity: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
    server: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>',
    search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
    network: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="2" width="6" height="6"/><rect x="2" y="16" width="6" height="6"/><rect x="16" y="16" width="6" height="6"/><line x1="12" y1="8" x2="5" y2="16"/><line x1="12" y1="8" x2="19" y2="16"/></svg>',
    radar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="12" x2="12" y2="2"/><line x1="12" y1="12" x2="18" y2="18"/></svg>',
    layers: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>',
    shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
  };

  const LOGO_SVG = '<img src="/static/brand/netatlas-mark.svg" alt="NetAtlas" class="logo-mark">';

  function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function formatDate(iso) {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString(undefined, {
        month: 'short', day: 'numeric', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      });
    } catch { return iso; }
  }

  function statusBadge(status) {
    const s = (status || 'unknown').toLowerCase();
    const cls = ['up', 'down', 'running', 'completed', 'failed', 'pending', 'cancelled', 'problem', 'ok'].includes(s) ? s : 'unknown';
    return `<span class="badge-status ${cls}">${escapeHtml(status || 'unknown')}</span>`;
  }

  function renderShell(activePage, pageTitle) {
    const user = Auth.getUser();
    const navHtml = NAV.map((sec) => `
      <div class="nav-section-label">${sec.section}</div>
      ${sec.items.map((item) => `
        <a href="${item.href}" class="nav-link${item.id === activePage ? ' active' : ''}">
          ${ICONS[item.icon] || ''}
          ${item.label}
        </a>
      `).join('')}
    `).join('');

    return `
      <div class="app-shell">
        <aside class="app-sidebar">
          <div class="sidebar-brand">
            ${LOGO_SVG}
            <span>NetAtlas</span>
          </div>
          <nav class="sidebar-nav">${navHtml}</nav>
          <div class="sidebar-footer">
            <div>${escapeHtml(user?.username || 'operator')}</div>
            <button class="btn-na" id="logout-btn" style="margin-top:0.5rem;width:100%">Sign out</button>
          </div>
        </aside>
        <header class="app-topbar">
          <h1 class="topbar-title">${escapeHtml(pageTitle)}</h1>
          <div class="topbar-actions">
            <span class="mono text-muted" id="clock"></span>
          </div>
        </header>
        <main class="app-main" id="page-content"></main>
      </div>
    `;
  }

  function initShell(activePage, pageTitle, renderContent) {
    if (!Auth.requireAuth()) return;
    document.body.innerHTML = renderShell(activePage, pageTitle);
    document.getElementById('logout-btn')?.addEventListener('click', () => Auth.logout());
    updateClock();
    setInterval(updateClock, 30000);
    const content = document.getElementById('page-content');
    if (renderContent) renderContent(content);
  }

  function updateClock() {
    const el = document.getElementById('clock');
    if (el) el.textContent = new Date().toLocaleTimeString();
  }

  function showError(container, msg) {
    container.innerHTML = `<div class="alert-na error">${escapeHtml(msg)}</div>`;
  }

  function queryParam(name) {
    return new URLSearchParams(window.location.search).get(name);
  }

  function formatBps(bps) {
    if (!bps) return '—';
    if (bps >= 1e9) return `${(bps / 1e9).toFixed(1)} Gbps`;
    if (bps >= 1e6) return `${(bps / 1e6).toFixed(0)} Mbps`;
    return `${bps} bps`;
  }

  return {
    NAV, ICONS, LOGO_SVG,
    escapeHtml, formatDate, statusBadge, renderShell, initShell,
    showError, queryParam, formatBps, updateClock,
  };
})();
