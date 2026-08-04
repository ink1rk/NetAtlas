/**
 * NetAtlas UI helpers — autocomplete, chips, debounce, toasts
 */
const Ui = (() => {
  function debounce(fn, ms = 250) {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  }

  function toast(message, kind = 'info') {
    let host = document.getElementById('na-toasts');
    if (!host) {
      host = document.createElement('div');
      host.id = 'na-toasts';
      host.className = 'na-toasts';
      document.body.appendChild(host);
    }
    const el = document.createElement('div');
    el.className = `na-toast na-toast--${kind}`;
    el.textContent = message;
    host.appendChild(el);
    requestAnimationFrame(() => el.classList.add('show'));
    setTimeout(() => {
      el.classList.remove('show');
      setTimeout(() => el.remove(), 250);
    }, 3200);
  }

  function highlight(text, query) {
    const raw = String(text ?? '');
    const q = String(query || '').trim();
    if (!q) return App.escapeHtml(raw);
    const esc = App.escapeHtml(raw);
    const re = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'ig');
    return esc.replace(re, '<mark>$1</mark>');
  }

  /**
   * Attach autocomplete to an input.
   * options.getSuggestions(query) -> Promise<{value,label,subtitle?,href?}[]>
   */
  function attachAutocomplete(input, options = {}) {
    const wrap = document.createElement('div');
    wrap.className = 'ac-wrap';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    input.classList.add('ac-input');
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('spellcheck', 'false');

    const list = document.createElement('div');
    list.className = 'ac-list';
    list.hidden = true;
    wrap.appendChild(list);

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

  return {
    debounce, toast, highlight, attachAutocomplete, hintChips, loadRecent, pushRecent,
  };
})();
