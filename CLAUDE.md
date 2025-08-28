# GPT Object Store (Multi-GPT, JSONB, OAuth-ready)

## Executive summary

Build a small, durable backend for multiple Custom GPTs to persist and retrieve JSON documents via a public HTTPS API. Storage uses PostgreSQL JSONB (with targeted GIN indexes). The API is OpenAPI 3.1 described (so GPT Actions can call it) and ships with required cursor/keyset pagination, API-key auth now with a non-breaking path to OAuth 2.0 later, sensible rate limits, and nightly backups from day one. References: OpenAI Actions expect OpenAPI schemas and support API Key/OAuth flows; use Problem Details (RFC 9457) for errors and Link headers (RFC 8288) for pagination. 


## 1) Goals & Non-Goals

**Goals**

* Store arbitrary, GPT-defined JSON documents with first-class collections per GPT.
* One API usable by many GPTs at once; all data strictly scoped by gpt_id.
* Required keyset/cursor pagination (recency at least), stable ordering. 
* Public HTTPS API with OpenAPI 3.1 for easy Actions integration. 
* Auth v1: API key via `Authorization: Bearer <token>`. Auth v2: add OAuth 2.0 w/o breaking clients (remain on Bearer per RFC 6750). 
* Nightly backups using `pg_dump` with rotation. 
* Sensible rate limits + 429/Retry-After. (OWASP guidance) 

**Non-Goals (for v1)**

* End-user OAuth flows (we only design for it now).
* Full-text search/indexing across JSON fields (beyond GIN where useful).
* Rich query DSL; only minimal filters + strong ordering.

## 2) Architecture overview

* API service (FastAPI or Express).
* PostgreSQL 17 (JSONB storage + GIN indexes).
* Backup sidecar (cron + pg_dump nightly).
* Ingress/TLS handled by the installer/user (no proxy service in Compose).

**Why JSONB?** Flexible per-GPT schemas, strong operators, and GIN support for containment/jsonpath queries.


## 3) Data model (DDL)

Postgres, UTC. Use UUID v4 defaults via `gen_random_uuid()` (requires `pgcrypto`).

```
-- Enable extension for gen_random_uuid on some installs
-- CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE gpts (
  id         TEXT PRIMARY KEY,                -- your chosen gpt-id
  name       TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE api_keys (
  token_hash BYTEA PRIMARY KEY,               -- store hash of the API key (never plaintext)
  gpt_id     TEXT NOT NULL REFERENCES gpts(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_used  TIMESTAMPTZ
);

CREATE TABLE collections (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  gpt_id     TEXT NOT NULL REFERENCES gpts(id),
  name       TEXT NOT NULL,                   -- e.g., "notes"
  schema     JSONB,                           -- optional JSON Schema for validation
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (gpt_id, name)
);

CREATE TABLE objects (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  gpt_id      TEXT NOT NULL REFERENCES gpts(id) ON DELETE CASCADE,
  collection  TEXT NOT NULL,                  -- fk to collections.name scoped by gpt_id
  body        JSONB NOT NULL,                 -- GPT-defined shape
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (gpt_id, collection) REFERENCES collections(gpt_id, name) ON DELETE CASCADE
);

-- Seek-friendly index (recency + deterministic tie-break)
CREATE INDEX objects_gpt_coll_created_desc ON objects (gpt_id, collection, created_at DESC, id DESC);

-- Query inside JSON when needed (containment/jsonpath)
CREATE INDEX objects_body_gin ON objects USING GIN (body);

```
> Prefer JSONB + GIN judiciously; measure before adding more JSON-field indexes.


## 4) API design (v1, OAuth-ready)

* Base: https://api.yourdomain.com/v1
* Auth header (now & later): Authorization: Bearer <token> (API key today; OAuth access tokens later per RFC 6750).
* Errors: `application/problem+json` (RFC 9457).
* Pagination: Required keyset/cursor using (`created_at`, `id`); include `Link` headers for `next`/`prev` (RFC 8288).


### Endpoints (minimum set)

* Collections
  * `POST /gpts/{gpt_id}/collections` – create/update (optional stored JSON Schema)
  * `GET /gpts/{gpt_id}/collections?limit&cursor&order` – list (paginated)
  * `GET /gpts/{gpt_id}/collections/{name}` – fetch one
* Objects
  * `POST /gpts/{gpt_id}/collections/{name}/objects` – create
  * `GET /gpts/{gpt_id}/collections/{name}/objects?limit&cursor&order` – list (paginated, recency)
  * `GET /objects/{id}` – fetch one
  * `PATCH /objects/{id}` – partial update
  * `DELETE /objects/{id}` – delete

**Seek pagination contract**

