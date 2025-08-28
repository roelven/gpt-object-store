# EVAL.md — Compliance & Verification Checklist

> Purpose: verify the repository implements the Multi-GPT JSONB Object Store exactly as specified: required seek pagination, collections as first-class, multi-GPT scoping, API key now / OAuth later, Problem Details, rate limits, nightly backups, OpenAPI 3.1, no proxy in compose, test & repo hygiene.

## 0) Inputs & assumptions

* Repo root (absolute path): `/full/path/to/repo`
* API base (local): `http://127.0.0.1:8000/v1` (TLS/ingress handled by installer in prod)
* Bearer key for tests: set env A`PI_KEY=<value>``
* DB DSN (if needed): `postgres://gptstore:change-me@127.0.0.1:5432/gptstore`
* A seeded GPT & collection for API checks:
  * `gpt_id = test-gpt`
  * `collection = notes`

> If any of the above differ, update variables before running checks.

---


## 1) Data model (DDL) — JSONB, multi-GPT, collections first-class

**Criteria**

* Tables: `gpts(id name created_at)`, `api_keys(token_hash gpt_id …)`, `collections(id gpt_id name schema … UNIQUE(gpt_id,name))`, `objects(id gpt_id collection body created_at updated_at …)`.
* FKs: `objects (gpt_id, collection)` → `collections (gpt_id, name)`; cascading deletes OK.
* Indexes: `objects_gpt_coll_created_desc` on `(gpt_id, collection, created_at DESC, id DESC)`, and `objects_body_gin` GIN on `body` (jsonb). JSONB & GIN use is required.

**Commands**

```
/usr/bin/psql "$DB_DSN" -c "\dt+"
/usr/bin/psql "$DB_DSN" -c "\d+ gpts"
/usr/bin/psql "$DB_DSN" -c "\d+ api_keys"
/usr/bin/psql "$DB_DSN" -c "\d+ collections"
/usr/bin/psql "$DB_DSN" -c "\d+ objects"
/usr/bin/psql "$DB_DSN" -c "SELECT indexname, indexdef FROM pg_indexes WHERE tablename='objects';"
```

**Pass if**

* All tables/columns/constraints exist as above.
* `objects.body` is JSONB; a GIN index on `body` exists.
* Composite index `(gpt_id, collection, created_at DESC, id DESC)` exists.

---


## 2) API surface (OpenAPI 3.1) — Actions-ready, OAuth-ready

**Criteria**

* An OpenAPI 3.1 file exists at `/full/path/to/repo/api/openapi/gpt-object-store.yaml`.
* `securitySchemes` include bearer (API key today) and oauth2 (auth code flow placeholders).
* Paths include collections & objects as specified; list endpoints accept `limit`, `cursor`, `order`.

**Commands**

```
/usr/bin/grep -E "openapi:\s*3\.1" /full/path/to/repo/api/openapi/gpt-object-store.yaml
/usr/bin/grep -E "securitySchemes:" -n /full/path/to/repo/api/openapi/gpt-object-store.yaml
/usr/bin/grep -E "/gpts/\{gpt_id\}/collections/\{name\}/objects:" -n /full/path/to/repo/api/openapi/gpt-object-store.yaml
```

**Pass if**

* Version is `3.1.x`.
* Both `bearerApiKey` (or equivalent HTTP bearer) and an `oauth2` scheme exist.

---


## 3) Auth now & later — Bearer header, OAuth-ready

**Criteria**

* All protected endpoints require `Authorization: Bearer <token>`.
* API keys are hashed at rest (column like `token_hash`, no plaintext key column).
* Future OAuth can reuse the same header (Bearer per RFC 6750) with no path changes.

**Commands**

```
/usr/bin/psql "$DB_DSN" -c "\d+ api_keys"
/usr/bin/curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Accept: application/json" \
  "http://127.0.0.1:8000/v1/gpts/test-gpt/collections"
```

**Pass if**

* `api_keys` stores a hash (binary/bytea); there is no plaintext key column.
* Missing auth returns 401 with Problem Details payload (see §6).

---


## 4) Pagination — required seek/keyset + Link headers

**Criteria**

* List endpoints must implement seek pagination ordered by `(created_at DESC, id DESC)`.
* Responses include `next_cursor`/`has_more` and an HTTP `Link: …; rel="next"` header (RFC 8288).

**Commands**

