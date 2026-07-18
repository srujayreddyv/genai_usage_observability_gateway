# GenAI Usage Observability Gateway

An extensible, privacy-conscious GenAI usage observability gateway that
collects enterprise AI usage analytics, normalizes provider data, applies
privacy controls, and exports organization metrics, pseudonymous usage events,
and collection workflow traces through OpenTelemetry.

Anthropic Claude Enterprise is planned as the first reference provider
implementation. A synthetic mock provider will support local development and
testing without external credentials.

## Scope

This project focuses on usage and adoption observability. It is not a complete
LLM runtime observability platform. It does not inspect prompts or responses,
determine whether an employee is performing personal or professional work, or
measure individual employee productivity.

The gateway provides observable usage and engineering activity signals that
organizations may use as one input when understanding GenAI adoption and
utilization. Usage telemetry does not prove productivity or that production
code was created.

## Project status

The project is in its foundation stage and is not production-ready. See
[`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) for completed work, known
limitations, and the next planned milestone.

## Development setup

Prerequisites:

- Python 3.13
- [`uv`](https://docs.astral.sh/uv/)

Create the environment and install locked dependencies:

```shell
uv sync --dev
```

Run the foundation checks:

```shell
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
uv run python -c "import genai_usage_observability_gateway"
```

Copy `.env.example` to `.env` only when local configuration is needed. Local
environment files, credentials, generated previews, caches, and telemetry
output must never be committed.

## License

Licensed under the [MIT License](LICENSE).
