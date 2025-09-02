CLAUDE.md — GPT Object Store (Multi-GPT, JSONB, OAuth-ready, Postgres-only)

0) Executive summary
Build a small, durable backend for multiple Custom GPTs to persist and retrieve JSON documents via a public HTTPS API. Storage uses PostgreSQL 17 JSONB with targeted GIN indexes. The API is OpenAPI 3.1 described (so GPT Actions can call it) and ships with required cursor or seek pagination, API-key auth now with a non-breaking path to OAuth 2.0 later, sensible rate limits, and nightly backups from day one. Use Problem Details (RFC 9457) for errors and Link headers (RFC 8288) for pagination. Add explicit Docker Compose bring-up tests with log parsing, and require every sub-agent to finish each implementation task with a git commit to maintain tight versioning. This project is Postgres-only; do not use SQLite.

1) Goals and Non-Goals
Goals
- Store arbitrary, GPT-defined JSON documents with first-class collections per GPT.
- One API usable by many GPTs at once; all data strictly scoped by gpt_id.
- Required keyset or seek pagination (recency at least), stable ordering.
- Public HTTPS API with OpenAPI 3.1 for easy Actions integration.
- Auth v1: API key via Authorization: Bearer <token>. Auth v2: add OAuth 2.0 without breaking clients (stay on Bearer per RFC 6750).
- Nightly backups using pg_dump with rotation.
- Sensible rate limits with 429 and Retry-After.
- Verified Docker Compose bring-up with automated log hygiene checks.
- Strict git hygiene: each sub-agent task ends with an atomic commit including the required footer.
- Postgres-only stance across code, docs, tests, and scripts.

Non-Goals (for v1)
- End-user OAuth UI flows (design for it, implement later).
- Full-text search across JSON fields beyond targeted JSONB and GIN usage.
- Rich query DSL; keep filters minimal with strong ordering.

2) Architecture overview
- API service (FastAPI or Express).
- PostgreSQL 17 (JSONB storage plus GIN indexes).
- Backup sidecar (cron plus pg_dump nightly).
- Ingress and TLS handled by the installer or operator (no proxy service in Compose).

Why JSONB
- Flexible per-GPT schemas, native operators, and GIN support for containment and jsonpath queries.

3) Data model (DDL)
Postgres, UTC. Use UUID v4 defaults via gen_random_uuid() (requires pgcrypto on some installs).

```sql
-- Optional extension (depends on distro)
-- CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE gpts (
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE api_keys (
  token_hash BYTEA PRIMARY KEY,               -- store hash of the API key
  gpt_id     TEXT NOT NULL REFERENCES gpts(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_used  TIMESTAMPTZ
);

CREATE TABLE collections (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  gpt_id     TEXT NOT NULL REFERENCES gpts(id),
  name       TEXT NOT NULL,                   -- e.g., notes
  schema     JSONB,                           -- optional JSON Schema for validation
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (gpt_id, name)
);

CREATE TABLE objects (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  gpt_id      TEXT NOT NULL REFERENCES gpts(id) ON DELETE CASCADE,
  collection  TEXT NOT NULL,
  body        JSONB NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (gpt_id, collection) REFERENCES collections(gpt_id, name) ON DELETE CASCADE
);

CREATE INDEX objects_gpt_coll_created_desc
  ON objects (gpt_id, collection, created_at DESC, id DESC);

CREATE INDEX objects_body_gin ON objects USING GIN (body);
```

4) API design (v1, OAuth-ready)
Base: https://api.yourdomain.com/v1
Auth header (now and later): Authorization: Bearer <token> (API key today; OAuth access tokens later per RFC 6750).
Errors: application/problem+json (RFC 9457).
Pagination: required keyset or seek using (created_at, id); include Link headers for next and prev (RFC 8288).

Endpoints (minimum set)
- Collections
  - POST   /gpts/{gpt_id}/collections     create or upsert a collection with optional stored JSON Schema
  - GET    /gpts/{gpt_id}/collections     list collections with limit, cursor, order
  - GET    /gpts/{gpt_id}/collections/{name}  fetch one
