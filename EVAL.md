EVAL.md — Compliance and Verification Checklist

Purpose
Verify the repository implements the Multi-GPT JSONB Object Store exactly as specified: required seek pagination, collections as first-class, multi-GPT scoping, API key now with OAuth later, Problem Details, rate limits, nightly backups, OpenAPI 3.1, no proxy in compose, Postgres-only, test and repo hygiene, Docker Compose bring-up and log hygiene validation, and strict git commit discipline after each task. At least 90 percent of tests must be passing for this evaluation to be considered complete.

0) Inputs and assumptions
- Repo root absolute path: /full/path/to/repo
- API base local: http://127.0.0.1:8000/v1
- Bearer key for tests: environment API_KEY=<value>
- DB DSN: postgres://gptstore:change-me@127.0.0.1:5432/gptstore
- Seeded GPT and collection for API checks:
  - gpt_id = test-gpt
  - collection = notes
Adjust variables as needed before running checks.

1) Data model (DDL) JSONB, multi-GPT, collections first-class
Criteria
- Tables: gpts(id, name, created_at), api_keys(token_hash, gpt_id, created_at, last_used), collections(id, gpt_id, name, schema, created_at, unique(gpt_id, name)), objects(id, gpt_id, collection, body, created_at, updated_at).
- Foreign keys: objects (gpt_id, collection) references collections (gpt_id, name) with cascading deletes.
- Indexes: objects_gpt_coll_created_desc on (gpt_id, collection, created_at desc, id desc) and objects_body_gin GIN on body (jsonb).

Commands
```bash
/usr/bin/psql "$DB_DSN" -c "\dt+"
/usr/bin/psql "$DB_DSN" -c "\d+ gpts"
/usr/bin/psql "$DB_DSN" -c "\d+ api_keys"
/usr/bin/psql "$DB_DSN" -c "\d+ collections"
/usr/bin/psql "$DB_DSN" -c "\d+ objects"
/usr/bin/psql "$DB_DSN" -c "SELECT indexname, indexdef FROM pg_indexes WHERE tablename='objects';"
```

Pass if
- All tables, columns, and constraints exist as above.
- objects.body is JSONB and a GIN index on body exists.
- Composite index (gpt_id, collection, created_at desc, id desc) exists.

2) Postgres-only enforcement
Criteria
- No references to sqlite exist anywhere in the repository (code, docs, configs, scripts).
- No sqlite3 binaries invoked.

Commands
```bash
/usr/bin/grep -R -n -i "sqlite" /full/path/to/repo && echo "Found sqlite references" && exit 1 || echo "No sqlite references found"
/usr/bin/grep -R -n -i "sqlite3" /full/path/to/repo && echo "Found sqlite3 references" && exit 1 || echo "No sqlite3 references found"
```

Pass if
- Both commands print the no references found messages and do not exit with failure.

3) API surface (OpenAPI 3.1) Actions-ready, OAuth-ready
Criteria
- A 3.1 OpenAPI file exists at /full/path/to/repo/api/openapi/gpt-object-store.yaml.
- securitySchemes include bearer (API key today) and oauth2 (auth code placeholders).
- Paths include collections and objects as specified; list endpoints accept limit, cursor, order.

Commands
```bash
/usr/bin/grep -E "openapi:\s*3\.1" /full/path/to/repo/api/openapi/gpt-object-store.yaml
/usr/bin/grep -E "securitySchemes:" -n /full/path/to/repo/api/openapi/gpt-object-store.yaml
/usr/bin/grep -E "/gpts/\{gpt_id\}/collections/\{name\}/objects:" -n /full/path/to/repo/api/openapi/gpt-object-store.yaml
```

Pass if
- Version is 3.1.x.
- Both bearerApiKey (or equivalent HTTP bearer) and oauth2 schemes exist.

4) Auth now and later Bearer header, OAuth-ready
Criteria
- Protected endpoints require Authorization: Bearer <token>.
- API keys are hashed at rest (token_hash), no plaintext keys stored.
- Future OAuth can reuse the same Bearer header with no path changes.

Commands
```bash
/usr/bin/psql "$DB_DSN" -c "\d+ api_keys"
/usr/bin/curl -s -o /dev/null -w "%{http_code}\n" -H "Accept: application/json" "http://127.0.0.1:8000/v1/gpts/test-gpt/collections"
```

Pass if
- api_keys stores a hash type (bytea or similar); no plaintext key field.
- Missing auth returns 401 with Problem Details payload.

