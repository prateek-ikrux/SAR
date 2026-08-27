# Candidate Search — backend

Vector search and retrieval over the ikrux candidate resume corpus.
FastAPI · MongoDB Atlas Vector Search (automated embedding, voyage-4) · MinIO · JWT auth over cookies or bearer tokens.

Reads candidates from the existing `ats.profiles` collection. Writes nothing there.
Its own users and sessions live in a separate database, `search_and_retrieval`.

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

`exact: true` (ENN) is the default here, as requested. It is deterministic and
exhaustive: it scores **every** vector in the index for every query.

At ~200k documents and voyage-4's 1024 dimensions, the `document` field alone is
roughly 800 MB of vectors; all four embedded fields together are around 3 GB.
**An M10 has 2 GB of RAM.** Expect ENN latency in the hundreds of milliseconds to
seconds, growing linearly as the corpus grows to 400k next year.

Nothing here is broken by that — but measure it before the frontend work starts:

```bash
uv run python -m scripts.check_setup --query "java developer with 9 plus years of experience"
```

That prints ENN and ANN timings for each path. If ENN is too slow, the options in
descending order of effort are: flip `SEARCH_DEFAULT_EXACT=false` (per-request
`exact` still works either way), add Atlas Search Nodes so the index gets its own
memory, or drop `email`/`phone` from the index.

### 4. The domain question is still open, so auth transport is configurable

Cookie auth is the safer design but it only works same-site. Since it is not yet
decided whether the frontend and API share a domain, `AUTH_TRANSPORT` selects how
the session is carried, and nothing else in the codebase changes when you switch.

**"Same site" means the same registrable domain — not the same origin.** Sibling
subdomains count, which is what usually catches people out:

| Deployment | Same site? | Setting |
|---|---|---|
| One origin behind a proxy — `app.ikrux.com` and `app.ikrux.com/api` | yes | `AUTH_TRANSPORT=cookie`, `COOKIE_SAMESITE=strict` |
| Sibling subdomains — `app.ikrux.com` and `api.ikrux.com` | yes | `AUTH_TRANSPORT=cookie`, `COOKIE_SAMESITE=strict`, `COOKIE_DOMAIN=.ikrux.com`, plus `CORS_ORIGINS` |
| Unrelated domains — `ikrux-hire.com` and `api.ikrux.com`, or a `*.vercel.app` frontend | **no** | `AUTH_TRANSPORT=bearer`, plus `CORS_ORIGINS` |
| Local dev — `localhost:3000` and `localhost:8000` | yes | `AUTH_TRANSPORT=cookie`, `COOKIE_SECURE=false`, `CORS_ORIGINS=http://localhost:3000` |
| Undecided | — | `AUTH_TRANSPORT=both` while you find out |

So only the third row forces a change. Note that `COOKIE_SAMESITE=none` is *not* a
reliable escape hatch for it: Safari and Firefox block third-party cookies
outright regardless of `SameSite`, and Chrome is heading the same way. That is why
cross-domain gets `bearer` rather than looser cookies.

**What each transport does**

- `cookie` (default) — access, refresh and CSRF cookies. Tokens never reach
  JavaScript, so XSS cannot exfiltrate a session. CSRF double-submit applies.
- `bearer` — no cookies. `POST /api/auth/verify-code` returns `access_token` and
  `refresh_token` in the body; send `Authorization: Bearer <access_token>`.
  Refresh posts `{"refresh_token": "..."}`. No CSRF token needed: a header is not
  an ambient credential. The tradeoff is that the frontend now holds the token,
  so keep it in memory rather than `localStorage`.
- `both` — accepts either, and returns tokens *and* sets cookies. The header wins
  when both are present. Useful only while the deployment shape is unsettled.

Everything else — rotation, reuse detection, revocable sessions, the 24-hour
absolute expiry, roles — is identical across all three.

Two guardrails catch the common mistakes at boot rather than in the browser:
`COOKIE_SAMESITE=none` with an empty `CORS_ORIGINS` is refused outright
(credentialed CORS cannot use a wildcard), and cookie transport with CORS origins
configured logs a warning pointing at this table.

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

**For local http development set `COOKIE_SECURE=false` in `.env`.** Otherwise the
browser accepts the sign-in and then rejects every request that follows, because
it silently discards `Secure` cookies sent over http. It looks like a broken
session, not a config problem.

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
| `POST` | `/api/auth/verify-code` | — | Exchanges the code for a session |
| `POST` | `/api/auth/refresh` | — | Rotates the refresh token |
| `POST` | `/api/auth/logout` | any | Revokes this session |
| `POST` | `/api/auth/logout-all` | any | Revokes every session for the user |
| `GET` | `/api/auth/me` | any | |
| `GET` | `/api/auth/sessions` | any | Live sessions, current one flagged |
| `DELETE` | `/api/auth/sessions/{id}` | any | Revoke one of your own sessions |
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
  "exact": true,             // null -> SEARCH_DEFAULT_EXACT. true = ENN, false = ANN
  "collapse_duplicates": true
}
```

Response carries `strategy`, `mode` (`enn`/`ann`), `took_ms`, `cached`,
`total_in_pool`, `has_more` and `pool_exhausted` alongside `results`.

Each hit has `id`, `headline`, `email`, `phone`, `file_name`, `score`, `snippet`,
`collapsed`, `duplicate_count` and `duplicates[]`.

`headline` is pulled from the resume's first markdown heading (`## SWEETY AGARWAL`
→ `Sweety Agarwal`). Pure string handling — no enrichment pipeline, no LLM. It is
occasionally wrong when a resume does not start with the candidate's name.

### Pagination

