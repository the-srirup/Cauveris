# Cauveris Makefile
# Note: If 'make' is not available, use the equivalent uv and npm commands documented in README.md

.PHONY: setup dev test lint typecheck golden-incident demo clean

# ===== Dependency Installation =====

setup: #### Install all dependencies
	uv sync
	cd apps/web && npm install

# ===== Development =====

dev: #### Start development servers (backend and frontend)
	@echo "Starting backend server..."
	uv run cauveris &
	BACKEND_PID=$$!
	@echo "Starting frontend server..."
	cd apps/web && npm run dev
	@echo "Stopping backend server..."
	kill $$BACKEND_PID

# Equivalent to running in separate terminals:
# Terminal 1: uv run cauveris serve
# Terminal 2: cd apps/web && npm run dev

# ===== Commands =====

golden-incident: #### Load the golden incident (CAU-0001)
	uv run cauveris --golden

test: #### Run the test suite
	uv run pytest -x

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