5) Pagination required seek or keyset and Link headers
Criteria
- List endpoints must implement seek pagination ordered by (created_at desc, id desc).
- Responses include next_cursor and has_more and an HTTP Link header with rel="next".

Commands
```bash
/usr/bin/curl -s -X POST "$API_BASE/gpts/test-gpt/collections/notes/objects" -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d '{"body":{"m":1}}' >/dev/null
/usr/bin/curl -s -X POST "$API_BASE/gpts/test-gpt/collections/notes/objects" -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d '{"body":{"m":2}}' >/dev/null

/usr/bin/curl -i -s "$API_BASE/gpts/test-gpt/collections/notes/objects?limit=1&order=desc" -H "Authorization: Bearer $API_KEY" -H "Accept: application/json" | /usr/bin/tee /tmp/page1.txt

/usr/bin/grep -E "^Link: .*rel=\"next\"" /tmp/page1.txt
/usr/bin/jq -r '.next_cursor' <<< "$(/usr/bin/awk '/^\{/{flag=1} flag{print}' /tmp/page1.txt)"

NEXT=$(/usr/bin/jq -r '.next_cursor' <<< "$(/usr/bin/awk '/^\{/{flag=1} flag{print}' /tmp/page1.txt)")
/usr/bin/curl -s "$API_BASE/gpts/test-gpt/collections/notes/objects?limit=1&cursor=$NEXT" -H "Authorization: Bearer $API_KEY" -H "Accept: application/json"
```

Pass if
- Page 1 returns 200, Link rel=next present, body contains next_cursor.
- Page 2 returns older item(s); ordering by recency is consistent.

6) Collections as first-class and multi-GPT scoping
Criteria
- Create, list, and get collections per gpt_id; unique on (gpt_id, name).
- Objects are scoped to both gpt_id and collection; cross-GPT access denied.

Commands
```bash
/usr/bin/curl -s -X POST "$API_BASE/gpts/test-gpt/collections" -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d '{"name":"notes"}'
/usr/bin/curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $API_KEY" -H "Accept: application/json" "$API_BASE/gpts/other-gpt/collections/notes/objects?limit=1"
```

Pass if
- Duplicate (gpt_id, name) is idempotent or rejects duplicates consistently.
- Cross-GPT read returns 404 or 403, not data.

7) Error format Problem Details (RFC 9457)
Criteria
- Errors use application/problem+json with fields type, title, status, detail.

Commands
```bash
/usr/bin/curl -s -i "$API_BASE/gpts/test-gpt/collections" -H "Accept: application/json"
/usr/bin/curl -s -i "$API_BASE/gpts/test-gpt/collections/notes/objects?cursor=bogus==" -H "Authorization: Bearer $API_KEY" -H "Accept: application/json"
```

Pass if
- Content-Type is application/problem+json.
- Body includes required fields; status matches HTTP code.

8) Rate limits sensible caps and Retry-After
Criteria
- Defaults: per-key read cap and stricter write cap; per-IP cap optional.
- Exceeding a cap yields 429 with Retry-After header.

Commands
```bash
/usr/bin/bash -lc 'for i in $(/usr/bin/seq 1 80); do /usr/bin/curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $API_KEY" "$API_BASE/gpts/test-gpt/collections"; done' | /usr/bin/tail -n 5
```

Pass if
- At least one request returns 429 and includes Retry-After.

9) Nightly backups pg_dump plus rotation
Criteria
- Backup sidecar exists, installs postgresql-client, runs nightly cron with pg_dump -Fc and retention delete (for example 14 days).

Commands
```bash
/usr/bin/grep -R --line-number "pg_dump" /full/path/to/repo/ops/backup
/usr/bin/grep -R --line-number "crond" /full/path/to/repo/ops/backup
```

Pass if
- Cron contains pg_dump command and a retention or deletion step.

10) Docker Compose bring-up and log hygiene
Criteria
- docker compose build completes successfully.
- docker compose up -d completes successfully.
- All services reach healthy state (db and api at minimum).
- Logs for api and db are free of forbidden error tokens during startup and a stabilization window (for example 30 seconds).
- After tests, environment is torn down with volumes removed.

Forbidden tokens (case-insensitive)
- error
- fatal
- panic
- traceback
- unhandledpromiserejection
- uncaught exception
- segmentation fault
- address already in use
- could not connect
- database system is in recovery mode