- Objects
  - POST   /gpts/{gpt_id}/collections/{name}/objects     create
  - GET    /gpts/{gpt_id}/collections/{name}/objects     list with limit, cursor, order
  - GET    /objects/{id}                                 fetch one
  - PATCH  /objects/{id}                                 partial update
  - DELETE /objects/{id}                                 delete

Seek pagination contract
- Sort: ORDER BY created_at DESC, id DESC (stable and deterministic).
- Cursor encodes (created_at, id, filters); client supplies cursor to continue.
- Response includes next_cursor, has_more, and Link header with rel="next" when more pages exist.

5) OpenAPI (Actions-friendly, OAuth-ready)
Ship an OpenAPI 3.1 file (checked into repo); GPT Actions consume this schema and support API Key and OAuth.

```yaml
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
  - bearerApiKey: []
paths:
  /gpts/{gpt_id}/collections/{name}/objects:
    get:
      summary: List objects (recency-ordered)
      parameters:
        - in: path
          name: gpt_id
          required: true
          schema: { type: string }
        - in: path
          name: name
          required: true
          schema: { type: string }
        - in: query
          name: limit
          schema: { type: integer, default: 50, maximum: 200 }
        - in: query
          name: cursor
          schema: { type: string }
        - in: query
          name: order
          schema: { type: string, enum: [asc, desc], default: desc }
      responses:
        "200": { description: OK }
        "400": { description: Bad Request, content: { application/problem+json: {} } }
        "401": { description: Unauthorized, content: { application/problem+json: {} } }
```

6) Rate limiting (built-in)
- Per API key default 60 requests per minute; writes 10 per minute.
- Per IP defense in depth 600 requests per 5 minutes.
- On breach: 429 Too Many Requests and Retry-After header.
- Log key, IP, route, and decision for observability.

7) Backups (nightly from day one)
Backup sidecar runs pg_dump nightly and keeps the last N days (for example 14). Prefer custom format -Fc for selective restore.

Example cron line inside sidecar
```
30 02 * * * /usr/bin/pg_dump -h db -U gptstore -Fc gptstore > /backups/backup-$(date +\%F-\%H\%M).dump && find /backups -type f -mtime +14 -delete
```

8) Docker Compose (no proxy or ingress)
Use the Compose Specification for services and volumes; end user provides TLS and ingress. The project must include automated bring-up and log checks to ensure services are healthy and do not emit error-severity logs during normal startup and idle operation.

```yaml
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
      - "8000:8000"

  backup:
    image: alpine:3
    volumes:
      - db-backups:/backups
    depends_on: [db]
    command: ["/bin/sh", "-c", "crond -f -L /var/log/cron.log"]
    # Dockerfile installs postgresql-client and writes crontab with the job above

volumes:
  db-data:
  db-backups:
```

9) Implementation plan (agent-oriented)

9.1 Process guardrails (enforced)
- Ask first when context is missing.
- TDD sequence for every unit of work: write failing test, implement code, verify all tests pass, git commit.
- Use full paths for every command executed by agents.
- Each test has a timeout; entire suite completes in 10 seconds or less.
- Keep each file under 300 lines; refactor when necessary.
- Clear and simple code; comment the why, not the what.
- Logging workflow: add logs during implementation and debugging, remove debug logs when stable; retain structured info logs as needed.

9.2 Git and versioning rules (tight enforcement)
- Every sub-agent and every implementation task must end with an atomic git commit. Do not leave the working tree dirty.
- Commit granularity one responsibility per commit; no bundling unrelated changes.
- Required footer appended to every commit message exactly as specified.
- Before switching tasks, run /usr/bin/git status --porcelain and ensure no changes. If changes exist, commit or revert.
- Provide descriptive commit subject lines.

9.3 Directory layout
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
  CLAUDE.md
