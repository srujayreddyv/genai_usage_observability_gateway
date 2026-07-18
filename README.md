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

The project has foundational configuration and domain models and is not
production-ready. See
[`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) for completed work, known
limitations, and the next planned milestone.

## Configuration

Settings are loaded from environment variables and an optional local `.env`
file using `pydantic-settings`. Mock mode is the local default. Selecting the
Anthropic provider requires `ANTHROPIC_ADMIN_API_KEY`; staging and production
also require `PSEUDONYMIZATION_KEY`. Secret values are redacted from model
representations and validation errors.

The normalized usage model contains only portable identity and observable
activity concepts. Provider adapters retain unique capabilities in strict,
typed provider-extension models. Optional activity counts distinguish a signal
that was not exposed (`null`) from an exposed signal with no activity (`0`).

## Mock provider

`MockAnalyticsClient` implements the asynchronous provider protocol using only
synthetic data. Each requested date returns exactly five fictional users with
varied activity and group membership, including developer and non-developer
patterns, accepted and rejected edit-tool actions, and an inactive user.

The mock provider-owned response schema exercises product categories exposed by
Anthropic's public [User Activity API](https://platform.claude.com/docs/en/api/admin/analytics/users/list.md):
chat, Claude Code, Cowork, Design, Office products, Science, and web search. It
contains no prompts, responses, tokens, costs, or real identities.

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
uv run pytest --cov=genai_usage_observability_gateway
uv run python -c "import genai_usage_observability_gateway"
```

Copy `.env.example` to `.env` only when local configuration is needed. Local
environment files, credentials, generated previews, caches, and telemetry
output must never be committed.

## License

Licensed under the [MIT License](LICENSE).
