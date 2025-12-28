.PHONY: help install dev-install format lint typecheck test test-unit test-cov clean docker-build docker-up docker-down

help:
	@echo "Available commands:"
	@echo "  install       - Install production dependencies"
	@echo "  dev-install   - Install development dependencies"
	@echo "  format        - Format code with ruff"
	@echo "  lint          - Lint code with ruff"
	@echo "  typecheck     - Type check with pyright"
	@echo "  test          - Run all tests"
	@echo "  test-unit     - Run unit tests only"
	@echo "  test-cov      - Run tests with coverage"
	@echo "  clean         - Clean build artifacts"
	@echo "  docker-build  - Build Docker image"
	@echo "  docker-up     - Start docker-compose services"
	@echo "  docker-down   - Stop docker-compose services"

install:
	pip install -e .

dev-install:
	pip install -e ".[dev]"
	pre-commit install

format:
	ruff format .

lint:
	ruff check .

typecheck:
	pyright

test:
	pytest tests/

test-unit:
	pytest tests/unit -m unit

test-cov:
	pytest tests/ --cov --cov-report=html --cov-report=term

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

docker-build:
	docker build -t voice-openai-connect:latest .

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f gateway
