/**
 * NetAtlas auth — JWT in sessionStorage
 */
const Auth = (() => {
  const KEYS = ['access_token', 'refresh_token', 'user'];

  function storeTokens(pair) {
    sessionStorage.setItem('access_token', pair.access_token);
    sessionStorage.setItem('refresh_token', pair.refresh_token);
  }

  function isAuthenticated() {
    return !!sessionStorage.getItem('access_token');
  }

  function getUser() {
    const raw = sessionStorage.getItem('user');
    return raw ? JSON.parse(raw) : null;
  }

  function setUser(user) {
    sessionStorage.setItem('user', JSON.stringify(user));
  }

  function clear() {
    KEYS.forEach((k) => sessionStorage.removeItem(k));
  }

  async function login(username, password) {
    const tokens = await Api.login(username, password);
    storeTokens(tokens);
    const user = await Api.me();
    setUser(user);
    return user;
  }

  async function logout() {
    try { await Api.logout(); } catch { /* ignore */ }
    clear();
    window.location.href = '/';
  }

  function requireAuth() {
    if (!isAuthenticated()) {
      window.location.href = '/';
      return false;
    }
    return true;
  }

  function redirectIfAuthenticated() {
    if (isAuthenticated()) {
      window.location.href = '/pages/dashboard.html';
      return true;
    }
    return false;
  }

  return { login, logout, isAuthenticated, getUser, setUser, requireAuth, redirectIfAuthenticated, clear };
})();
