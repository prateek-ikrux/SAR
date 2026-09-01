# Candidate Search — web app

React + Vite client for the ikrux Candidate Search API. Recruiters describe who
they are looking for in plain language; the API runs vector search over the
resume corpus and this app presents the results.

**This is a standalone client.** It has no server of its own, holds no secrets,
and does not assume the API lives anywhere in particular — it reaches it over the
network by URL, the same way in development as in production. The only thing it
needs to know is where that URL is.

## Running it

```bash
cp .env.example .env    # then point VITE_API_BASE_URL at your API
npm install
npm run dev             # http://localhost:5173
```

The API must be running and must allow this origin. In the API's `.env`:

```
CORS_ORIGINS="http://localhost:5173"
```

Without that, every request is blocked by the browser before it is sent — the
app looks broken and nothing appears in the API logs. It is the first thing to
check when requests fail in development.

The dev server uses `strictPort`, so it fails if 5173 is taken rather than
quietly moving to 5174. That is deliberate: a different port is a different
origin, which CORS would then reject.

## Configuration

One variable, and it is required.

| | |
|---|---|
| `VITE_API_BASE_URL` | Full URL of the API **including its `/api` prefix**, e.g. `http://localhost:8000/api` |

Paths are appended directly to it — `/search` becomes
`http://localhost:8000/api/search` — so leaving the prefix off produces 404s on
every call.

Vite inlines the value into the bundle **at build time**, not at run time. So a
built image is specific to one API URL, and pointing it somewhere else means
rebuilding rather than restarting. There is no default: the app throws
immediately with an explanatory message if the variable is missing, which is far
easier to diagnose than an app that loads and then fails every request.

## Building

```bash
npm run build           # -> dist/
npm run preview         # serve dist/ locally
npm run lint
```

## Container

Multi-stage: Node builds, nginx serves the static output. The API URL is a build
argument, since it has to be present when the bundle is compiled.

```bash
docker build --build-arg VITE_API_BASE_URL=https://api.example.com/api -t candidate-search-web .
docker run -p 8080:80 candidate-search-web
```

`nginx.conf` serves static files only — it does **not** proxy the API. The
browser talks to the API directly, which is why `CORS_ORIGINS` on the API has to
name this app's origin.

## How it is put together

| | |
|---|---|
| `src/lib/api.js` | The axios instance. Knows the API URL and attaches the bearer token. |
| `src/lib/authToken.js` | The only file that knows the token lives in `localStorage`. |
| `src/hooks/` | One hook per API concern — components never call `api` directly. |
| `src/stores/uiStore.js` | Client-only preferences: theme, recent searches, score visibility. |
| `src/pages/` | Sign in, search, users. |
| `src/components/ui/` | shadcn primitives. Generated; rarely edited by hand. |

**Where state lives** is the thing worth knowing before changing anything.
Server state belongs to React Query; the search query, page and page size live in
the URL so results are linkable; the token is in `localStorage`; and only genuine
client preferences go in the zustand store. The store deliberately holds no user
object and no signed-in flag — that would be a second source of truth that drifts
the moment a token expires.

## Auth

There are no passwords. Sign-in is an emailed one-time code exchanged for a
24-hour bearer token, which is stored in `localStorage` and sent as an
`Authorization` header on every request.

That storage choice is deliberate and has a cost: an XSS bug in this app can read
the token. An httpOnly cookie would prevent that but only works when the app and
API are same-site, which they are not. Treat `dangerouslySetInnerHTML` and every
new dependency accordingly.

A `401` means the session is over — there is no refresh endpoint. The app clears
the token and returns to sign-in rather than retrying.
