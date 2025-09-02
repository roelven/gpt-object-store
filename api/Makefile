.PHONY: test lint run install install-dev clean

# Install production dependencies
install:
	pip install -r requirements.txt

# Install development dependencies
install-dev:
	pip install -r requirements.txt -r requirements-dev.txt

# Run tests with coverage
test:
	pytest tests/ --cov=src --cov-report=term-missing --timeout=10

# Lint and format code
lint:
	black --check src/ tests/
	mypy src/

# Format code
format:
	black src/ tests/

# Run the FastAPI application
run:
	uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# Clean up cache files
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name ".pytest_cache" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .coverage htmlcov/

# Type check
typecheck:
	mypy src/

# Run all checks (lint, typecheck, test)
check: lint typecheck test