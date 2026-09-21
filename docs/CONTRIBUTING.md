# Contributing to Cauveris

Thank you for your interest in contributing to Cauveris!

## Development Setup

1. Fork the repository
2. Clone your fork locally
3. Install development dependencies:
   `ash
   uv sync
   cd apps/web && npm install
   cd ..
   `

## Code Style

We use:
- **Ruff** for linting
- **MyPy** for type checking
- **Black** for code formatting (dev dependency)

Run checks before submitting:
`ash
uv run ruff check .
uv run mypy cauveris
`

## Making Changes

1. Create a feature branch: git checkout -b feature/your-feature-name
2. Make your changes
3. Add tests for new functionality
4. Ensure all tests pass: uv run pytest -x
5. Commit your changes with descriptive messages
6. Push to your fork and open a pull request

## Reporting Issues

Please use the GitHub issue tracker to report bugs or request features.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

