# Cauveris

Autonomous reality debugger for AI-powered robotic systems

## Overview

Cauveris is an autonomous debugging system designed to diagnose and fix issues in AI-powered robotic systems. It analyzes incident data, generates hypotheses about root causes, runs experiments in sandbox environments, and creates verified patches.

## Features

- Incident ingestion and validation
- Timeline construction from multi-modal evidence
- Hypothesis generation for root cause analysis
- Sandboxed experimentation for validation
- Patch generation and verification
- Automated reporting

## Project Structure

```text
cauveris/
├── cauveris/                 # Main Python package
│   ├── api/                  # FastAPI backend and SSE endpoints
│   ├── config.py             # Configuration management
│   ├── main.py               # CLI entry point
│   ├── security.py           # Security utilities and validation
│   ├── schemas/              # Pydantic data models
│   ├── model_gateway/        # LLM provider abstractions (Local, Nebius)
│   ├── ingestion/            # Incident bundle processing
│   ├── timeline/             # Evidence timeline builder
│   ├── hypothesis/           # Root cause hypothesis generation
│   ├── sandbox/              # Experiment sandbox management
│   ├── simulation/           # Digital twin simulation runner
│   ├── patch/                # Patch generation
│   ├── verifier/             # Patch verification engine
│   ├── report/               # Report generation
│   ├── state_machine/        # Pipeline orchestration state machine
│   └── datasets/             # Golden incident generator module
├── apps/
│   └── web/                  # Next.js frontend application
├── datasets/                 # Reference test datasets
├── golden_incident/          # Golden incident sample bundle (CAU-0001)
├── docs/                     # Project documentation and specifications
├── scripts/                  # Utility and helper scripts
└── tests/                    # Test suite
```

## Installation

### Prerequisites

- Python 3.11+
- Node.js 18+ (for frontend)
- [uv](https://docs.astral.sh/uv/) package installer
- Git

### Setup

```bash
# Clone the repository
git clone https://github.com/the-srirup/cauveris.git
cd cauveris

# Install Python dependencies
uv sync

# Install frontend dependencies
cd apps/web && npm install
cd ../..
```

## Usage

### Backend Server

```bash
# Start the backend API server
uv run cauveris serve

# Or using the Makefile
make dev  # Starts both backend and frontend
```

### Frontend

```bash
cd apps/web
npm run dev
```

### Processing the Golden Incident

```bash
# Load the golden incident (CAU-0001)
uv run cauveris --golden

# Trigger reconstruction via API:
curl -X POST http://localhost:8000/api/v1/incidents/{incident_id}/reconstruct
```

## Development

### Testing & Verification

```bash
# Run test suite
uv run pytest -x

# Run linting
uv run ruff check .

# Run type checking
uv run mypy cauveris
```

### Code Style

- Ruff for linting
- MyPy for static type checking
- Black / Ruff for code formatting

## Configuration

Configuration is managed through environment variables and a `.env` file. See `.env.example` for reference.

## License

Apache 2.0 License - see [LICENSE](LICENSE) file

