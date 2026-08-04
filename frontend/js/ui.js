/**
 * NetAtlas UI helpers — autocomplete, chips, debounce, toasts, notifications
 */
const Ui = (() => {
  const NOTIF_KEY = 'netatlas_notifications';

  function debounce(fn, ms = 250) {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  }

  function toast(message, kind = 'info', opts = {}) {
    let host = document.getElementById('na-toasts');
    if (!host) {
      host = document.createElement('div');
      host.id = 'na-toasts';
      host.className = 'na-toaster';
      document.body.appendChild(host);
    }
    const map = { ok: 'success', error: 'danger', danger: 'danger', warn: 'warning', warning: 'warning', info: 'info', success: 'success' };
    const k = map[kind] || 'info';
    const el = document.createElement('div');
    el.className = `na-toast na-toast--${k} show`;
    el.setAttribute('role', 'status');
    const title = opts.title || ({
      success: 'OK',
      danger: 'Error',
      warning: 'Warning',
      info: 'Info',
    })[k] || 'Info';
    el.innerHTML = `
      <div class="na-toast__bar"></div>
      <div>
        <div class="na-toast__title">${App.escapeHtml(title)}</div>
        <div class="na-toast__msg">${App.escapeHtml(message)}</div>
      </div>
      <button type="button" class="na-toast__close" aria-label="Close">×</button>
    `;
    const close = () => {
      el.classList.add('is-leaving');
      setTimeout(() => el.remove(), 180);
    };
    el.querySelector('.na-toast__close')?.addEventListener('click', close);
    host.appendChild(el);
    setTimeout(close, opts.duration ?? 3600);
    return el;
  }

  function highlight(text, query) {
    const raw = String(text ?? '');
    const q = String(query || '').trim();
    if (!q) return App.escapeHtml(raw);
    const esc = App.escapeHtml(raw);
    const re = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'ig');
    return esc.replace(re, '<mark>$1</mark>');
  }

  function attachAutocomplete(input, options = {}) {
    const parent = input.parentNode;
    let wrap = input.closest('.ac-wrap');
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.className = 'ac-wrap';
      parent.insertBefore(wrap, input);
      wrap.appendChild(input);
    }
    input.classList.add('ac-input');
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('spellcheck', 'false');

    let list = wrap.querySelector('.ac-list');
    if (!list) {
      list = document.createElement('div');
      list.className = 'ac-list';
      list.hidden = true;
      wrap.appendChild(list);
    }

    let items = [];
    let active = -1;
    let open = false;

    function close() {
      open = false;
      list.hidden = true;
      list.innerHTML = '';
      active = -1;
    }

    function render() {
      if (!items.length) {
        close();
        return;
      }
      open = true;
      list.hidden = false;
      list.innerHTML = items.map((it, i) => `
        <button type="button" class="ac-item${i === active ? ' active' : ''}" data-idx="${i}">
          <span class="ac-item-label">${App.escapeHtml(it.label || it.value)}</span>
          ${it.subtitle ? `<span class="ac-item-sub">${App.escapeHtml(it.subtitle)}</span>` : ''}
        </button>
      `).join('');
    }

    async function refresh() {
      const q = input.value.trim();
      if (q.length < (options.minChars ?? 1)) {
        if (options.emptySuggestions) {
          items = await options.emptySuggestions();
          render();
        } else close();
        return;
      }
      try {
        items = (await options.getSuggestions(q)) || [];
        active = items.length ? 0 : -1;
        render();
      } catch {
        close();
      }
    }

    function choose(idx) {
      const it = items[idx];
      if (!it) return;
      if (options.onSelect) options.onSelect(it);
      else if (it.href) window.location.href = it.href;
      else input.value = it.value || it.label || '';
      close();
    }

    const onInput = debounce(refresh, options.delay ?? 220);
    input.addEventListener('input', onInput);
    input.addEventListener('focus', () => { refresh(); });
    input.addEventListener('keydown', (e) => {
      if (!open && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
        refresh();
        return;
      }
      if (!open) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        active = Math.min(items.length - 1, active + 1);
        render();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        active = Math.max(0, active - 1);
        render();
      } else if (e.key === 'Enter' && active >= 0) {
        e.preventDefault();
        choose(active);
      } else if (e.key === 'Escape') {
        close();
      }
    });
    list.addEventListener('mousedown', (e) => {
      const btn = e.target.closest('[data-idx]');
      if (!btn) return;
      e.preventDefault();
      choose(Number(btn.dataset.idx));
    });
    document.addEventListener('click', (e) => {
      if (!wrap.contains(e.target)) close();
    });

    return { refresh, close };
  }

  function hintChips(container, chips, onPick) {
    container.innerHTML = chips.map((c) => `
      <button type="button" class="hint-chip" data-value="${App.escapeHtml(c.value)}">
        ${App.escapeHtml(c.label || c.value)}
      </button>
    `).join('');
    container.querySelectorAll('.hint-chip').forEach((btn) => {
      btn.addEventListener('click', () => onPick(btn.dataset.value, btn));
    });
  }

  function recentKey(name) {
    return `netatlas_recent_${name}`;
  }

  function loadRecent(name, limit = 8) {
    try {
      const raw = JSON.parse(localStorage.getItem(recentKey(name)) || '[]');
      return Array.isArray(raw) ? raw.slice(0, limit) : [];
    } catch {
      return [];
    }
  }

  function pushRecent(name, value, limit = 8) {
    const v = String(value || '').trim();
    if (!v) return;
    const next = [v, ...loadRecent(name, limit).filter((x) => x !== v)].slice(0, limit);
    localStorage.setItem(recentKey(name), JSON.stringify(next));
  }

  /* ── Notifications ─────────────────────────────────────── */

  function loadNotifications() {
    try {
      const raw = JSON.parse(localStorage.getItem(NOTIF_KEY) || '[]');
      return Array.isArray(raw) ? raw : [];
    } catch {
      return [];
    }
  }

  function saveNotifications(list) {
    localStorage.setItem(NOTIF_KEY, JSON.stringify(list.slice(0, 50)));
  }

  function pushNotification({ title, message, kind = 'info', href = null }) {
    const item = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      title,
      message,
      kind,
      href,
      ts: new Date().toISOString(),
      read: false,
    };
    const list = [item, ...loadNotifications()];
    saveNotifications(list);
    renderNotificationBadge();
    toast(message || title, kind === 'error' ? 'error' : kind, { title });
    return item;
  }

  function unreadCount() {
    return loadNotifications().filter((n) => !n.read).length;
  }

  function renderNotificationBadge() {
    const badge = document.getElementById('notif-badge');
    if (!badge) return;
    const n = unreadCount();
    if (n > 0) {
      badge.hidden = false;
      badge.textContent = n > 99 ? '99+' : String(n);
    } else {
      badge.hidden = true;
    }
  }

  function renderNotificationPanel() {
    const drop = document.getElementById('notif-dropdown');
    if (!drop) return;
    const items = loadNotifications();
    drop.innerHTML = `
      <div class="na-notif-panel">
        <div class="na-notif-panel__header">
          <strong>${I18n.t('shell.notifications')}</strong>
          <button type="button" class="na-btn na-btn--ghost na-btn--sm" id="notif-clear">${I18n.t('shell.mark_all_read')}</button>
        </div>
        ${items.length ? items.map((n) => `
          <div class="na-notif-item${n.read ? '' : ' is-unread'}" data-id="${App.escapeHtml(n.id)}" ${n.href ? `data-href="${App.escapeHtml(n.href)}"` : ''}>
            <div class="na-notif-item__dot" style="${n.read ? 'background:var(--na-color-text-muted)' : ''}"></div>
            <div>
              <div class="na-notif-item__title">${App.escapeHtml(n.title || '')}</div>
              <div class="na-notif-item__meta">${App.escapeHtml(n.message || '')} · ${App.formatDate(n.ts)}</div>
            </div>
          </div>
        `).join('') : `<div class="na-empty" style="padding:1.5rem"><div class="na-empty__desc">${I18n.t('shell.no_notifications')}</div></div>`}
      </div>
    `;
    drop.querySelector('#notif-clear')?.addEventListener('click', (e) => {
      e.stopPropagation();
      const next = loadNotifications().map((n) => ({ ...n, read: true }));
      saveNotifications(next);
      renderNotificationBadge();
      renderNotificationPanel();
    });
    drop.querySelectorAll('.na-notif-item').forEach((el) => {
      el.addEventListener('click', () => {
        const id = el.dataset.id;
        const next = loadNotifications().map((n) => (n.id === id ? { ...n, read: true } : n));
        saveNotifications(next);
        renderNotificationBadge();
        if (el.dataset.href) window.location.href = el.dataset.href;
        else renderNotificationPanel();
      });
    });
  }

  function toggleNotificationPanel() {
    const drop = document.getElementById('notif-dropdown');
    if (!drop) return;
    const open = !drop.classList.contains('is-open');
    document.querySelectorAll('.na-notif-dropdown.is-open').forEach((d) => d.classList.remove('is-open'));
    if (open) {
      renderNotificationPanel();
      drop.classList.add('is-open');
    }
  }

  async function initNotifications() {
    renderNotificationBadge();
    document.addEventListener('click', (e) => {
      const drop = document.getElementById('notif-dropdown');
      const btn = document.getElementById('notif-btn');
      if (!drop || !drop.classList.contains('is-open')) return;
      if (drop.contains(e.target) || btn?.contains(e.target)) return;
      drop.classList.remove('is-open');
    });

    // Seed from observability if empty / refresh soft status
    try {
      const [obs, alerts] = await Promise.all([
        Api.get('/observability/status').catch(() => null),
        Api.get('/observability/alerts', { page_size: 5 }).catch(() => null),
      ]);
      const problems = obs?.triggers_in_problem ?? 0;
      if (problems > 0 && !loadNotifications().some((n) => n.id === 'seed-problems')) {
        const list = loadNotifications();
        list.unshift({
          id: 'seed-problems',
          title: I18n.t('shell.notif_problems_title'),
          message: I18n.t('dash.trigger_problems', { n: problems }),
          kind: 'warning',
          href: '/pages/observability.html',
          ts: new Date().toISOString(),
          read: false,
        });
        saveNotifications(list);
      }
      const alertItems = alerts?.items || alerts?.alerts || [];
      alertItems.slice(0, 3).forEach((a, i) => {
        const id = `alert-${a.id || i}`;
        if (loadNotifications().some((n) => n.id === id)) return;
        const list = loadNotifications();
        list.unshift({
          id,
          title: a.name || a.title || I18n.t('shell.notif_alert'),
          message: a.message || a.description || a.severity || '',
          kind: (a.severity || '').toLowerCase() === 'critical' ? 'danger' : 'warning',
          href: '/pages/observability.html',
          ts: a.created_at || a.ts || new Date().toISOString(),
          read: false,
        });
        saveNotifications(list);
      });
      renderNotificationBadge();
    } catch { /* ignore */ }
  }

  return {
    debounce, toast, highlight, attachAutocomplete, hintChips, loadRecent, pushRecent,
    pushNotification, initNotifications, toggleNotificationPanel, renderNotificationBadge,
  };
})();