Commands
```bash
/usr/bin/docker compose -f /full/path/to/repo/ops/compose.yml build
/usr/bin/docker compose -f /full/path/to/repo/ops/compose.yml up -d

# Wait for health checks (db then api)
/usr/bin/bash -lc 'for s in db api; do \
  for i in $(/usr/bin/seq 1 30); do \
    CID=$(/usr/bin/docker compose -f /full/path/to/repo/ops/compose.yml ps -q $s); \
    HS=$(/usr/bin/docker inspect --format "{{json .State.Health.Status}}" "$CID" 2>/dev/null | /usr/bin/tr -d "\""); \
    if [ "$HS" = "healthy" ]; then echo "$s healthy"; break; fi; /usr/bin/sleep 1; \
  done; \
done'

/usr/bin/sleep 5
/usr/bin/docker compose -f /full/path/to/repo/ops/compose.yml logs --no-color > /tmp/compose_startup.log
/usr/bin/grep -E -i "(error|fatal|panic|traceback|unhandledpromiserejection|uncaught exception|segmentation fault|address already in use|could not connect|database system is in recovery mode)" /tmp/compose_startup.log && echo "FORBIDDEN TOKENS FOUND" && exit 1 || echo "Logs clean"

/usr/bin/docker compose -f /full/path/to/repo/ops/compose.yml down -v
```

Pass if
- Build and up complete without failure.
- Both db and api report healthy within 30 seconds.
- Log scan prints Logs clean and does not print FORBIDDEN TOKENS FOUND.

11) Endpoint behavior CRUD sanity
Criteria
- POST /objects returns 201 with object payload.
- GET /objects/{id} returns 200 with same body.
- PATCH /objects/{id} updates updated_at.
- DELETE /objects/{id} returns 204.

Commands
```bash
OID=$(/usr/bin/curl -s -X POST "$API_BASE/gpts/test-gpt/collections/notes/objects" -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d '{"body":{"a":1}}' | /usr/bin/jq -r '.id')
/usr/bin/curl -s "$API_BASE/objects/$OID" -H "Authorization: Bearer $API_KEY" | /usr/bin/jq '.body'
/usr/bin/curl -s -X PATCH "$API_BASE/objects/$OID" -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d '{"body":{"a":2}}' | /usr/bin/jq -r '.updated_at'
/usr/bin/curl -s -o /dev/null -w "%{http_code}\n" -X DELETE -H "Authorization: Bearer $API_KEY" "$API_BASE/objects/$OID"
```

Pass if
- Status codes and behaviors match criteria.

12) Repo hygiene and tests
Criteria and Commands
- OpenAPI present; see section 3.

- Tests complete within 10 seconds with per-test timeouts, and at least 90 percent of tests pass.
If a Make target exists:
```bash
/usr/bin/timeout 12s /usr/bin/make -C /full/path/to/repo/api test | /usr/bin/tee /tmp/test_output.txt
```
If direct test runner is used, substitute the full path command accordingly and tee to the same file. Then compute pass rate using one of the strategies below. Pass if pass rate is greater than or equal to 90 percent and total runtime is less than or equal to 10 seconds.

Strategy A (pytest-like summary)
```bash
/usr/bin/awk '
  /passed,/ || /failed,/ || /errors,/ {
    for (i=1;i<=NF;i++){
      if ($i ~ /passed,?/){sub(/,/, "", $i); split($i,a,"passed"); p=a[1]}
      if ($i ~ /failed,?/){sub(/,/, "", $i); split($i,a,"failed"); f=a[1]}
      if ($i ~ /errors,?/){sub(/,/, "", $i); split($i,a,"errors"); e=a[1]}
      if ($i ~ /skipped,?/){sub(/,/, "", $i); split($i,a,"skipped"); s=a[1]}
    }
  }
  END {
    if (p=="" && f=="" && e=="") { exit 2 }
    total = p + f + e + 0
    rate = (total>0)? (100.0 * p / total) : 0
    printf("TOTAL=%d PASSED=%d FAILED=%d ERRORS=%d RATE=%.2f%%\n", total, p, f, e, rate);
    if (rate < 90.0) exit 3
  }
' /tmp/test_output.txt
```

Strategy B (jest-like summary)
```bash
/usr/bin/awk '
  /Tests:/ {
    for (i=1;i<=NF;i++){
      if ($i ~ /[0-9]+/ && $(i+1)=="passed,"){p=$i}
      if ($i ~ /[0-9]+/ && $(i+1)=="failed,"){f=$i}
    }
  }
  END {
    if (p=="" && f==""){ exit 2 }
    total = p + f + 0
    rate = (total>0)? (100.0 * p / total) : 0
    printf("TOTAL=%d PASSED=%d FAILED=%d RATE=%.2f%%\n", total, p, f, rate);
    if (rate < 90.0) exit 3
  }
' /tmp/test_output.txt
```

