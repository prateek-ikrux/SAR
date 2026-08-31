# Candidate Search — backend

Vector search and retrieval over the ikrux candidate resume corpus.
FastAPI · MongoDB Atlas Vector Search (automated embedding, voyage-4) · MinIO · JWT bearer auth.

Reads candidates from the existing `ats.profiles` collection. Writes nothing there.
Its own users and sign-in codes live in a separate database, `search_and_retrieval`.

---

## Read this before running

### 1. The vector index embeds four fields — only one of them is useful

The index definition on `ats.profiles` is:

```json
{ "fields": [
  { "type": "autoEmbed", "modality": "text", "model": "voyage-4", "path": "file_name" },
  { "type": "autoEmbed", "modality": "text", "model": "voyage-4", "path": "email" },
  { "type": "autoEmbed", "modality": "text", "model": "voyage-4", "path": "phone" },
  { "type": "autoEmbed", "modality": "text", "model": "voyage-4", "path": "document" }
] }
```

`$vectorSearch` searches **one** `path` per query. The pipeline in the original
notes used `path: "file_name"` — that searches the embedding of the string
`"262_sweetyagarwal[8_0].pdf"`, not the resume. It returns results, which is why
the mistake is easy to miss, but the ranking is meaningless.

**This service uses `path: "document"`** (`VECTOR_PATH`). Run `scripts/check_setup.py`
to see both side by side on the same query.

`email` and `phone` should never have been embedded — semantic similarity over an
identifier is not a useful operation, and each embedded field multiplies index
size and cost. Searching for an email or phone number is handled here by an exact
`$match` instead (see *Identifier lookup*). Dropping those two fields from the
index would shrink it by roughly half; that is a decision for you, not a blocker.

### 2. It is one vector per resume, not chunks

`autoEmbed` produces a single embedding for the whole field value, truncated at
the model's input limit. There is no chunking option in the index definition, so
every resume — 4k tokens or 15k — is one averaged vector.

The practical effect: a 12-year Java architect and a fresher who once wrote
"Java" both sit near a "Java" query, because the vector describes the whole
document rather than any one claim in it. Section-level chunking is the fix when
precision becomes the complaint. Noted, not built — pure vector search over whole
documents is what was asked for.

### 3. ENN cost at your corpus size

ENN is the initial mode. It is deterministic and exhaustive: it scores **every**
vector in the index for every query.

At ~200k documents and voyage-4's 1024 dimensions, the `document` field alone is
roughly 800 MB of vectors; all four embedded fields together are around 3 GB.
**An M10 has 2 GB of RAM.** Expect ENN latency in the hundreds of milliseconds to
seconds, growing linearly as the corpus grows to 400k next year.

Nothing here is broken by that — but measure it before the frontend work starts:

```bash
uv run python -m scripts.check_setup --query "java developer with 9 plus years of experience"
```

That prints ENN and ANN timings for each path. If ENN is too slow, the options in
descending order of effort are: add Atlas Search Nodes so the index gets its own
memory, or drop `email`/`phone` from the index.

**ENN is the only mode.** `exact: true` is written directly into the
`$vectorSearch` stage in `search_service._run_vector_search`: there is no admin
screen, no environment variable, and no request field that can switch a search to
ANN. Every query scores the whole index, so the same query always returns the
same ranking. Making ANN available again means editing that stage and shipping
it — which is the point. Approximate results should never become the default
because a config value drifted.

### 4. One auth transport: bearer tokens

The web app and this API are independent deployments on separate origins, so a
session cookie is not an option — `SameSite` cookies do not cross sites, and
browsers block third-party cookies regardless of what `SameSite` says. There is
no `AUTH_TRANSPORT` switch and no cookie code: `POST /api/auth/verify-code`
returns `access_token` in the body, and every authenticated request carries
`Authorization: Bearer <access_token>`.

**The tradeoff, stated plainly.** The token lives in JavaScript — the web app
keeps it in `localStorage` — so an XSS bug in the frontend can read it and use it
for up to 24 hours. An `httpOnly` cookie would have prevented that, at the cost
of only working same-site. This is the deliberate trade for deploying the two
halves independently.

**What falls out of it**

- **No CSRF machinery.** CSRF exists because cookies are *ambient*: the browser
  attaches them to any request to that origin, including ones a hostile page
  triggered. An `Authorization` header is set explicitly by our own code, after
  a CORS preflight, so there is nothing to forge. No double-submit token, no
  `X-CSRF-Token` header, no exempt-path list.
