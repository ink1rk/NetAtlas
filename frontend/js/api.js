/**
 * NetAtlas API client — base /api/v1, JWT from sessionStorage
 */
const API_BASE = '/api/v1';

const Api = (() => {
  let refreshing = null;

  function getToken() {
    return sessionStorage.getItem('access_token');
  }

  function getRefreshToken() {
    return sessionStorage.getItem('refresh_token');
  }

  async function refreshTokens() {
    if (refreshing) return refreshing;
    const rt = getRefreshToken();
    if (!rt) throw new Error((typeof I18n !== 'undefined' && I18n.t('api.no_refresh')) || 'No refresh token');

    refreshing = fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: rt }),
    }).then(async (res) => {
      refreshing = null;
      if (!res.ok) throw new Error((typeof I18n !== 'undefined' && I18n.t('api.refresh_failed')) || 'Refresh failed');
      const data = await res.json();
      sessionStorage.setItem('access_token', data.access_token);
      sessionStorage.setItem('refresh_token', data.refresh_token);
      return data;
    }).catch((err) => {
      refreshing = null;
      throw err;
    });

    return refreshing;
  }

  async function request(path, options = {}) {
    const headers = { ...options.headers };
    if (!(options.body instanceof FormData)) {
      headers['Content-Type'] = headers['Content-Type'] || 'application/json';
    }
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    let res = await fetch(`${API_BASE}${path}`, { ...options, headers });

    if (res.status === 401 && getRefreshToken() && !options._retry) {
      try {
        await refreshTokens();
        return request(path, { ...options, _retry: true });
      } catch {
        sessionStorage.clear();
        window.location.href = '/';
        throw new Error((typeof I18n !== 'undefined' && I18n.t('api.session_expired')) || 'Session expired');
      }
    }

    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try {
        const err = await res.json();
        if (typeof err.detail === 'string') msg = err.detail;
        else if (Array.isArray(err.detail)) {
          msg = err.detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
        } else if (err.error?.message) msg = err.error.message;
        else if (err.message) msg = err.message;
      } catch { /* ignore */ }
      throw new Error(msg);
    }

    if (res.status === 204) return null;
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('application/json')) return res.json();
    return res.text();
  }

  function qs(params) {
    const sp = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') sp.set(k, v);
    });
    const s = sp.toString();
    return s ? `?${s}` : '';
  }

  return {
    get: (path, params) => request(path + (params ? qs(params) : '')),
    post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) }),
    delete: (path) => request(path, { method: 'DELETE' }),

    login: (username, password) =>
      request('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
        _retry: true,
      }),

    logout: () => {
      const rt = getRefreshToken();
      if (rt) {
        return request('/auth/logout', {
          method: 'POST',
          body: JSON.stringify({ refresh_token: rt }),
          _retry: true,
        }).catch(() => {});
      }
      return Promise.resolve();
    },

    me: () => request('/auth/me'),

    healthz: () => request('/healthz'),
    readyz: () => request('/readyz'),

    listDevices: (params) => request('/devices' + qs(params)),
    deviceFacets: () => request('/devices/facets'),
    getDevice: (id) => request(`/devices/${id}`),
    getDeviceInterfaces: (id) => request(`/devices/${id}/interfaces`),
    getDeviceNeighbors: (id) => request(`/devices/${id}/neighbors`),
    getDeviceMetrics: (id) => request(`/devices/${id}/metrics`),

    search: (q, params) => request(`/search${qs({ q, ...(params || {}) })}`),
    searchSuggest: (q, limit = 8) => request(`/search/suggest${qs({ q, limit })}`),

    topologyGraph: () => request('/topology/graph'),
    cablePath: (from, to) => request('/topology/cable-path' + qs({ from_device_id: from, to_device_id: to })),
    listLinks: () => request('/links'),

    listSeeds: () => request('/discovery/seeds'),
    createSeed: (data) => request('/discovery/seeds', { method: 'POST', body: JSON.stringify(data) }),
    deleteSeed: (id) => request(`/discovery/seeds/${id}`, { method: 'DELETE' }),
    listJobs: () => request('/discovery/jobs'),
    startJob: (data) => request('/discovery/jobs', { method: 'POST', body: JSON.stringify(data || {}) }),
    getJob: (id) => request(`/discovery/jobs/${id}`),
    cancelJob: (id) => request(`/discovery/jobs/${id}/cancel`, { method: 'POST', body: '{}' }),
    retryJob: (id) => request(`/discovery/jobs/${id}/retry`, { method: 'POST', body: '{}' }),

    listSnapshots: () => request('/snapshots'),
    getSnapshot: (id) => request(`/snapshots/${id}`),
    diffSnapshots: (leftId, rightId) =>
      request('/snapshots/diff', { method: 'POST', body: JSON.stringify({ left_id: leftId, right_id: rightId }) }),

    listPrefixes: () => request('/ipam/prefixes'),
    createPrefix: (data) => request('/ipam/prefixes', { method: 'POST', body: JSON.stringify(data) }),
    listAddresses: (prefixId, params) => request(`/ipam/prefixes/${prefixId}/addresses` + qs(params || {})),
    listConflicts: () => request('/ipam/conflicts'),

    // Device Intelligence / Digital Twin
    deviceIntelligence: (id) => request(`/devices/${id}/intelligence`),
    detectDeviceRole: (id) => request(`/devices/${id}/role/detect`, { method: 'POST', body: '{}' }),
    detectAllRoles: () => request('/devices/roles/detect-all', { method: 'POST', body: '{}' }),
    overrideDeviceRole: (id, body) => request(`/devices/${id}/role`, { method: 'PATCH', body: JSON.stringify(body) }),
    updateDeviceMetadata: (id, body) => request(`/devices/${id}/metadata`, { method: 'PATCH', body: JSON.stringify(body) }),
    traceMac: (q) => request('/trace/mac' + qs({ q })),
    listVlans: () => request('/vlans'),
    getVlan: (vlanId) => request(`/vlans/${vlanId}`),
    auditTimeline: (params) => request('/audit/timeline' + qs(params || {})),
    objectHistory: (type, id) => request(`/audit/objects/${type}/${id}`),
    cableMap: () => request('/cable-map'),
    topologyLayout: () => request('/topology/layout'),
  };
})();
