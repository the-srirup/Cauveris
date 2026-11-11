# Cauveris Makefile
# Note: If 'make' is not available, use the equivalent uv and npm commands documented in README.md

.PHONY: setup dev test lint typecheck quality backend-quality frontend-quality backend-test frontend-test test-coverage build security production-proof e2e golden-incident demo clean live-demo live-demo-check live-demo-stop

# ===== Dependency Installation =====

setup: #### Install all dependencies using committed lockfiles
	uv sync --frozen
	npm --prefix apps/web ci

# ===== Quality Gates =====

quality: backend-quality frontend-quality #### Run all backend and frontend quality checks

backend-quality: #### Run backend linter, typecheck, and runtime fixture guard
	uv run python scripts/check_runtime_fixture_imports.py
	uv run ruff check .
	uv run mypy cauveris

frontend-quality: #### Run frontend runtime fixture guard and strict TypeScript check
	node apps/web/scripts/check-runtime-fixture-imports.mjs
	npm --prefix apps/web run typecheck

# ===== Tests =====

test: backend-test frontend-test #### Run both backend and frontend test suites

backend-test: #### Run backend pytest suite
	uv run pytest -v

frontend-test: #### Run frontend Vitest suite
	npm --prefix apps/web test

test-coverage: #### Run backend and frontend tests with coverage reports
	uv run pytest --junitxml=test-results/backend-results.xml -v
	npm --prefix apps/web run test:coverage

security: #### Run security and authentication mutation regression tests
	uv run pytest tests/test_auth_mutations.py tests/test_production_auth_e2e.py tests/test_refresh_token_rotation.py tests/test_phase1_anti_mock.py -v

# ===== Production Build & Proof =====

build: #### Build Next.js frontend in production mode
	npm --prefix apps/web run build

production-proof: #### Run end-to-end production path proof against live server
	uv run python scripts/run_production_e2e.py

e2e: build #### Run Playwright production end-to-end browser tests
	npm --prefix apps/web run e2e:production

lint: #### Run linting
	uv run ruff check .

typecheck: #### Run type checking
	uv run mypy cauveris

demo: #### Run a full demo: load golden incident and process it
	@echo "Loading golden incident..."
	uv run cauveris --golden &
	BACKEND_PID=$$!
	@echo "Starting backend for processing..."
	# Wait a moment for the golden incident to load
	sleep 2
	@echo "Triggering reconstruction via API (in another terminal, call:)"
	@echo "curl -X POST http://localhost:8000/api/v1/incidents/$(ls -lt evidence_store/ | head -2 | tail -1 | awk '{print $$9}')/reconstruct"
	@echo "Or use the frontend at http://localhost:3000"
	wait $$BACKEND_PID

clean: #### Remove generated files and caches
	rm -rf .uv
	rm -rf __pycache__ */__pycache__ */*/__pycache__ */*/*/__pycache__
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf htmlcov
	rm -rf apps/web/.next
	rm -rf apps/web/node_modules
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".ipynb_checkpoints" -exec rm -rf {} +

# ===== Live Demonstration =====

live-demo: #### Start the complete stack in honest production-demo mode for live recording
	@python scripts/start_live_demo.py

live-demo-check: #### Verify production-demo health, readiness, storage, and models
	@python scripts/live_demo_check.py

live-demo-stop: #### Stop background servers started for live demo
	@python scripts/stop_live_demo.py