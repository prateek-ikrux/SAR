import axios from "axios";

/**
 * The single place that knows how the session is carried.
 *
 * Today: httpOnly cookies, same origin (Vite proxies /api to the API in dev).
 * If the frontend ever lands on a different registrable domain, cookies stop
 * working and the API switches to AUTH_TRANSPORT=bearer - at which point only
 * this file changes: drop `withCredentials`, keep the token in memory, and set
 * an Authorization header in the request interceptor.
 */
export const api = axios.create({
  baseURL: "/api",
  withCredentials: true,
  timeout: 60_000,
});

function csrfToken() {
  const match = document.cookie.split("; ").find((c) => c.startsWith("cs_csrf="));
  return match ? decodeURIComponent(match.split("=")[1]) : "";
}

const SAFE_METHODS = ["get", "head", "options"];

api.interceptors.request.use((config) => {
  if (!SAFE_METHODS.includes((config.method || "get").toLowerCase())) {
    const token = csrfToken();
    if (token) config.headers["X-CSRF-Token"] = token;
  }
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

    // There is no refresh token: a 401 means the 24 hour token has expired or
    // the account was disabled. Retrying would fail identically, so the only
    // correct move is to send the user back to sign-in.
    if ((status === 401 || status === 403) && !AUTH_PATHS.some((p) => url.startsWith(p))) {
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