```
# Create a few objects
/usr/bin/curl -s -X POST "$API_BASE/gpts/test-gpt/collections/notes/objects" \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"body":{"m":1}}' >/dev/null
/usr/bin/curl -s -X POST "$API_BASE/gpts/test-gpt/collections/notes/objects" \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"body":{"m":2}}' >/dev/null

# Page 1 (limit=1)
/usr/bin/curl -i -s "$API_BASE/gpts/test-gpt/collections/notes/objects?limit=1&order=desc" \
  -H "Authorization: Bearer $API_KEY" -H "Accept: application/json" | /usr/bin/tee /tmp/page1.txt

# Extract next_cursor
/usr/bin/grep -E "^Link: .*rel=\"next\"" /tmp/page1.txt
/usr/bin/jq -r '.next_cursor' <<< "$(/usr/bin/awk '/^\{/{flag=1} flag{print}' /tmp/page1.txt)"

# Page 2 using cursor
NEXT=$(/usr/bin/jq -r '.next_cursor' <<< "$(/usr/bin/awk '/^\{/{flag=1} flag{print}' /tmp/page1.txt)")
/usr/bin/curl -s "$API_BASE/gpts/test-gpt/collections/notes/objects?limit=1&cursor=$NEXT" \
  -H "Authorization: Bearer $API_KEY" -H "Accept: application/json"
```

**Pass if**

* Page 1 returns 200, `Link: … rel="next"` present, JSON body contains `next_cursor`.
* Page 2 returns the older item(s); ordering by recency is consistent.

---


## 5) Collections as first-class & multi-GPT scoping

**Criteria**

* Can create/list/get collections per gpt_id; unique (`gpt_id`, `name`).
* Objects are scoped to both `gpt_id` and `collection`; cross-GPT access is denied.

**Commands**

```
# Create collection in test-gpt
/usr/bin/curl -s -X POST "$API_BASE/gpts/test-gpt/collections" \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"name":"notes"}'

# Attempt to read with another (nonexistent) gpt
/usr/bin/curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $API_KEY" -H "Accept: application/json" \
  "$API_BASE/gpts/other-gpt/collections/notes/objects?limit=1"
```

**Pass if**

* Duplicate (`gpt_id`, `name`) is idempotent/unique.
* Cross-GPT read returns 404/403 (not data).

---


## 6) Error format — Problem Details (RFC 9457)

**Criteria**

* Errors are returned as `application/problem+json` with at least `type`, `title`, `status`, `detail`.

**Commands**

```
# 401 (no auth)
/usr/bin/curl -s -i "$API_BASE/gpts/test-gpt/collections" -H "Accept: application/json"
/usr/bin/curl -s -i "$API_BASE/gpts/test-gpt/collections/notes/objects?cursor=bogus==" \
  -H "Authorization: Bearer $API_KEY" -H "Accept: application/json"
```

**Pass if**

* Response `Content-Type` is `application/problem+json`.
* Body includes required fields; `status` matches HTTP code.

---


## 7) Rate limits — sensible caps + Retry-After

**Criteria**

* Defaults: per-key read cap and stricter write cap; per-IP cap optional.
* Exceeding a cap yields 429 + `Retry-After` header.

**Commands**

```
# Burst GET beyond limit (example 80 in a minute; tune to configured limit)
/usr/bin/bash -lc 'for i in $(/usr/bin/seq 1 80); do \
  /usr/bin/curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $API_KEY" "$API_BASE/gpts/test-gpt/collections"; done' | /usr/bin/tail -n 5
```

**Pass if**

* At least one request returns 429, and the response includes `Retry-After`.

---


## 8) Nightly backups — pg_dump + rotation

**Criteria**

* A backup sidecar exists (Dockerfile/entrypoint), installs `postgresql-client`, and runs a nightly cron with `pg_dump` (prefer `-Fc`) and rotation (e.g., 14 days).
* `pg_dump` is used (not filesystem copies of live data dirs).

**Commands**

```
/usr/bin/grep -R --line-number "pg_dump" /full/path/to/repo/ops/backup
/usr/bin/grep -R --line-number "crond" /full/path/to/repo/ops/backup
```

**Pass if**

* Cron contains `pg_dump` command and a retention/deletion step.

---


## 9) Endpoint behavior — CRUD sanity

**Criteria**