```

9.4 Pseudocode (high level)
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
  validate gpt_id and collection
  query:
     ORDER BY created_at DESC, id DESC
     if cursor: WHERE (created_at, id) < (ts, id)
     LIMIT <= max_limit
  return items + next_cursor + Link rel="next" if has_more

WRITE OBJECT:
  optional: validate body against stored JSON Schema (if present)
  insert (gpt_id, collection, body) returning id and timestamps

PATCH and DELETE:
  authorize by gpt_id; apply change; return 204 or 200

ERRORS:
  return RFC 9457 Problem Details on failure

RATE LIMITING:
  token-bucket per key and optional per IP
  exceed -> 429 with Retry-After

BACKUP:
  sidecar runs nightly pg_dump and rotates files
```

9.5 Tests (examples)
- Auth
  - Missing or invalid Bearer yields 401 Problem Details.
  - Valid API key injects correct gpt_id.
- Collections
  - Create is idempotent on (gpt_id, name).
  - List paginated with Link header present.
- Objects
  - Create, read, patch updates updated_at, delete returns 204.
  - List stable order by (created_at, id) with seek pagination across pages.
  - Tampered cursor yields 400 Problem Details.
- Rate limiting
  - Exceed read or write caps yields 429 with Retry-After.
- Errors
  - Handlers return Problem Details shape on failures.
- Backups
  - Cron exists; command invokes pg_dump and rotation.
- Docker Compose bring-up and log hygiene
  - Build succeeds.
  - Up in detached mode succeeds.
  - All services reach healthy state.
  - Logs contain no forbidden error patterns during startup and 30 seconds idle.

10) SQL and pagination details
Why keyset or seek instead of OFFSET
- Avoid scanning and discarding N rows, scale better, deterministic order with tiebreaker on id.

Example queries
```sql
-- first page
SELECT * FROM objects
WHERE gpt_id = $1 AND collection = $2
ORDER BY created_at DESC, id DESC
LIMIT $3;

-- with cursor (ts, id)
SELECT * FROM objects
WHERE gpt_id = $1 AND collection = $2
  AND (created_at, id) < ($3::timestamptz, $4::uuid)
ORDER BY created_at DESC, id DESC
LIMIT $5;
```

11) Security notes (baseline)
- HTTPS only; never accept plaintext.
- Auth today API key Bearer tokens stored hashed; no plaintext API keys at rest.
- Auth tomorrow OAuth 2.0 Authorization Code with PKCE or Client Credentials; same Authorization Bearer header (no path or schema changes).
- Error format RFC 9457 Problem Details.
- Resource controls with rate limits and timeouts.

12) Deliverables (Definition of Done)
- ops/compose.yml includes db, api, backup only; no proxy or ingress service.
- Postgres migrations with tables and indexes above.
- API service with:
  - API key Bearer auth middleware
  - Collections and Objects endpoints
  - Required seek pagination with Link headers
  - Problem Details errors
  - Rate limiting with 429 and Retry-After
- OpenAPI 3.1 file api/openapi/gpt-object-store.yaml with API key security scheme and placeholder oauth2 scheme.
- Backup sidecar Dockerfile and cron config using pg_dump -Fc nightly.
- Test suite within 10 seconds demonstrating all behaviors above, with at least 90 percent of tests passing.
- Docker Compose bring-up test and log hygiene check scripts or make targets that an evaluator can run with full paths.
- Git hygiene:
  - No uncommitted changes after any task
  - Each task ends with an atomic commit including the required footer

13) Open questions (Ask-First for the agent)
- Preferred language and runtime (FastAPI Python or Express or NestJS Node).
- Expected maximum throughput to tune default rate limits.
- Desired backup retention window (default 14 days).
- Any initial JSON Schemas to validate per collection.
- CORS needed for browser clients or only server-to-server via Actions.

14) References
- RFC 8288 Link header semantics
- RFC 9457 Problem Details
- RFC 6749 OAuth 2.0 and RFC 6750 Bearer token usage
- OpenAPI 3.1 official specification
- PostgreSQL JSONB and GIN documentation
- pg_dump documentation
- OWASP REST and API security guidance
- Compose Specification
- Postgres gen_random_uuid availability via pgcrypto
