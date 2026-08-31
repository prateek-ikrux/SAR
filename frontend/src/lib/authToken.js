const STORAGE_KEY = "candidate-search-auth";

/**
 * The access token, kept in localStorage.
 *
 * A deliberate trade. An httpOnly cookie keeps the token out of reach of
 * JavaScript entirely, but it only survives when the web app and the API are
 * same-site - and these two ship as independent containers on separate origins.
 * The cost of this approach is real: any XSS bug in this app can read the token
 * and use it for up to 24 hours. Treat `dangerouslySetInnerHTML` and every new
 * dependency accordingly.
 *
 * The expiry is stored alongside the token because there is no refresh
 * endpoint. Once the 24 hour token lapses the only move is a fresh sign-in, so
 * knowing it locally saves a guaranteed-401 round trip on every page load.
 *
 * Every access is guarded, and falls back to a module variable: localStorage
 * throws outright in some privacy modes, and a storage failure should cost the
 * user persistence across reloads - not the ability to sign in at all.
 */

let fallback = null;

function read() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    // Unreadable or malformed - fall through to the in-memory copy.
  }
  return fallback;
}

export function getToken() {
  const stored = read();
  if (!stored?.accessToken) return null;

  // Treat an expired token as absent rather than sending it and waiting for the
  // 401. `expiresAt` is the server's own value from the sign-in response.
  if (stored.expiresAt && Date.parse(stored.expiresAt) <= Date.now()) {
    clearToken();
    return null;
  }
  return stored.accessToken;
}

/** Takes the sign-in response body as-is. */
export function setToken({ access_token: accessToken, expires_at: expiresAt }) {
  if (!accessToken) return;
  fallback = { accessToken, expiresAt };
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(fallback));
  } catch {
    // Storage unavailable (private mode, quota, disabled). The session lives in
    // `fallback` for this page load; it just will not survive a reload.
  }
}

export function clearToken() {
  fallback = null;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to do - the token is already unreachable.
  }
}
