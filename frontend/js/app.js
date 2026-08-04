/**
 * NetAtlas shared application shell & utilities
 */
const App = (() => {
  const ASSET_V = 'di1';
  const THEME_KEY = 'netatlas_theme';
  const SIDEBAR_KEY = 'netatlas_sidebar_collapsed';

  function navSections() {
    return [
      { section: I18n.t('nav.workspaces'), items: [
        { id: 'dashboard', label: I18n.t('ws.network'), href: '/pages/dashboard.html?ws=network', icon: 'share' },
        { id: 'cable', label: I18n.t('ws.cable'), href: '/pages/dashboard.html?ws=cable', icon: 'cable' },
        { id: 'devices', label: I18n.t('ws.inventory'), href: '/pages/dashboard.html?ws=inventory', icon: 'server' },
        { id: 'find', label: I18n.t('ws.find'), href: '/pages/dashboard.html?ws=find', icon: 'search' },
        { id: 'vlans', label: I18n.t('ws.vlans'), href: '/pages/dashboard.html?ws=vlans', icon: 'layers' },
        { id: 'ipam', label: I18n.t('ws.ipam'), href: '/pages/dashboard.html?ws=ipam', icon: 'network' },
        { id: 'monitoring', label: I18n.t('ws.monitoring'), href: '/pages/dashboard.html?ws=monitoring', icon: 'activity' },
        { id: 'snapshots', label: I18n.t('ws.snapshots'), href: '/pages/dashboard.html?ws=snapshots', icon: 'layers' },
        { id: 'backups', label: I18n.t('ws.backups'), href: '/pages/dashboard.html?ws=backups', icon: 'archive' },
      ]},
      { section: I18n.t('nav.operations'), items: [
        { id: 'discovery', label: I18n.t('nav.discovery'), href: '/pages/discovery.html', icon: 'radar' },
        { id: 'observability', label: I18n.t('nav.observability'), href: '/pages/observability.html', icon: 'shield' },
        { id: 'search', label: I18n.t('nav.search'), href: '/pages/search.html', icon: 'search' },
      ]},
      { section: I18n.t('nav.legacy'), items: [
        { id: 'devices-full', label: I18n.t('noc.open_full') + ' · ' + I18n.t('nav.devices'), href: '/pages/devices.html', icon: 'server' },
        { id: 'topology', label: I18n.t('nav.topology'), href: '/pages/topology.html', icon: 'share' },
      ]},
    ];
  }

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
    bell: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>',
    sun: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>',
    moon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>',
    command: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 3a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3 3 3 0 0 0 3-3 3 3 0 0 0-3-3H6a3 3 0 0 0-3 3 3 3 0 0 0 3 3 3 3 0 0 0 3-3V6a3 3 0 0 0-3-3 3 3 0 0 0-3 3 3 3 0 0 0 3 3h12a3 3 0 0 0 3-3 3 3 0 0 0-3-3z"/></svg>',
    zap: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
    menu: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>',
    cable: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 9h6v6H4z"/><path d="M14 9h6v6h-6z"/><path d="M10 12h4"/><circle cx="7" cy="7" r="1"/><circle cx="17" cy="17" r="1"/></svg>',
    archive: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="4" rx="1"/><path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8"/><path d="M10 12h4"/></svg>',
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
      return new Date(iso).toLocaleString(I18n.locale(), {
        month: 'short', day: 'numeric', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      });
    } catch { return iso; }
  }

  function statusBadge(status) {
    const s = (status || 'unknown').toLowerCase();
    const known = ['up', 'down', 'running', 'completed', 'failed', 'pending', 'cancelled', 'problem', 'ok', 'unknown', 'used', 'free', 'reserved'];
    const cls = known.includes(s) ? s : 'unknown';
    return `<span class="badge-status ${cls}">${escapeHtml(I18n.statusLabel(status))}</span>`;
  }

  function getTheme() {
    try {
      const saved = localStorage.getItem(THEME_KEY);
      if (saved === 'light' || saved === 'dark') return saved;
    } catch { /* ignore */ }
    return 'dark';
  }

  function applyTheme(theme) {
    const t = theme === 'light' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', t);
    document.body?.setAttribute('data-theme', t);
    try { localStorage.setItem(THEME_KEY, t); } catch { /* ignore */ }
    const btn = document.getElementById('theme-btn');
    if (btn) {
      btn.innerHTML = t === 'light' ? ICONS.moon : ICONS.sun;
      btn.setAttribute('aria-label', t === 'light' ? I18n.t('shell.theme_dark') : I18n.t('shell.theme_light'));
      btn.title = t === 'light' ? I18n.t('shell.theme_dark') : I18n.t('shell.theme_light');
    }
  }

  function toggleTheme() {
    applyTheme(getTheme() === 'dark' ? 'light' : 'dark');
  }

  function isSidebarCollapsed() {
    try { return localStorage.getItem(SIDEBAR_KEY) === '1'; } catch { return false; }
  }

  function setSidebarCollapsed(collapsed) {
    const shell = document.querySelector('.app-shell');
    if (!shell) return;
    shell.classList.toggle('is-sidebar-collapsed', collapsed);
    try { localStorage.setItem(SIDEBAR_KEY, collapsed ? '1' : '0'); } catch { /* ignore */ }
  }

  function userInitials(username) {
    const u = String(username || 'OP');
    return u.slice(0, 2).toUpperCase();
  }

  function topbarHtml(pageTitle, theme) {
    return `
      <header class="app-topbar">
        <div class="topbar-left">
          <button type="button" class="btn-na btn-menu topbar-icon-btn" id="menu-btn" aria-label="Menu">${ICONS.menu}</button>
          <button type="button" class="topbar-icon-btn" id="sidebar-collapse-btn" title="${I18n.t('shell.toggle_sidebar')}" aria-label="${I18n.t('shell.toggle_sidebar')}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/></svg>
          </button>
          <h1 class="topbar-title">${escapeHtml(pageTitle)}</h1>
        </div>
        <div class="topbar-search">
          <div class="na-search na-search--global ac-wrap">
            <span class="na-search__icon">${ICONS.search}</span>
            <input type="search" id="global-search" class="na-search__input ac-input" placeholder="${I18n.t('shell.global_search')}" autocomplete="off" />
            <span class="na-search__kbd">⌘K</span>
          </div>
        </div>
        <div class="topbar-actions">
          <button type="button" class="topbar-icon-btn" id="cmd-btn" title="${I18n.t('shell.command_palette')}" aria-label="${I18n.t('shell.command_palette')}">${ICONS.command}</button>
          <button type="button" class="topbar-icon-btn" id="quick-btn" title="${I18n.t('shell.quick_actions')}" aria-label="${I18n.t('shell.quick_actions')}">${ICONS.zap}</button>
          <div class="na-notif-anchor">
            <button type="button" class="topbar-icon-btn" id="notif-btn" title="${I18n.t('shell.notifications')}" aria-label="${I18n.t('shell.notifications')}">
              ${ICONS.bell}
              <span class="na-notif-badge" id="notif-badge" hidden>0</span>
            </button>
            <div class="na-notif-dropdown" id="notif-dropdown"></div>
          </div>
          <button type="button" class="topbar-icon-btn" id="theme-btn" aria-label="${theme === 'light' ? I18n.t('shell.theme_dark') : I18n.t('shell.theme_light')}">${theme === 'light' ? ICONS.moon : ICONS.sun}</button>
          ${I18n.langSwitcherHtml()}
          <span class="topbar-clock mono" id="clock"></span>
        </div>
      </header>
    `;
  }

  function renderShell(activePage, pageTitle) {
    const user = Auth.getUser();
    const theme = getTheme();
    const collapsed = isSidebarCollapsed();
    const navHtml = navSections().map((sec) => `
      <div class="nav-section">
        <div class="nav-section-label">${sec.section}</div>
        ${sec.items.map((item) => `
          <a href="${item.href}" class="nav-link${item.id === activePage ? ' active' : ''}" title="${escapeHtml(item.label)}">
            ${ICONS[item.icon] || ''}
            <span class="nav-link__label">${item.label}</span>
          </a>
        `).join('')}
      </div>
    `).join('');

    return `
      <div class="sidebar-backdrop" id="sidebar-backdrop"></div>
      <div class="app-shell${collapsed ? ' is-sidebar-collapsed' : ''}">
        <aside class="app-sidebar" id="app-sidebar">
          <div class="sidebar-brand">
            ${LOGO_SVG}
            <div class="sidebar-brand__text">
              <div class="sidebar-brand__name">Net<span>Atlas</span></div>
              <div class="sidebar-brand__sub">${I18n.t('shell.product_sub')}</div>
            </div>
          </div>
          <nav class="sidebar-nav" aria-label="Main">${navHtml}</nav>
          <div class="sidebar-footer">
            <div class="sidebar-user">
              <div class="sidebar-user__avatar">${escapeHtml(userInitials(user?.username))}</div>
              <div class="sidebar-user__meta">
                <div class="sidebar-user__name">${escapeHtml(user?.username || I18n.t('shell.operator'))}</div>
                <div class="sidebar-user__role">${I18n.t('shell.role_operator')}</div>
              </div>
            </div>
            <button class="btn-na btn-na-secondary" id="logout-btn" style="width:100%">${I18n.t('shell.logout')}</button>
          </div>
        </aside>
        ${topbarHtml(pageTitle, theme)}
        <main class="app-main" id="page-content"></main>
      </div>
      <div class="na-toaster" id="na-toasts" aria-live="polite" aria-atomic="true"></div>
    `;
  }

  function renderNocShell(activeWs, pageTitle) {
    const user = Auth.getUser();
    const theme = getTheme();
    const rail = typeof Noc !== 'undefined'
      ? Noc.railHtml(activeWs)
      : '';

    return `
      <div class="sidebar-backdrop" id="sidebar-backdrop"></div>
      <div class="app-shell app-shell--noc">
        <aside class="app-sidebar" id="app-sidebar">
          <div class="sidebar-brand" style="justify-content:center;padding:0;height:var(--na-topbar-h)">
            <a href="/pages/dashboard.html" title="NetAtlas">${LOGO_SVG}</a>
          </div>
          ${rail}
          <div class="sidebar-footer" style="padding:0.5rem;border-top:1px solid var(--na-border)">
            <button class="topbar-icon-btn" id="logout-btn" title="${I18n.t('shell.logout')}" aria-label="${I18n.t('shell.logout')}" style="width:100%">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
            </button>
            <div class="sidebar-user__avatar" style="margin:0.5rem auto 0" title="${escapeHtml(user?.username || '')}">${escapeHtml(userInitials(user?.username))}</div>
          </div>
        </aside>
        ${topbarHtml(pageTitle, theme)}
        <main class="app-main" id="page-content"></main>
        <footer class="noc-status-bar" id="noc-status-bar"></footer>
      </div>
      <div class="na-toaster" id="na-toasts" aria-live="polite" aria-atomic="true"></div>
    `;
  }

  function bindShellChrome({ noc = false } = {}) {
    document.getElementById('logout-btn')?.addEventListener('click', () => Auth.logout());
    document.getElementById('menu-btn')?.addEventListener('click', () => {
      document.getElementById('app-sidebar')?.classList.toggle('open');
      document.getElementById('sidebar-backdrop')?.classList.toggle('is-open');
    });
    document.getElementById('sidebar-backdrop')?.addEventListener('click', () => {
      document.getElementById('app-sidebar')?.classList.remove('open');
      document.getElementById('sidebar-backdrop')?.classList.remove('is-open');
    });
    document.getElementById('sidebar-collapse-btn')?.addEventListener('click', () => {
      if (noc) {
        document.getElementById('noc-workspace')?.classList.toggle('is-left-collapsed');
        return;
      }
      setSidebarCollapsed(!isSidebarCollapsed());
    });
    document.getElementById('theme-btn')?.addEventListener('click', toggleTheme);
    document.getElementById('cmd-btn')?.addEventListener('click', () => openCommandPalette());
    document.getElementById('quick-btn')?.addEventListener('click', () => openCommandPalette('actions'));
    document.getElementById('notif-btn')?.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleNotifications();
    });

    I18n.bindLangSwitcher(document);
    bindGlobalSearch();
    bindCommandPalette();
    if (typeof Ui !== 'undefined' && Ui.initNotifications) Ui.initNotifications();
    updateClock();
    setInterval(updateClock, 30000);
  }

  function initShell(activePage, pageTitleOrKey, renderContent) {
    if (!Auth.requireAuth()) return;
    applyTheme(getTheme());
    const pageTitle = pageTitleOrKey.startsWith('title.') || pageTitleOrKey.startsWith('nav.') || pageTitleOrKey.startsWith('ws.')
      ? I18n.t(pageTitleOrKey)
      : pageTitleOrKey;
    document.title = `${pageTitle} — NetAtlas`;
    document.body.innerHTML = renderShell(activePage, pageTitle);
    applyTheme(getTheme());
    bindShellChrome({ noc: false });

    const content = document.getElementById('page-content');
    if (renderContent) renderContent(content);
  }

  function initNocShell(workspaceId, pageTitleOrKey) {
    if (!Auth.requireAuth()) return;
    applyTheme(getTheme());
    const ws = workspaceId || App.queryParam('ws') || 'network';
    const pageTitle = pageTitleOrKey
      ? (pageTitleOrKey.startsWith('title.') || pageTitleOrKey.startsWith('ws.') ? I18n.t(pageTitleOrKey) : pageTitleOrKey)
      : I18n.t('ws.network');
    document.title = `${pageTitle} — NetAtlas NOC`;
    document.body.innerHTML = renderNocShell(ws, pageTitle);
    applyTheme(getTheme());
    bindShellChrome({ noc: true });

    const content = document.getElementById('page-content');
    if (typeof Noc !== 'undefined') {
      Noc.mount(content, { workspace: ws }).catch((err) => {
        showError(content, err.message);
      });
    }
  }

  function locateFromSearch(it) {
    Ui.pushRecent('search', it.label || it.value);
    // Prefer map selection when in NOC
    if (typeof Noc !== 'undefined' && document.getElementById('noc-workspace')) {
      const href = it.href || '';
      const m = href.match(/id=([^&]+)/);
      const id = m ? decodeURIComponent(m[1]) : null;
      if (id) {
        Noc.selectObject({ type: 'device', id, data: { id, hostname: it.label } });
        Topology.fitTo?.(id);
        return;
      }
    }
    if (it.href) {
      window.location.href = it.href;
      return;
    }
    window.location.href = `/pages/search.html?q=${encodeURIComponent(it.value || it.label)}`;
  }

  function bindGlobalSearch() {
    const input = document.getElementById('global-search');
    if (!input || typeof Ui === 'undefined') return;
    Ui.attachAutocomplete(input, {
      minChars: 1,
      delay: 200,
      emptySuggestions: async () => Ui.loadRecent('search').map((v) => ({
        value: v, label: v, subtitle: I18n.t('shell.recent'),
      })),
      getSuggestions: async (q) => {
        const data = await Api.searchSuggest(q, 8);
        return (data.suggestions || []).map((s) => ({
          value: s.label,
          label: s.label,
          subtitle: s.subtitle,
          href: s.href,
        }));
      },
      onSelect: locateFromSearch,
    });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const q = input.value.trim();
        if (!q) return;
        Ui.pushRecent('search', q);
        if (document.getElementById('noc-workspace')) {
          // filter left list
          const filter = document.getElementById('noc-filter-q');
          if (filter) {
            filter.value = q;
            filter.dispatchEvent(new Event('input', { bubbles: true }));
          }
          return;
        }
        window.location.href = `/pages/search.html?q=${encodeURIComponent(q)}`;
      }
    });
    input.closest('.na-search')?.querySelector('.na-search__kbd')?.addEventListener('click', () => openCommandPalette());
  }

  function commandItems(filterMode) {
    const nav = [];
    navSections().forEach((sec) => {
      sec.items.forEach((item) => {
        nav.push({
          group: I18n.t('cmd.navigation'),
          id: `nav-${item.id}`,
          label: item.label,
          meta: sec.section,
          icon: item.icon,
          run: () => { window.location.href = item.href; },
        });
      });
    });

    const actions = [
      {
        group: I18n.t('cmd.actions'),
        id: 'act-discovery',
        label: I18n.t('cmd.start_discovery'),
        meta: 'Discovery',
        icon: 'radar',
        run: () => { window.location.href = '/pages/discovery.html'; },
      },
      {
        group: I18n.t('cmd.actions'),
        id: 'act-topology',
        label: I18n.t('cmd.open_topology'),
        meta: 'NOC',
        icon: 'share',
        run: () => { window.location.href = '/pages/dashboard.html?ws=network'; },
      },
      {
        group: I18n.t('cmd.intelligence'),
        id: 'act-open-device',
        label: I18n.t('cmd.open_device'),
        meta: 'open device <host|ip>',
        icon: 'server',
        run: (typed) => runIntelligenceCommand('open', typed),
      },
      {
        group: I18n.t('cmd.intelligence'),
        id: 'act-find-ip',
        label: I18n.t('cmd.find_ip'),
        meta: 'find IP <addr>',
        icon: 'search',
        run: (typed) => runIntelligenceCommand('ip', typed),
      },
      {
        group: I18n.t('cmd.intelligence'),
        id: 'act-show-vlan',
        label: I18n.t('cmd.show_vlan'),
        meta: 'show VLAN <id>',
        icon: 'layers',
        run: (typed) => runIntelligenceCommand('vlan', typed),
      },
      {
        group: I18n.t('cmd.intelligence'),
        id: 'act-trace-mac',
        label: I18n.t('cmd.trace_mac'),
        meta: 'trace MAC <addr>',
        icon: 'cable',
        run: (typed) => runIntelligenceCommand('mac', typed),
      },
      {
        group: I18n.t('cmd.actions'),
        id: 'act-focus',
        label: I18n.t('noc.focus_mode'),
        meta: 'F',
        icon: 'zap',
        run: () => { closeCommandPalette(); if (typeof Noc !== 'undefined') Noc.toggleFocusMode(); },
      },
      {
        group: I18n.t('cmd.actions'),
        id: 'act-search',
        label: I18n.t('cmd.focus_search'),
        meta: '/',
        icon: 'search',
        run: () => {
          closeCommandPalette();
          document.getElementById('global-search')?.focus();
        },
      },
      {
        group: I18n.t('cmd.actions'),
        id: 'act-theme',
        label: I18n.t('cmd.toggle_theme'),
        meta: 'Theme',
        icon: 'sun',
        run: () => { toggleTheme(); closeCommandPalette(); },
      },
      {
        group: I18n.t('cmd.actions'),
        id: 'act-observability',
        label: I18n.t('cmd.open_alerts'),
        meta: 'Alerts',
        icon: 'shield',
        run: () => { window.location.href = '/pages/observability.html'; },
      },
      {
        group: I18n.t('cmd.actions'),
        id: 'act-devices',
        label: I18n.t('cmd.browse_devices'),
        meta: 'Inventory',
        icon: 'server',
        run: () => { window.location.href = '/pages/dashboard.html?ws=inventory'; },
      },
      {
        group: I18n.t('noc.future_ready'),
        id: 'fut-ai',
        label: I18n.t('noc.future.ai'),
        meta: 'Soon',
        icon: 'zap',
        run: () => { closeCommandPalette(); Noc?.showFuture?.('ai'); },
      },
      {
        group: I18n.t('noc.future_ready'),
        id: 'fut-visio',
        label: I18n.t('noc.future.visio'),
        meta: 'Soon',
        icon: 'share',
        run: () => { closeCommandPalette(); Noc?.showFuture?.('visio'); },
      },
    ];

    if (filterMode === 'actions') return actions;
    return [...actions, ...nav];
  }

  function parseCmdQuery(raw) {
    const q = String(raw || '').trim();
    const lower = q.toLowerCase();
    const patterns = [
      { kind: 'mac', re: /^(?:trace\s+mac|mac|find\s+mac)\s+(.+)$/i },
      { kind: 'ip', re: /^(?:find\s+ip|ip)\s+(.+)$/i },
      { kind: 'vlan', re: /^(?:show\s+vlan|vlan)\s+(\d+)$/i },
      { kind: 'open', re: /^(?:open\s+device|open|device)\s+(.+)$/i },
    ];
    for (const p of patterns) {
      const m = q.match(p.re);
      if (m) return { kind: p.kind, value: m[1].trim() };
    }
    // Heuristics when user types value directly
    if (/^([0-9a-f]{2}[:-]){5}[0-9a-f]{2}$/i.test(q) || /^[0-9a-f]{12}$/i.test(q)) {
      return { kind: 'mac', value: q };
    }
    if (/^\d{1,3}(?:\.\d{1,3}){3}$/.test(q)) return { kind: 'ip', value: q };
    if (/^vlan\s*\d+$/i.test(lower) || /^\d{1,4}$/.test(q)) {
      const id = q.replace(/[^\d]/g, '');
      if (id) return { kind: 'vlan', value: id };
    }
    return { kind: 'search', value: q };
  }

  async function runIntelligenceCommand(kind, typedOverride) {
    const typed = (typedOverride ?? document.getElementById('na-cmd-input')?.value ?? '').trim();
    const parsed = parseCmdQuery(typed);
    let value = '';
    if (parsed.kind === kind) value = parsed.value || '';
    else if (parsed.kind === 'search' && parsed.value) value = parsed.value;

    if (kind === 'mac') {
      const q = value || prompt(I18n.t('cmd.trace_mac'), '') || '';
      if (!q) return;
      window.location.href = `/pages/dashboard.html?ws=find&q=${encodeURIComponent(q)}`;
      return;
    }
    if (kind === 'ip') {
      const q = value || prompt(I18n.t('cmd.find_ip'), '') || '';
      if (!q) return;
      window.location.href = `/pages/dashboard.html?ws=find&q=${encodeURIComponent(q)}`;
      return;
    }
    if (kind === 'vlan') {
      const q = value || prompt(I18n.t('cmd.show_vlan'), '') || '';
      if (!q) return;
      window.location.href = `/pages/dashboard.html?ws=vlans&vlan=${encodeURIComponent(q)}`;
      return;
    }
    if (kind === 'open') {
      const q = value || prompt(I18n.t('cmd.open_device'), '') || '';
      if (!q) return;
      try {
        const res = await Api.search(q, { limit: 5 });
        const d = (res.devices || [])[0];
        if (d?.id) {
          window.location.href = `/pages/dashboard.html?ws=inventory&device=${encodeURIComponent(d.id)}`;
          return;
        }
      } catch { /* fall through */ }
      window.location.href = `/pages/search.html?q=${encodeURIComponent(q)}`;
    }
  }

  let cmdState = { open: false, active: 0, items: [], mode: 'all' };

  function openCommandPalette(mode = 'all') {
    cmdState.mode = mode;
    let root = document.getElementById('na-cmd');
    if (!root) {
      root = document.createElement('div');
      root.id = 'na-cmd';
      root.className = 'na-cmd';
      root.innerHTML = `
        <div class="na-cmd__panel" role="dialog" aria-modal="true" aria-label="${I18n.t('shell.command_palette')}">
          <div class="na-cmd__search">
            ${ICONS.search}
            <input type="text" id="na-cmd-input" placeholder="${I18n.t('cmd.placeholder')}" autocomplete="off" />
          </div>
          <div class="na-cmd__list" id="na-cmd-list"></div>
          <div class="na-cmd__footer">
            <span><kbd>↑</kbd><kbd>↓</kbd> ${I18n.t('cmd.navigate')}</span>
            <span><kbd>↵</kbd> ${I18n.t('cmd.select')}</span>
            <span><kbd>esc</kbd> ${I18n.t('cmd.close')}</span>
          </div>
        </div>
      `;
      document.body.appendChild(root);
      root.addEventListener('click', (e) => {
        if (e.target === root) closeCommandPalette();
      });
      document.getElementById('na-cmd-input')?.addEventListener('input', () => renderCommandList());
      document.getElementById('na-cmd-input')?.addEventListener('keydown', onCmdKeydown);
    }
    cmdState.open = true;
    cmdState.active = 0;
    root.classList.add('is-open');
    const input = document.getElementById('na-cmd-input');
    if (input) {
      input.value = '';
      input.focus();
    }
    renderCommandList();
  }

  function closeCommandPalette() {
    cmdState.open = false;
    document.getElementById('na-cmd')?.classList.remove('is-open');
  }

  function filteredCmdItems() {
    const raw = (document.getElementById('na-cmd-input')?.value || '').trim();
    const q = raw.toLowerCase();
    const all = commandItems(cmdState.mode);
    if (!q) return all;
    const parsed = parseCmdQuery(raw);
    const scored = all.filter((it) =>
      it.label.toLowerCase().includes(q)
      || (it.meta || '').toLowerCase().includes(q)
      || (it.group || '').toLowerCase().includes(q)
      || (parsed.kind === 'mac' && it.id === 'act-trace-mac')
      || (parsed.kind === 'ip' && it.id === 'act-find-ip')
      || (parsed.kind === 'vlan' && it.id === 'act-show-vlan')
      || (parsed.kind === 'open' && it.id === 'act-open-device')
    );
    return scored;
  }

  function renderCommandList() {
    const list = document.getElementById('na-cmd-list');
    if (!list) return;
    cmdState.items = filteredCmdItems();
    if (cmdState.active >= cmdState.items.length) cmdState.active = Math.max(0, cmdState.items.length - 1);

    if (!cmdState.items.length) {
      list.innerHTML = `<div class="na-empty" style="padding:2rem"><div class="na-empty__title">${I18n.t('cmd.empty')}</div></div>`;
      return;
    }

    let html = '';
    let lastGroup = '';
    cmdState.items.forEach((it, i) => {
      if (it.group !== lastGroup) {
        lastGroup = it.group;
        html += `<div class="na-cmd__group">${escapeHtml(it.group)}</div>`;
      }
      html += `
        <button type="button" class="na-cmd__item${i === cmdState.active ? ' is-active' : ''}" data-idx="${i}">
          <span class="na-cmd__item-icon">${ICONS[it.icon] || ICONS.zap}</span>
          <span>${escapeHtml(it.label)}</span>
          <span class="na-cmd__item-meta">${escapeHtml(it.meta || '')}</span>
        </button>
      `;
    });
    list.innerHTML = html;
    list.querySelectorAll('[data-idx]').forEach((btn) => {
      btn.addEventListener('click', () => runCmdItem(Number(btn.dataset.idx)));
    });
    list.querySelector('.is-active')?.scrollIntoView({ block: 'nearest' });
  }

  function runCmdItem(idx) {
    const it = cmdState.items[idx];
    if (!it) return;
    const typed = (document.getElementById('na-cmd-input')?.value || '').trim();
    closeCommandPalette();
    if (typeof it.run === 'function') it.run(typed);
  }

  function onCmdKeydown(e) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      cmdState.active = Math.min(cmdState.items.length - 1, cmdState.active + 1);
      renderCommandList();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      cmdState.active = Math.max(0, cmdState.active - 1);
      renderCommandList();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      runCmdItem(cmdState.active);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      closeCommandPalette();
    }
  }

  function bindCommandPalette() {
    document.addEventListener('keydown', (e) => {
      const meta = e.ctrlKey || e.metaKey;
      if (meta && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (cmdState.open) closeCommandPalette();
        else openCommandPalette();
        return;
      }
      if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const tag = (e.target?.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea' || e.target?.isContentEditable) return;
        e.preventDefault();
        document.getElementById('global-search')?.focus();
      }
      if (e.key === 'Escape') {
        closeCommandPalette();
        document.getElementById('notif-dropdown')?.classList.remove('is-open');
      }
    });
  }

  function toggleNotifications() {
    if (typeof Ui !== 'undefined' && Ui.toggleNotificationPanel) {
      Ui.toggleNotificationPanel();
    }
  }

  function updateClock() {
    const el = document.getElementById('clock');
    if (el) el.textContent = new Date().toLocaleTimeString(I18n.locale());
  }

  function showError(container, msg) {
    container.innerHTML = `<div class="alert-na error">${escapeHtml(msg)}</div>`;
  }

  function queryParam(name) {
    return new URLSearchParams(window.location.search).get(name);
  }

  function formatBps(bps) {
    if (!bps) return '—';
    if (bps >= 1e9) return `${(bps / 1e9).toFixed(1)} ${I18n.t('unit.gbps')}`;
    if (bps >= 1e6) return `${(bps / 1e6).toFixed(0)} ${I18n.t('unit.mbps')}`;
    return `${bps} ${I18n.t('unit.bps')}`;
  }

  // Apply theme ASAP for FOUC reduction when script loads after body
  try {
    const t = localStorage.getItem(THEME_KEY);
    if (t === 'light' || t === 'dark') {
      document.documentElement.setAttribute('data-theme', t);
    } else {
      document.documentElement.setAttribute('data-theme', 'dark');
    }
  } catch {
    document.documentElement.setAttribute('data-theme', 'dark');
  }

  return {
    ASSET_V, ICONS, LOGO_SVG, navSections,
    escapeHtml, formatDate, statusBadge, renderShell, renderNocShell, initShell, initNocShell,
    showError, queryParam, formatBps, updateClock,
    getTheme, applyTheme, toggleTheme, openCommandPalette, closeCommandPalette,
  };
})();
