import axios from "axios";
import { clearToken, getToken } from "@/lib/authToken";

/**
 * The single place that knows how the session is carried.
 *
 * Bearer tokens, held in localStorage by @/lib/authToken. The web app and the
 * API deploy as independent containers on separate origins, where a same-site
 * session cookie cannot reach - so the token travels in an Authorization header
 * instead. Nothing here reads or writes cookies, and `withCredentials` is off:
 * no ambient credential means no CSRF token to double-submit either.
 */
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api",
  timeout: 60_000,
});

api.interceptors.request.use((config) => {
  // Read per request rather than at module load, so a sign-in or a sign-out
  // takes effect on the very next call without rebuilding the client.
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

/** Set by the auth provider so a 401 anywhere can drop the session. */
let onUnauthorized = () => {};
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

const AUTH_PATHS = ["/auth/request-code", "/auth/verify-code"];

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const url = error.config?.url || "";

    // There is no refresh token: a 401 means the 24 hour token has expired, and
    // a 403 from these endpoints means the account was deactivated. Retrying
    // would fail identically, so discard the token and send the user back to
    // sign-in. Dropping it here as well as in the handler keeps storage and the
    // in-app session from disagreeing after a reload.
    if ((status === 401 || status === 403) && !AUTH_PATHS.some((p) => url.startsWith(p))) {
      clearToken();
      onUnauthorized(status);
    }
    return Promise.reject(error);
  },
);

/** Pull a human-readable message out of a FastAPI error response. */
export function errorMessage(error, fallback = "Something went wrong.") {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
  if (error?.code === "ECONNABORTED") return "The request timed out.";
  if (!error?.response) return "Cannot reach the API. Is it running?";
  return fallback;
}
