# Candidate Search — backend

Vector search and retrieval over the ikrux candidate resume corpus.
FastAPI · MongoDB Atlas Vector Search (automated embedding, voyage-4) · MinIO · JWT auth over cookies or bearer tokens.

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
descending order of effort are: switch the mode to ANN on the admin Settings page
(see below), add Atlas Search Nodes so the index gets its own memory, or drop
`email`/`phone` from the index.

**ENN vs ANN is an application-wide setting, not a per-request option.** An admin
chooses it on the Settings page (`PUT /api/settings`), and **ENN is the mode until
someone explicitly switches to ANN** — there is no environment variable that can
make ANN the starting mode. A caller cannot override the mode on an individual
search either, deliberately: recruiters search, they do not tune the engine.

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

- `cookie` (default) — access and CSRF cookies. The token never reaches
  JavaScript, so XSS cannot exfiltrate it. CSRF double-submit applies.
- `bearer` — no cookies. `POST /api/auth/verify-code` returns `access_token` in
  the body; send `Authorization: Bearer <access_token>`. No CSRF token needed: a
  header is not an ambient credential. The tradeoff is that the frontend now
  holds the token, so keep it in memory rather than `localStorage`.
- `both` — accepts either, and returns the token *and* sets cookies. The header
  wins when both are present. Useful while the deployment shape is unsettled.

Everything else — the 24-hour token lifetime, roles, the per-request account
check — is identical across all three.

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
| `POST` | `/api/auth/verify-code` | — | Exchanges the code for a 24h access token |
| `POST` | `/api/auth/logout` | any | Clears cookies in this browser (token stays valid until expiry) |
| `GET` | `/api/auth/me` | any | |
| `POST` | `/api/search` | any | Vector search |
| `GET` | `/api/profiles/{id}` | any | Full resume text + duplicates |
| `GET` | `/api/profiles/{id}/resume` | any | Presigned MinIO URL (`?redirect=true` to jump straight to the PDF) |
| `GET` | `/api/settings` | admin | Current search mode |
| `PUT` | `/api/settings` | admin | Set ENN or ANN for everyone |
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

Response carries `strategy`, `mode` (`enn`/`ann`), `took_ms`, `total_in_pool`,
`has_more` and `pool_exhausted` alongside `results`.

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
free page 2. At ~120k documents that is roughly 800ms–1.1s per page under ENN,
and 450–700ms under ANN, and Atlas re-embeds the query text every time.

### Pagination

`$vectorSearch` has no `skip`, so a page is served by asking for a larger `limit`
and slicing: `SEARCH_POOL_SIZE` (default 100), grown as needed for deeper pages
and capped by `SEARCH_MAX_POOL_SIZE`.

Under **ENN** this is exact and deterministic, so the same query returns the same
ranking every time and paging is consistent.

Under **ANN** it is approximate, and Atlas does not guarantee an identical
ordering across separate calls. Because each page is now its own query rather
than a slice of one shared pool, a candidate could in principle appear on two
pages, or be skipped between them. In practice HNSW traversal over an unchanged
index is stable, so this is a caveat rather than an observed problem — but ENN is
the safer choice if consistent paging matters.

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
   -> 200 {"user": {...}, "csrf_token": "...", "expires_at": "..."}   + cookies / token
```

`request-code` answers identically whether or not the address has an account, so
it cannot be used to enumerate who works here. A code is 6 digits, valid for 10
minutes, single-use, Argon2id-hashed at rest, and invalidated by: being used,
expiring, 5 wrong attempts, or a newer code being issued. Three limits sit on top
— 60s resend cooldown and 5 codes per hour per address, plus a per-IP ceiling.

- **One access token, nothing else** — JWT, HS256, 24 hours
  (`ACCESS_TOKEN_TTL_HOURS`). Delivered as an `httpOnly` cookie scoped to `/`, or
  as a bearer token, per `AUTH_TRANSPORT`. There is no refresh token and no
  server-side session record. When it expires the user signs in again.
- **The account is still checked on every request** — the token is stateless,
  but each authenticated request re-reads the user from the database. So
  deactivating or deleting an account, or changing its role, takes effect on
  that user's *very next request*. `role` is read from the database, never
  trusted from the token.
- **An individual token cannot be revoked.** This is the deliberate trade for
  dropping sessions, and it has two consequences worth knowing:
  - `POST /auth/logout` only clears the cookies in that browser. The token stays
    valid until it expires, so logging out on a shared machine does not
    invalidate a copy taken beforehand.
  - If a token is stolen, the only lever is to deactivate the account
    (`PATCH /api/users/{id}` with `{"active": false}`), which cuts off *all* of
    that user's access immediately. There is no way to kill one token and leave
    the others.
- **CSRF** — cookie transport only, since only cookies are ambient credentials.
  `SameSite` plus a double-submit token: `verify-code` returns `csrf_token` and also sets
  it as a readable `cs_csrf` cookie; send it back as `X-CSRF-Token` on every
  non-GET request. Enforced only once the access cookie exists and no
  `Authorization` header is present, so sign-in and bearer clients are unaffected.
- **Codes** — Argon2id-hashed, never stored or logged in the clear.
  Rate limited per IP, per address, and per code.
- **Roles** — `admin` and `recruiter`. Admins manage users; the API refuses to
  demote, deactivate or delete the last active admin.

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
}).then((r) => r.json());   // -> { access_token, token_type: "Bearer", expires_at, ... }

await fetch("https://api.ikrux.com/api/search", {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.access_token}` },
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

Writing the API client so the transport (cookie vs bearer) is a single swappable
module keeps a later domain decision to a one-file change.

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
    settings_service.py app-wide search settings, admin managed
    dedupe.py          email/phone normalisation, transitive grouping
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