* Sort: `ORDER BY created_at DESC, id DESC` (stable, deterministic).
* Cursor encodes `(created_at, id, filters)`; client supplies `cursor` to continue.
* Response includes `next_cursor`, `has_more`, and a `Link` header with `rel="next"``.


## 5) OpenAPI (Actions-friendly, OAuth-ready)

Ship an OpenAPI **3.1** file (checked into repo); GPT Actions consume this schema and support API Key and OAuth. 

```
openapi: 3.1.0
info: { title: GPT Object Store, version: "1.0.0" }
servers: [{ url: https://api.yourdomain.com/v1 }]
components:
  securitySchemes:
    bearerApiKey:
      type: http
      scheme: bearer
      bearerFormat: APIKey
    oauth2:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://auth.yourdomain.com/oauth/authorize
          tokenUrl: https://auth.yourdomain.com/oauth/token
          scopes:
            objects:read: Read objects
            objects:write: Write objects
security:
  - bearerApiKey: []   # swap to oauth2 later without changing paths
paths:
  /gpts/{gpt_id}/collections/{name}/objects:
    get:
      summary: List objects (recency-ordered)
      parameters:
        - in: path; name: gpt_id; required: true; schema: { type: string }
        - in: path; name: name; required: true; schema: { type: string }
        - in: query; name: limit; schema: { type: integer, default: 50, maximum: 200 }
        - in: query; name: cursor; schema: { type: string }
        - in: query; name: order; schema: { type: string, enum: [asc, desc], default: desc }
      responses:
        "200": { description: OK }
        "400": { description: Bad Request, content: { application/problem+json: {} } }
        "401": { description: Unauthorized, content: { application/problem+json: {} } }
```

## 6) Rate limiting (built-in)

* **Per API key**: default `60 req/min`; writes `10 req/min`.
* **Per IP** (defense-in-depth): `600 req/5min`.
* On breach: `429 Too Many Requests` + `Retry-After`.
* Log key, IP, route, and decision for observability.


## 7) Backups (nightly from day 1)

Backup sidecar runs pg_dump nightly and keeps the last N days (e.g., 14). Prefer custom format `-Fc` for selective restore.

Example cron line inside sidecar:
```
30 02 * * * /usr/bin/pg_dump -h db -U gptstore -Fc gptstore \
  > /backups/backup-$(date +\%F-\%H\%M).dump && \
  find /backups -type f -mtime +14 -delete
```


## 8) Docker Compose

Use the Compose Specification for services/volumes; end user provides TLS/ingress.
```
# ops/compose.yml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_DB: gptstore
      POSTGRES_USER: gptstore
      POSTGRES_PASSWORD: change-me
    volumes:
      - db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U gptstore"]
      interval: 10s
      retries: 5

  api:
    build:
      context: /full/path/to/api
    environment:
      DATABASE_URL: postgres://gptstore:change-me@db:5432/gptstore
      RATE_LIMITS: "key:60/m,write:10/m,ip:600/5m"
    depends_on: [db]
    ports:
      - "8000:8000"   # public ingress handled by the installer

  backup:
    image: alpine:3
    volumes:
      - db-backups:/backups
    depends_on: [db]
    command: ["/bin/sh", "-c", "crond -f -L /var/log/cron.log"]
    # Dockerfile/entrypoint installs: postgresql-client, sets /etc/crontabs/root with the job above

volumes:
  db-data:
  db-backups:

```


## 9) Implementation plan (agent-oriented)

### 9.1 Directory layout

```
/full/path/to/
  api/
    src/
      main.[py|ts]
      config.[py|ts]
      auth/
      routes/
      models/
      db/
      rate_limit/
      pagination/
      errors/
    tests/
      unit/
      integration/
    openapi/
      gpt-object-store.yaml
    Dockerfile
  ops/
    compose.yml
    backup/
      Dockerfile
      crontab
  .github/workflows/ci.yaml
  CLAUDE.md
  EVAL.md
```

### 9.3 Pseudocode (high level)

```
INIT:
  load env; connect to Postgres; run migrations

AUTH MIDDLEWARE:
  parse Authorization: Bearer <token>
  if token is API key:
     hash -> lookup api_keys -> inject gpt_id into request scope
  else if token is JWT/OAuth (future):
     validate; map client_id/scope->gpt_id (config); inject gpt_id
  else 401 problem+json

PAGINATION HELPERS:
  encode_cursor(created_at, id, filters) -> base64
  decode_cursor -> (ts, id, filters)

LIST OBJECTS:
  validate gpt_id & collection
  build query:
     ORDER BY created_at DESC, id DESC
     if cursor: WHERE (created_at, id) < (ts, id)
     LIMIT <= max_limit
  return items + next_cursor + Link rel="next" if has_more

WRITE OBJECT:
  optional: validate body against stored JSON Schema (if present)
  insert (gpt_id, collection, body) returning id, timestamps

PATCH/DELETE:
  authorize (by gpt_id); apply change; return 204/200

ERRORS:
  on any failure return RFC9457 Problem Details

RATE LIMITING:
  token-bucket in-memory + (optional) sliding window per key/IP
  on exceed -> 429 + Retry-After

BACKUP:
  backup sidecar runs nightly pg_dump and rotates files
```


### 9.4 Tests (examples)

* **Auth**
  * rejects missing/invalid Bearer → 401 Problem Details
  * accepts valid API key → injects correct gpt_id
* **Collections**
  * create, idempotent on same (gpt_id, name)
  * list with pagination; `Link` header present
* **Objects**
  * create/read/patch/delete happy paths
  * list: stable order by (`created_at, id`); **seek pagination** across pages
  * cursor includes filters; tampered cursor → 400 Problem Details
* **Rate limiting**
  * hit read/write caps → 429 + `Retry-After`
* **Errors**
  * every handler returns Problem Details shape on failure
* **Backups**
  * cron file exists; command includes `pg_dump` and rotation

> Enforce per-test timeouts; whole suite ≤ 10s. (Design fast tests with small in-memory data or a local Postgres fixture.)


### 9.5 CI

* Lint + typecheck
* Run unit tests (≤ 10s)
* Generate OpenAPI from source (if code-first) and validate schema

### 10) SQL & pagination details

**Why keyset/seek, not OFFSET?** Avoids scanning/throwing away N rows; scales better. Use composite ordering `(created_at DESC, id DESC)` for determinism. 

**Example queries**

```
-- first page
SELECT * FROM objects
WHERE gpt_id = $1 AND collection = $2
ORDER BY created_at DESC, id DESC
LIMIT $3;

-- with cursor(ts, id)
SELECT * FROM objects
WHERE gpt_id = $1 AND collection = $2
  AND (created_at, id) < ($3::timestamptz, $4::uuid)
ORDER BY created_at DESC, id DESC
LIMIT $5;
```

### 11) Security notes (baseline)

* HTTPS only; never accept plaintext.
* Auth today: API key Bearer tokens (opaque), stored hashed.
* Auth tomorrow: OAuth 2.0 Authorization Code + PKCE or Client Credentials. Same `Authorization: Bearer` header per RFC 6750 (no path/shape changes).
* Error format: RFC 9457 Problem Details — consistent, machine-readable.
* Resource controls: rate limits/timeouts to mitigate unrestricted resource consumption.


### 12) Deliverables (Definition of Done)

* `docker-compose.yml` (db, api, backup) — no proxy/ingress defined.
* Postgres migrations (tables + indexes above).
* API service with:
  * Auth middleware (API key Bearer)
  * Collections + Objects endpoints
  * Required **seek pagination** + `Link` headers (RFC 8288)
  * Problem Details errors (RFC 9457)
  * Rate limiting (per key/IP) with 429 + Retry-After
* OpenAPI 3.1 file `api/openapi/gpt-object-store.yaml` (API key security scheme + placeholder oauth2 scheme).
* Backup sidecar Dockerfile + cron config using `pg_dump -Fc` nightly.
* Test suite (≤ 10s) proving all behaviors above.


### 13) Open questions (ASK-FIRST for the agent)

1. Preferred language/runtime (FastAPI Python vs. Express/NestJS Node)?
2. Expected maximum throughput (to tune default rate limits)?
3. Desired retention for backups (default 14 days ok)?
4. Any initial JSON Schemas to validate per collection?
5. Do we need CORS for browser clients (not required for GPT Actions)?


### 14) References

- Web Linking (`Link` headers) — RFC 8288
- Problem Details — RFC 9457 (obsoletes 7807)
- OAuth 2.0 (RFC 6749) & Bearer Tokens (RFC 6750)
- OpenAPI 3.1 (official spec)
- PostgreSQL JSONB & GIN indexes (official docs)
- `pg_dump` (official docs)
- OWASP REST/API security guidance (rate limiting)


### 15) First sprint — concrete tasks

> Follow the TDD sequence for every task. Keep each file under 300 lines.

1. Scaffold API service (+ health check)
2. DB migrations for gpts, api_keys, collections, objects (+ indexes)
3. Auth middleware (API key)
4. Collections CRUD (read-heavy)
5. Objects write + read
6. Seek pagination helpers
7. Rate limiting middleware
8. Problem Details everywhere
9. OpenAPI 3.1 file (API-key default + oauth2 placeholder)
10. Backup sidecar


### 16) Acceptance criteria checklist

- [ ] OpenAPI 3.1 present; pasteable into GPT Actions; uses Bearer API key
- [ ] All list endpoints implement seek pagination + Link headers
- [ ] Data separated by gpt_id; collections are first-class
- [ ] Problem Details errors everywhere
- [ ] Rate limits enforced with 429/Retry-After
- [ ] Nightly backups created and rotated
- [ ] Test suite completes ≤ 10s with per-test timeouts
- [ ] No file >300 LOC; no one-off inline scripts
- [ ] Each commit message appended with the required footer