- **`CORS_ORIGINS` is required**, and is the one thing that must be right for the
  browser to reach this API at all. It must list the web app's origin exactly —
  scheme included, no trailing slash. An empty value logs a warning at boot,
  because the failure otherwise shows up as a blocked request in the browser with
  nothing in the API logs.
- **No `/auth/logout` endpoint.** There would be nothing for it to do: the token
  is stateless and there is no session record to end. Signing out is the client
  discarding its own copy.

---

## Running it

```bash
cd backend
cp .env.example .env    # fill in MONGODB_URI, JWT_SECRET, GRAPH_*, MinIO creds
uv sync
uv run python -m scripts.check_setup           # confirm Atlas is reachable and sane
uv run python -m scripts.create_admin --email you@ikrux.com --name "Your Name" --send-code
uv run fastapi dev app/main.py --port 8000
```

Interactive API docs: <http://localhost:8000/api/docs>

`--send-code` mails a sign-in code immediately, which is the quickest end-to-end
check that the Graph credentials actually work.

Without Graph credentials you can still develop: set

```
OTP_LOG_CODE_WHEN_MAIL_UNCONFIGURED=true
```

and the code is written to the server log instead of being emailed. The config
refuses to start with this enabled when `ENVIRONMENT=production`.

Generate a signing secret:

```bash
uv run python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Optional — index `email` and `phone` on `ats.profiles` so identifier lookups and
duplicate expansion do not scan the collection. Adds indexes only, no data:

```bash
uv run python -m scripts.create_profile_indexes --confirm
```

---

## Docker

Two images, wired together by `docker-compose.yml` at the repo root:

```bash
docker compose up -d --build     # web http://localhost:8080, api http://localhost:8000
docker compose logs -f api
docker compose down
```

Create the first admin inside the running container:

```bash
docker compose exec api python -m scripts.create_admin \
  --email you@ikrux.com --name "Your Name" --send-code
```

**Both containers publish a host port**, because the browser talks to each of
them directly. `web` serves static files and nothing else — it does not proxy the
API. Two settings have to agree for the pair to work, and compose derives both
from the same ports so they cannot drift:

| | Set to | Where |
|---|---|---|
| `VITE_API_BASE_URL` | the api's origin (`http://localhost:${API_PORT}`) | build **arg** on `web` |
| `CORS_ORIGINS` | the web app's origin (`http://localhost:${WEB_PORT}`) | env on `api`, overriding `backend/.env` |

Override the ports with `WEB_PORT` / `API_PORT` in a `.env` next to
`docker-compose.yml`.

**The two images differ in how configuration reaches them, and it matters.** The
api reads `backend/.env` at run time via `env_file`, so nothing is baked in —
`.dockerignore` excludes `.env`, the image holds no credentials, and one image
promotes between environments unchanged. The web image cannot work that way: Vite
inlines `VITE_API_BASE_URL` into the bundle at build time, so **a web image is
specific to one API origin** and pointing it somewhere else means rebuilding, not
restarting. If you would rather promote a single web image, serve the value from
a small runtime-generated script instead of a build arg.

**Before a real deployment**, over HTTPS:

- build `web` with `VITE_API_BASE_URL` set to the api's public HTTPS origin
- set `CORS_ORIGINS` to the web app's public HTTPS origin — scheme included, no
  trailing slash, no wildcard
- set `ENVIRONMENT=production` — this makes the config refuse to start without
  Graph credentials, and refuse `OTP_LOG_CODE_WHEN_MAIL_UNCONFIGURED`
- terminate TLS in front of both containers

---

## Microsoft Graph setup

Sign-in codes are sent from `service@ikrux.com` through Microsoft 365, using an
app-only (client credentials) token. In Entra ID:

1. **App registration** → note the *Directory (tenant) ID* and *Application
   (client) ID* → `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`.
2. **Certificates & secrets** → new client secret → `GRAPH_CLIENT_SECRET`.
   Secrets expire; diarise the renewal, because when it lapses nobody can log in.
3. **API permissions** → Microsoft Graph → **Application permissions** →
   `Mail.Send` → **Grant admin consent**. Delegated `Mail.Send` will not work:
   there is no signed-in user in this flow.
4. `GRAPH_SENDER=service@ikrux.com` — the mailbox the code is sent *from*. It
   needs a real licensed mailbox.

