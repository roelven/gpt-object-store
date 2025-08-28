# GPT Object Store

A durable backend for multiple Custom GPTs to persist and retrieve JSON documents via a public HTTPS API. Built with PostgreSQL JSONB storage, OpenAPI 3.1, and OAuth-ready authentication.

## Features

- **Multi-GPT Support**: Data strictly scoped by `gpt_id` with first-class collections
- **JSONB Storage**: Flexible document storage with PostgreSQL JSONB and GIN indexes
- **Seek Pagination**: Keyset/cursor pagination with stable ordering and Link headers (RFC 8288)
- **OpenAPI 3.1**: Actions-ready API specification for GPT integration
- **Bearer Authentication**: API key support now, OAuth 2.0 ready for future
- **Rate Limiting**: Per-key and per-IP rate limits with 429/Retry-After responses
- **Nightly Backups**: Automated pg_dump backups with rotation
- **Problem Details**: RFC 9457 error responses

## Quick Start

### Prerequisites

- Docker and Docker Compose
- PostgreSQL 17 (included in Docker setup)

### Deployment

1. Clone the repository
2. Configure environment variables:
   ```bash
   export DATABASE_URL=postgres://gptstore:change-me@db:5432/gptstore
   export RATE_LIMITS="key:60/m,write:10/m,ip:600/5m"
   ```

3. Start services:
   ```bash
   docker-compose -f ops/compose.yml up -d
   ```

### API Usage

```bash
# Create a collection
curl -X POST "http://localhost:8000/v1/gpts/my-gpt/collections" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "notes"}'

# Create an object
curl -X POST "http://localhost:8000/v1/gpts/my-gpt/collections/notes/objects" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"body": {"title": "My Note", "content": "Hello World"}}'

# List objects with pagination
curl "http://localhost:8000/v1/gpts/my-gpt/collections/notes/objects?limit=50" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

## API Documentation

Full OpenAPI 3.1 specification available at `/openapi/gpt-object-store.yaml` when the API is running.

### Authentication

All endpoints require Bearer token authentication:
```
Authorization: Bearer <api_key>
```

### Pagination

List endpoints support seek pagination with `limit`, `cursor`, and `order` parameters. Responses include `next_cursor` and `Link` headers.

### Error Handling

Errors follow RFC 9457 Problem Details format:
```json
{
  "type": "https://example.com/probs/invalid-cursor",
  "title": "Invalid Cursor",
  "status": 400,
  "detail": "The provided cursor is malformed"
}
```

## Development

### Project Structure

```
api/
  src/           # Source code
  tests/         # Test suite
  openapi/       # OpenAPI specification
ops/
  compose.yml    # Docker Compose configuration
  backup/        # Backup sidecar configuration
```

### Testing

Run the test suite:
```bash
cd api && make test
```

Tests complete in under 10 seconds with per-test timeouts.

## Backup Strategy

Nightly backups are performed using `pg_dump -Fc` with 14-day retention. Backups are stored in the `db-backups` volume.

## Security

- API keys are hashed at rest
- HTTPS required in production
- Rate limiting per API key and IP
- Input validation and JSON Schema support
- OAuth 2.0 ready authentication

## License

MIT License