Fallback strategy (count PASS and FAIL tokens; best-effort)
```bash
P=$(/usr/bin/grep -E -c "\bPASS\b" /tmp/test_output.txt || echo 0)
F=$(/usr/bin/grep -E -c "\bFAIL\b" /tmp/test_output.txt || echo 0)
T=$(/usr/bin/awk -v p="$P" -v f="$F" 'BEGIN{print p+f}')
RATE=$(/usr/bin/awk -v p="$P" -v t="$T" 'BEGIN{if(t==0) print 0; else print 100.0*p/t}')
echo "TOTAL=$T PASSED=$P FAILED=$F RATE=$RATE%"
awk -v r="$RATE" 'BEGIN{exit (r<90.0)?3:0}'
```

- File length less than or equal to 300 lines
```bash
/usr/bin/find /full/path/to/repo -type f \( -name "*.py" -o -name "*.ts" \) -exec /usr/bin/wc -l {} \; | /usr/bin/awk '$1>300{print}'
```
Pass if no file exceeds 300 lines.

- Commit footer enforced and TDD sequence approximate
```bash
/usr/bin/git -C /full/path/to/repo log -n 30 --pretty=%B | /usr/bin/grep -E "Generated with \[GPT-OSS-20b\].*Zed" -q
```
Pass if every recent commit includes the required footer. Reviewer should also verify test-first commits appear before implementation commits where practical.

- No inline one-off scripts in app sources
```bash
/usr/bin/grep -R --line-number "pg_dump" /full/path/to/repo/api || /usr/bin/true
```
Pass if nothing found.

- Full paths used in scripts where applicable; spot check Makefile and local scripts.

13) Security header and media type checks
Criteria
- Auth required yields 401 without Authorization.
- Error responses use application/problem+json.
- Auth header scheme is Bearer.

Commands
```bash
/usr/bin/curl -i -s "$API_BASE/gpts/test-gpt/collections/notes/objects?limit=1" | /usr/bin/grep -E "HTTP/1.1 401|HTTP/2 401"
/usr/bin/curl -i -s "$API_BASE/gpts/test-gpt/collections/notes/objects?cursor=bad==" -H "Authorization: Bearer $API_KEY" | /usr/bin/grep -i "Content-Type: application/problem+json"
```

Pass if criteria met.

14) Git discipline after every sub-agent task
Criteria
- Working tree is clean after evaluator runs (indicates agents committed their changes).
- All commits include the required footer.
- No untracked or modified files remain after completing an implementation step.

Commands
```bash
/usr/bin/git -C /full/path/to/repo status --porcelain
/usr/bin/git -C /full/path/to/repo log -n 30 --pretty=%B | /usr/bin/grep -E "Co-Authored-By:\s*GPT-OSS-20b" -q
```

Pass if
- status output is empty.
- required footer present in recent commit bodies.

15) Documentation conformance Link and Problem Details standards
- Link header semantics per RFC 8288 for pagination.
- Problem Details per RFC 9457 for error payloads.
These standards underpin sections 5 and 7 checks.

16) Evaluation rubric
Area                                     Weight   Result
Data model and indexes                     15%    PASS or FAIL
OpenAPI 3.1 and OAuth-ready                15%    PASS or FAIL
Auth (Bearer API key)                      10%    PASS or FAIL
Pagination (seek and Link)                 15%    PASS or FAIL
Collections and multi-GPT                  10%    PASS or FAIL
Problem Details errors                     10%    PASS or FAIL
Rate limiting                              10%    PASS or FAIL
Nightly backups                            10%    PASS or FAIL
Repo and tests hygiene                      5%    PASS or FAIL
Docker Compose bring-up and log hygiene    Required PASS
Test pass rate                             Required ≥ 90%

Overall PASS requires
- No critical FAIL in Data model, OpenAPI or OAuth-ready, Auth, Pagination, Problem Details, Docker Compose bring-up and log hygiene, and Test pass rate.
- Total score greater than or equal to 85 percent, and at least 90 percent of tests passing.

17) PASS or FAIL Summary (fill in)
- Data model and indexes: …
- OpenAPI 3.1 and OAuth-ready: …
- Auth (Bearer API key): …
- Pagination (seek and Link): …
- Collections and multi-GPT: …
- Problem Details errors: …
- Rate limiting: …
- Nightly backups: …
- Repo and tests hygiene: …
- Docker Compose bring-up and log hygiene: …
- Test pass rate (≥ 90%): …

Overall: PASS or FAIL