`Mail.Send` as an application permission lets the app send as **any** mailbox in
the tenant. Narrow it with an [Application Access
Policy](https://learn.microsoft.com/en-us/graph/auth-limit-mailbox-access) so
this registration can only send as `service@ikrux.com`:

```powershell
New-ApplicationAccessPolicy -AppId <client-id> `
  -PolicyScopeGroupId service@ikrux.com -AccessRight RestrictAccess `
  -Description "Candidate Search sign-in codes"
```

Codes are sent with `saveToSentItems: false`, so live sign-in codes are not left
sitting in the shared mailbox's Sent Items where anyone with access could read
them.

`GET /api/ready` reports `mail: ok` once the credentials work, and readiness is
**false** without them — no mail means no logins.

---

## API

| Method | Path | Role | Notes |
|---|---|---|---|
| `POST` | `/api/auth/request-code` | — | Emails a one-time sign-in code |
| `POST` | `/api/auth/verify-code` | — | Exchanges the code for a 24h access token |
| `GET` | `/api/auth/me` | any | |
| `POST` | `/api/search` | any | Vector search |
| `GET` | `/api/profiles/{id}` | any | Full resume text + duplicates |
| `GET` | `/api/profiles/{id}/resume` | any | Presigned MinIO URL (`?redirect=true` to jump straight to the PDF) |
| `GET` | `/api/users` | admin | |
| `POST` | `/api/users` | admin | |
| `PATCH` | `/api/users/{id}` | admin | |
| `DELETE` | `/api/users/{id}` | admin | |
| `GET` | `/api/health`, `/api/ready` | — | |

### Search

```jsonc
POST /api/search
{
  "query": "java developer with 9 plus years of experience",
  "page": 1,
  "page_size": 10,
  "collapse_duplicates": true
}
```

Response carries `strategy` (`vector` or `identifier`), `took_ms`,
`total_in_pool`, `has_more` and `pool_exhausted` alongside `results`.

Each hit has `id`, `headline`, `email`, `phone`, `file_name`, `score`, `snippet`,
`collapsed`, `duplicate_count` and `duplicates[]`.

`headline` is pulled from the resume's first markdown heading (`## SWEETY AGARWAL`
→ `Sweety Agarwal`). Pure string handling — no enrichment pipeline, no LLM. It is
occasionally wrong when a resume does not start with the candidate's name.

### Nothing is cached

Every request runs a fresh `$vectorSearch`. Results are always current, and
searching the same text twice genuinely searches twice — the second call is a
new query against Atlas, not a replay.

The cost is real and worth knowing: **each page is a full query**. There is no
free page 2. At ~120k documents that is roughly 800ms–1.1s per page, and Atlas
re-embeds the query text every time.

### Pagination

`$vectorSearch` has no `skip`, so a page is served by asking for a larger `limit`
and slicing: `SEARCH_POOL_SIZE` (default 100), grown as needed for deeper pages
and capped by `SEARCH_MAX_POOL_SIZE`.

Because searches run ENN, this is exact and deterministic: the same query returns
the same ranking every time, so paging is consistent even though each page is its
own query. That property is the reason ANN is not an option — under an
approximate search a candidate could appear on two pages, or be skipped between
them, since Atlas does not guarantee identical ordering across separate calls.

### Duplicate collapsing

Two documents are the same person if they share a normalised email **or** a
normalised phone (non-digits stripped, last 10 digits). Grouping is transitive,
so resume A (email X), resume B (email X + phone Y) and resume C (phone Y)
collapse into one result.

The best-scoring document becomes the primary and keeps its score;
`duplicate_count` and `duplicates[]` carry the rest. A duplicate's email or phone
fills in a gap on the primary if the primary is missing one. Pass
`collapse_duplicates: false` to see the raw ranking. `GET /api/profiles/{id}`
always lists that person's other documents.

The search pool is over-fetched 3× when collapsing, so a page of 10 still fills
after merging.

### Identifier lookup

A query that is an email address or a phone number is answered with an exact
`$match`, not a vector search — `strategy: "identifier"` in the response. Someone
typing a phone number wants that person, not people whose numbers look similar.

---

## Auth model

**There are no passwords.** Signing in is two steps: request a one-time code,
then exchange it for a 24-hour access token.

```
POST /api/auth/request-code   {"email": "you@ikrux.com"}
   -> 200 {"message": "If that address has an account, a sign-in code is on its way.",
           "expires_in_minutes": 10, "resend_available_in_seconds": 60}

POST /api/auth/verify-code    {"email": "you@ikrux.com", "code": "630843"}
   -> 200 {"user": {...}, "access_token": "eyJ...", "expires_at": "..."}
```