`$vectorSearch` has no `skip`. Deep pages exist only by asking for a larger
`limit` and slicing the result.

Re-running the query for each page would repeat the whole scan every time —
under ENN that means a full 200k-vector pass per page. So one pool is fetched
(`SEARCH_POOL_SIZE`, default 100, capped by `SEARCH_MAX_POOL_SIZE`), cached for
`SEARCH_CACHE_TTL_SECONDS`, and paged in memory. Page 2 costs nothing.

Because ENN is deterministic the cached pool is exactly what a re-query would
return, so paging stays stable — the intuition about ENN was right, the "call
again per page" part is just wasted work. ANN is not deterministic, which is a
second reason to page from one pool rather than re-query.

The cache is in-process. If this API is ever run as more than one replica, move
it to Redis or pagination will jump between replicas.

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
then exchange it for a session.

```
POST /api/auth/request-code   {"email": "you@ikrux.com"}
   -> 200 {"message": "If that address has an account, a sign-in code is on its way.",
           "expires_in_minutes": 10, "resend_available_in_seconds": 60}

POST /api/auth/verify-code    {"email": "you@ikrux.com", "code": "630843"}
   -> 200 {"user": {...}, "csrf_token": "...", ...}   + session cookies / tokens
```

`request-code` answers identically whether or not the address has an account, so
it cannot be used to enumerate who works here. A code is 6 digits, valid for 10
minutes, single-use, Argon2id-hashed at rest, and invalidated by: being used,
expiring, 5 wrong attempts, or a newer code being issued. Three limits sit on top
— 60s resend cooldown and 5 codes per hour per address, plus a per-IP ceiling.

- **Access token** — JWT, HS256, 15 minutes. Delivered as an `httpOnly` cookie scoped to `/`, or as a bearer token, per `AUTH_TRANSPORT`.
- **Refresh token** — JWT, HS256, `httpOnly` cookie scoped to `/api/auth` so it
  is not sent on ordinary API calls. Rotated on every use.
- **Session** — a document in `search_and_retrieval.sessions`, revocable, with a
  hard 24-hour absolute expiry (`REFRESH_TOKEN_TTL_HOURS`). Refresh cannot extend
  past it, so everyone re-authenticates daily.
- **Refresh reuse detection** — presenting an already-rotated refresh token
  revokes the entire session family immediately. That is the signature of a
  stolen token.
- **Revocation is real** — every authenticated request confirms the session is
  still live, so logout, admin deactivation and role changes take effect at
  once rather than waiting for a token to expire.
- **CSRF** — cookie transport only, since only cookies are ambient credentials.
  `SameSite` plus a double-submit token: `verify-code` returns `csrf_token` and also sets
  it as a readable `cs_csrf` cookie; send it back as `X-CSRF-Token` on every
  non-GET request. Enforced only once a session cookie exists and no
  `Authorization` header is present, so sign-in and bearer clients are unaffected.
- **Codes** — Argon2id-hashed, never stored or logged in the clear.
  Rate limited per IP, per address, and per code.
- **Roles** — `admin` and `recruiter`. Admins manage users; the API refuses to
  demote, deactivate or delete the last active admin. Changing a role
  or active flag revokes that user's sessions.

There is no signup route and no self-service account creation. The first admin comes from `scripts/create_admin.py`; the rest are created by an admin via `POST /api/users`.

### Frontend integration sketch

The sign-in screen is two states: collect the email, then collect the code. Keep
the email in component state between them — `verify-code` needs both.

**Cookie transport** — nothing is stored client-side except the CSRF token:

```ts
// Screen 1
await fetch("/api/auth/request-code", {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email }),
});

// Screen 2
const session = await fetch("/api/auth/verify-code", {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email, code }),
}).then((r) => r.json());

await fetch("/api/search", {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token },
  body: JSON.stringify({ query: "java developer with 9 plus years", page: 1, page_size: 10 }),
});
```

**Bearer transport** — same endpoints, token held in memory:

```ts
const session = await fetch("https://api.ikrux.com/api/auth/verify-code", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email, code }),
}).then((r) => r.json());   // -> { access_token, refresh_token, token_type: "Bearer", ... }

await fetch("https://api.ikrux.com/api/search", {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.access_token}` },
  body: JSON.stringify({ query: "java developer with 9 plus years", page: 1, page_size: 10 }),
});
```

`request-code` always returns 200, so screen 2 should show unconditionally — a
typo'd address simply never receives a code. Handle `429` on resend: the response
carries `resend_available_in_seconds` for the countdown.

On a `401`, call `POST /api/auth/refresh` once and retry — with no body under
cookie transport, or `{"refresh_token": "..."}` under bearer. If refresh also
fails, send the user back to login. Writing the API client so the transport is a
single swappable module keeps this a one-file change later.

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
    auth_service.py    sessions, rotation, reuse detection
    otp_service.py     one-time codes: issue, rate limit, verify
    mailer.py          Microsoft Graph client credentials + sendMail
    search_service.py  the $vectorSearch pipeline, pooling, presentation
    dedupe.py          email/phone normalisation, transitive grouping
    cache.py           in-process TTL cache for search pools
    storage.py         MinIO presigned URLs
    cookies.py         cookie policy in one place
scripts/
  check_setup.py             inspect the index, compare paths, time ENN vs ANN
  create_admin.py            create the first admin, optionally mail a code
  create_profile_indexes.py  optional email/phone indexes on ats.profiles
```

## Not built

Out of scope by decision, listed so nobody assumes otherwise: hybrid/lexical
search, reranking, LLM enrichment into structured filters, ingestion of new
resumes, audit logging, SSO, automated tests, Docker packaging.
