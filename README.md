# GPT Object Store

A production-ready, PostgreSQL-backed REST API for multiple Custom GPTs to persist and retrieve JSON documents. Built with FastAPI, featuring JSONB storage, cursor-based pagination, API key authentication (OAuth-ready), and comprehensive backup capabilities.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-009688.svg)](https://fastapi.tiangolo.com)
[![PostgreSQL 17](https://img.shields.io/badge/PostgreSQL-17-316192.svg)](https://www.postgresql.org/)
[![OpenAPI 3.1](https://img.shields.io/badge/OpenAPI-3.1-85ea2d.svg)](https://www.openapis.org/)

## 🚀 Features

- **Multi-GPT Support**: Strict data isolation per GPT with first-class collections
- **JSONB Storage**: Flexible JSON document storage with GIN indexes for performance
- **Cursor Pagination**: Efficient seek-based pagination (not offset) with Link headers
- **API Key Authentication**: Secure Bearer token auth with bcrypt hashing (OAuth-ready)
- **Rate Limiting**: Token bucket algorithm with configurable per-key and per-IP limits
- **Problem Details**: RFC 9457 compliant error responses
- **JSON Schema Validation**: Optional schema enforcement per collection
- **Automated Backups**: Nightly pg_dump with configurable retention
- **OpenAPI 3.1**: Full specification for GPT Actions integration
- **Docker Compose**: Complete containerized deployment
- **Comprehensive Testing**: 90%+ coverage with <10 second execution

## 📋 Requirements

- Python 3.11+
- PostgreSQL 17
- Docker & Docker Compose (for containerized deployment)
- 2GB+ RAM recommended

## 📚 Documentation

- **[Custom GPT Integration Guide](CUSTOM_GPT_GUIDE.md)** - Step-by-step guide to building Custom GPTs with persistent storage
- **[API Reference](#api-documentation)** - Complete API endpoint documentation
- **[Deployment Guide](#docker-deployment)** - Production deployment instructions

## 🌟 Example Use Cases

Build powerful Custom GPTs with persistent memory:

- **📔 Daily Diary GPT** - Personal journaling with weekly summaries ([Full Tutorial](CUSTOM_GPT_GUIDE.md))
- **📊 Habit Tracker** - Track daily habits and visualize progress
- **📚 Learning Journal** - Document and review your learning journey
- **🏋️ Workout Logger** - Store exercise routines and track PRs
- **📝 Meeting Notes** - Organize and search meeting transcripts
- **🎯 Goal Manager** - Set, track, and review personal goals

## 🏗️ Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Custom GPTs   │────▶│   FastAPI App   │────▶│  PostgreSQL 17  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │                          │
                               │                          │
                        ┌──────▼────────┐         ┌──────▼────────┐
                        │ Rate Limiter  │         │ Backup Sidecar │
                        └───────────────┘         └───────────────┘
```

## 🛠️ Installation

### Local Development

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/gpt-object-store.git
cd gpt-object-store
```

2. **Set up Python environment**
```bash
cd api
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

3. **Configure environment variables**
```bash
cd ops
cp .env.sample .env
# Edit .env with your settings, especially API_URL
vim .env  # or use your preferred editor
```

4. **Run database migrations**
```bash
alembic upgrade head
```

5. **Start the API server**
```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker Deployment

1. **Configure environment variables** (Required!)
```bash
cd ops
cp .env.sample .env
# Edit .env and set API_URL to your domain (required)
vim .env  # Change API_URL from localhost to your actual domain
```

2. **Start all services**
```bash
make up
```

3. **Check service health**
```bash
make status
```

3. **View logs**
```bash
make logs
```

## 🔑 API Key Management

The GPT Object Store uses API keys for authentication. Use the Makefile commands to manage GPTs and API keys:

### Create a GPT and API Key

```bash
cd ops

# First, create a GPT identity
make create-gpt ID=diary-gpt NAME="Daily Diary Assistant"

# Then generate an API key for it
make create-key GPT_ID=diary-gpt
# Output: API Key: abc123... (save this securely - it cannot be retrieved again!)
```

### List and Manage

```bash
# List all GPTs
make list-gpts

# List API keys for a specific GPT (shows metadata only)
make list-keys GPT_ID=diary-gpt

# Revoke an API key
make revoke-key KEY=abc123...
```

### Database Access

```bash
# Direct PostgreSQL access when needed
make db-shell

# Manual backup
make db-backup
```

## 🧪 Testing

### Run Test Suite

```bash
# Run all tests with coverage
cd api
./tests/test_runner.sh

# Or use make
make test
```

The test suite must complete in <10 seconds and maintain ≥90% coverage.

### Test Categories

- **Unit Tests**: Mock-based tests for individual components
- **Integration Tests**: Database and API endpoint testing
- **Performance Tests**: Pagination and rate limiting validation

## 📊 Seeding Test Data

For development and testing, you can seed the database with sample data:

```bash
cd ops
./seed-test-data.sh
```

This creates:
- Test GPT: `test-gpt`
- API Key: `test-api-key-123`
- Collection: `notes`
- Sample objects for pagination testing

### ⚠️ Clearing Test Data for Production

**Important**: Before deploying to production, clear all test data:

```bash
# Connect to your database
psql $DATABASE_URL

-- Remove all test data
DELETE FROM objects WHERE gpt_id = 'test-gpt';
DELETE FROM collections WHERE gpt_id = 'test-gpt';
DELETE FROM api_keys WHERE gpt_id = 'test-gpt';
DELETE FROM gpts WHERE id = 'test-gpt';

-- Or completely reset the database (WARNING: This deletes ALL data)
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;

-- Then re-run migrations
\q
alembic upgrade head
```

## ✅ Compliance Validation

Run the comprehensive evaluation script to validate all requirements:

```bash
cd ops
./run-eval.sh
```

This validates:
- Database schema compliance
- PostgreSQL-only enforcement
- API functionality
- Pagination implementation
- Error handling
- Rate limiting
- Backup configuration
- Docker setup
- Test coverage

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `RATE_LIMITS` | Rate limit configuration | `key:60/m,write:10/m,ip:600/5m` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `CORS_ORIGINS` | Allowed CORS origins | `*` |
| `MAX_PAGE_SIZE` | Maximum pagination size | `200` |
| `DEFAULT_PAGE_SIZE` | Default pagination size | `50` |

### Rate Limiting

Configure rate limits using the format: `type:count/period`

- `key:60/m` - 60 requests per minute per API key
- `write:10/m` - 10 write operations per minute
- `ip:600/5m` - 600 requests per 5 minutes per IP

## 📚 API Documentation

### Interactive Documentation

Once running, access the API documentation at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI spec: http://localhost:8000/openapi.json

### Authentication

All API requests (except health checks) require Bearer token authentication:

```bash
curl -H "Authorization: Bearer your-api-key" \
     http://localhost:8000/v1/gpts/test-gpt/collections
```

### Core Endpoints

#### Collections
- `POST /v1/gpts/{gpt_id}/collections` - Create/upsert collection
- `GET /v1/gpts/{gpt_id}/collections` - List collections (paginated)
- `GET /v1/gpts/{gpt_id}/collections/{name}` - Get collection
- `PATCH /v1/gpts/{gpt_id}/collections/{name}` - Update collection
- `DELETE /v1/gpts/{gpt_id}/collections/{name}` - Delete collection

#### Objects
- `POST /v1/gpts/{gpt_id}/collections/{name}/objects` - Create object
- `GET /v1/gpts/{gpt_id}/collections/{name}/objects` - List objects (paginated)
- `GET /v1/objects/{id}` - Get object
- `PATCH /v1/objects/{id}` - Update object
- `DELETE /v1/objects/{id}` - Delete object

#### Health
- `GET /health` - Overall health status
- `GET /ready` - Readiness check
- `GET /live` - Liveness probe

### Pagination

List endpoints support cursor-based pagination:

```bash
# First page
GET /v1/gpts/test-gpt/collections/notes/objects?limit=50

# Next page using cursor
GET /v1/gpts/test-gpt/collections/notes/objects?cursor=eyJ0cyI6IjIwMjQtMDEtMDEiLCJpZCI6IjEyMyJ9&limit=50
```

Responses include:
- `next_cursor`: Cursor for the next page
- `has_more`: Boolean indicating more pages exist
- `Link` header with `rel="next"` for navigation

### Error Responses

All errors follow RFC 9457 Problem Details format:

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Collection 'notes' not found for GPT 'test-gpt'",
  "instance": "/v1/gpts/test-gpt/collections/notes"
}
```

## 🔒 Security

- **API Keys**: Stored as bcrypt hashes, never in plaintext
- **Rate Limiting**: Configurable per-key and per-IP limits
- **Input Validation**: Pydantic models with strict typing
- **SQL Injection**: Protected via parameterized queries
- **CORS**: Configurable origin restrictions
- **Non-root Docker**: All containers run as non-root users

## 🗄️ Backup & Recovery

### Automated Backups

The backup sidecar runs nightly at 02:30 UTC:
- Format: PostgreSQL custom format (`pg_dump -Fc`)
- Retention: 14 days (configurable)
- Location: `/backups` volume in container

### Manual Backup

```bash
cd ops
make backup-test
```

### Restore from Backup

```bash
# List available backups
docker compose -f ops/compose.yml exec backup ls -la /backups

# Restore specific backup
docker compose -f ops/compose.yml exec db pg_restore \
  -U gptstore -d gptstore -c /backups/backup-2024-01-01-0230.dump
```

## 🚦 Monitoring

### Troubleshooting

#### Missing API_URL Error

**Problem**: "API_URL environment variable is required"

**Solution**: 
- Copy `.env.sample` to `.env` in the ops directory
- Set `API_URL` to your public API endpoint
- This is required for OpenAPI spec generation and GPT Actions

#### Database Connection Issues

**Problem**: Cannot connect to database externally

**Solution**:
The database is now internal to Docker and not exposed on port 5432. Access it via:
```bash
make db-shell
# or
docker compose exec db psql -U gptstore -d gptstore
```

### Health Checks

- **Database**: `pg_isready` every 10 seconds
- **API**: HTTP health endpoint every 30 seconds
- **Backup**: Cron process monitoring

### Logs

View logs for debugging:

```bash
# All services
docker compose -f ops/compose.yml logs

# Specific service
docker compose -f ops/compose.yml logs api

# Follow logs
docker compose -f ops/compose.yml logs -f
```

## 🛤️ Roadmap

- [ ] OAuth 2.0 implementation (authorization code flow)
- [ ] GraphQL API endpoint
- [ ] Full-text search with pg_trgm
- [ ] Webhook notifications
- [ ] Admin dashboard
- [ ] Prometheus metrics
- [ ] Horizontal scaling support

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for your changes
4. Ensure all tests pass (`make test`)
5. Commit with descriptive messages
6. Push to your branch
7. Open a Pull Request

### Development Guidelines

- Follow PEP 8 for Python code
- Maintain test coverage above 90%
- Keep files under 300 lines
- Use type hints for all functions
- Document API changes in OpenAPI spec
- Run `black` formatter before committing

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- Database powered by [PostgreSQL](https://www.postgresql.org/)
- Error handling follows [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html)
- Pagination implements [RFC 8288](https://www.rfc-editor.org/rfc/rfc8288.html)

## 📧 Support

For issues and questions:
- Open an issue on GitHub
- Check existing issues before creating new ones
- Include logs and error messages in bug reports

---

Built with ❤️ for the Custom GPT ecosystem