`request-code` answers identically whether or not the address has an account, so
it cannot be used to enumerate who works here. A code is 6 digits, valid for 10
minutes, single-use, Argon2id-hashed at rest, and invalidated by: being used,
expiring, 5 wrong attempts, or a newer code being issued. Three limits sit on top
— 60s resend cooldown and 5 codes per hour per address, plus a per-IP ceiling.

- **One access token, nothing else** — JWT, HS256, 24 hours
  (`ACCESS_TOKEN_TTL_HOURS`), returned in the `verify-code` body and sent back as
  `Authorization: Bearer`. There is no refresh token and no server-side session
  record. When it expires the user signs in again.
- **The account is still checked on every request** — the token is stateless,
  but each authenticated request re-reads the user from the database. So
  deactivating or deleting an account, or changing its role, takes effect on
  that user's *very next request*. `role` is read from the database, never
  trusted from the token.
- **An individual token cannot be revoked.** This is the deliberate trade for
  dropping sessions, and it has two consequences worth knowing:
  - Signing out is the client discarding its own copy — there is no logout
    endpoint, because there is nothing server-side to end. The token stays valid
    until it expires, so signing out on a shared machine does not invalidate a
    copy taken beforehand.
  - If a token is stolen, the only lever is to deactivate the account
    (`PATCH /api/users/{id}` with `{"active": false}`), which cuts off *all* of
    that user's access immediately. There is no way to kill one token and leave
    the others.
- **No CSRF protection, deliberately** — there is nothing to protect. CSRF
  attacks work by making the browser attach an *ambient* credential to a request
  the user did not intend; an `Authorization` header is not ambient. No cookie is
  ever read or set by this API.
- **Codes** — Argon2id-hashed, never stored or logged in the clear.
  Rate limited per IP, per address, and per code.
- **Roles** — `admin` and `recruiter`. Admins manage users; the API refuses to
  demote, deactivate or delete the last active admin.

There is no signup route and no self-service account creation. The first admin comes from `scripts/create_admin.py`; the rest are created by an admin via `POST /api/users`.

### Frontend integration sketch

The sign-in screen is two states: collect the email, then collect the code. Keep
the email in component state between them — `verify-code` needs both.

```ts
// Screen 1
await fetch(`${API}/api/auth/request-code`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email }),
});

// Screen 2 -> { user, access_token, expires_at }
const session = await fetch(`${API}/api/auth/verify-code`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email, code }),
}).then((r) => r.json());

// Every call after that
await fetch(`${API}/api/search`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Authorization: `Bearer ${session.access_token}`,
  },
  body: JSON.stringify({ query: "java developer with 9 plus years", page: 1, page_size: 10 }),
});
```

`request-code` always returns 200, so screen 2 should show unconditionally — a
typo'd address simply never receives a code. Handle `429` on resend: the response
carries `resend_available_in_seconds` for the countdown.

**A `401` means sign in again.** There is no refresh endpoint to try first, so
the API client should clear its local state and route to the sign-in screen. Do
not build a retry loop — the request will fail identically every time.

`verify-code` returns `expires_at`, so the frontend can warn before the 24 hours
are up rather than dropping the user mid-search. A search result the user is
reading is not lost by a 401; only the next request fails.

Keep the token in one module rather than reading it at each call site. The web
app does this in `src/lib/authToken.js`, which is also the only place that knows
it lives in `localStorage`.

---

## Layout

```
app/
  config.py            settings + validation (rejects weak JWT secrets)
  db.py                one Atlas client, two databases
  security.py          Argon2 hashing, JWT issue/verify
  dependencies.py      current_user, require_role, client_ip
  logging_config.py    JSON logs with a request id
  models.py            request/response schemas
  routers/             auth, search, profiles, users, health
  services/
    auth_service.py    account lookup, token issuing, rate limiting
    otp_service.py     one-time codes: issue, rate limit, verify
    mailer.py          Microsoft Graph client credentials + sendMail
    search_service.py  the $vectorSearch pipeline, paging, presentation
    dedupe.py          email/phone normalisation, transitive grouping
    storage.py         MinIO presigned URLs
scripts/
  check_setup.py             inspect the index, compare paths, time ENN vs ANN
  create_admin.py            create the first admin, optionally mail a code
  create_profile_indexes.py  optional email/phone indexes on ats.profiles
```

## Not built

Out of scope by decision, listed so nobody assumes otherwise: hybrid/lexical
search, reranking, LLM enrichment into structured filters, ingestion of new
resumes, audit logging, SSO, automated tests, Docker packaging.