* `POST /objects` → 201 with object payload.
* `GET /objects/{id}` → 200 with same body.
* `PATCH /objects/{id}` updates `updated_at`.
* `DELETE /objects/{id}` → 204.

**Commands**

```
OID=$(/usr/bin/curl -s -X POST "$API_BASE/gpts/test-gpt/collections/notes/objects" \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"body":{"a":1}}' | /usr/bin/jq -r '.id')
/usr/bin/curl -s "$API_BASE/objects/$OID" -H "Authorization: Bearer $API_KEY" | /usr/bin/jq '.body'
/usr/bin/curl -s -X PATCH "$API_BASE/objects/$OID" \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"body":{"a":2}}' | /usr/bin/jq -r '.updated_at'
/usr/bin/curl -s -o /dev/null -w "%{http_code}\n" -X DELETE \
  -H "Authorization: Bearer $API_KEY" "$API_BASE/objects/$OID"
```

**Pass if**

* Status codes and behaviors match criteria.

---


## 10) Repo hygiene & tests (from CLAUDE.md rules)

**Criteria & Commands**

* OpenAPI present: see §2.
* Tests ≤ 10s, per-test timeouts:
	`/usr/bin/timeout 12s /usr/bin/make -C /full/path/to/repo/api test`
	Pass: suite completes under 10s (CI timing), and test code shows per-test timeouts.
* File length ≤ 300 lines:
	`/usr/bin/find /full/path/to/repo -type f -name "*.py" -o -name "*.ts" \
  | /usr/bin/xargs -I{} /usr/bin/wc -l {} | /usr/bin/awk '$1>300{print}'`
	Pass: no file listed exceeds 300 LOC.
* No inline one-off scripts: backup logic lives under ops/backup/* (Dockerfile + crontab), not embedded in app sources.
	`/usr/bin/grep -R --line-number "pg_dump" /full/path/to/repo/api || /usr/bin/true`
	Pass: no `pg_dump` or similar devops commands embedded in app files.
* Use full paths in scripts & CI where applicable. (Spot check Makefile/CI.)

---


## 11) Security header & media type checks

**Criteria**

Auth required → 401 without `Authorization`.
Error responses `Content-Type: application/problem+json`.
Auth header scheme is Bearer (works for API key & future OAuth).

**Commands**
```
/usr/bin/curl -i -s "$API_BASE/gpts/test-gpt/collections/notes/objects?limit=1" | /usr/bin/grep -E "HTTP/1.1 401|HTTP/2 401"
/usr/bin/curl -i -s "$API_BASE/gpts/test-gpt/collections/notes/objects?cursor=bad==" \
  -H "Authorization: Bearer $API_KEY" | /usr/bin/grep -i "Content-Type: application/problem+json"
```

Pass if criteria met.

---


## 12) Documentation conformance (Link & Problem Details standards)

* `Link` header semantics per RFC 8288 for pagination.
* Problem Details per RFC 9457 for error payloads.

> These standards are the basis for §4 and §6 checks.

---


## 13) Evaluation rubric

| Area                                           | Weight | Result      |
| ---------------------------------------------- | -----: | ----------- |
| Data model & indexes                           |    15% | PASS / FAIL |
| OpenAPI 3.1 & OAuth-ready                      |    15% | PASS / FAIL |
| Auth (Bearer API key)                          |    10% | PASS / FAIL |
| Pagination (seek + `Link`)                     |    15% | PASS / FAIL |
| Collections & multi-GPT                        |    10% | PASS / FAIL |
| Problem Details errors                         |    10% | PASS / FAIL |
| Rate limiting                                  |    10% | PASS / FAIL |
| Nightly backups                                |    10% | PASS / FAIL |
| Repo/test hygiene (timeouts, ≤300 LOC, footer) |     5% | PASS / FAIL |

**Overall PASS** requires:

* No critical FAIL in: Data model, OpenAPI/OAuth-ready, Auth, Pagination, Problem Details.
* Total score ≥ 85%.


---

## 14) PASS/FAIL Summary (fill in)

* Data model & indexes: …
* OpenAPI 3.1 & OAuth-ready: …
* Auth (Bearer API key): …
* Pagination (seek + `Link`): …
* Collections & multi-GPT: …
* Problem Details errors: …
* Rate limiting: …
* Nightly backups: …
* Repo/test hygiene: …

**Overall**: PASS / FAIL



