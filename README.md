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
Anthropic provider requires a Claude Enterprise Analytics API key in
`ANTHROPIC_ANALYTICS_API_KEY`; staging and production also require
`PSEUDONYMIZATION_KEY`. Secret values are redacted from model representations
and validation errors. Analytics API keys and Admin API keys are different
credential types and are not interchangeable.

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

## Anthropic provider

`AnthropicAnalyticsClient` retrieves all cursor pages from the Claude
Enterprise User Activity API for one UTC date. It uses the documented
`x-api-key` and `anthropic-version` headers, validates the complete public
response shape, and converts provider failures to secret-safe application
errors. The result limit and request timeout are configurable with
`ANTHROPIC_RESULT_LIMIT` and `ANTHROPIC_REQUEST_TIMEOUT_SECONDS`.

The implementation is based only on Anthropic's public documentation. Its
automated tests use synthetic responses and mocked HTTP; no real Analytics API
credential or provider connection has been used or tested.

## Normalization and aggregation

The Anthropic adapter maps only genuinely portable concepts into the common
record: provider identity, chat messages, Claude Code sessions, accepted and
rejected edit-tool actions, and the provider's documented daily active-user
definition. All other documented product activity remains typed in an
Anthropic-specific extension instead of being forced into misleading generic
fields.

Organization aggregation rejects empty inputs, mixed reporting dates, duplicate
provider users, incompatible providers, and unavailable required common
metrics. It emits identity-free common totals plus additive Anthropic-specific
activity totals for Claude Code, Cowork, Design, Office, Science, and web
search. Distinct provider fields that cannot be honestly summed into an
organization-wide distinct value remain available on the per-user extension
but are not mislabeled as organization-level distinct counts.

No token, cost, prompt, response, productivity, or production-code values are
created or inferred by normalization or aggregation.

## Privacy boundary

Raw email addresses and provider user identifiers stop at the ingestion and
normalization boundary. Before preview or future telemetry processing, each
provider user identifier is namespaced by provider and pseudonymized with
[HMAC-SHA256](https://www.rfc-editor.org/rfc/rfc2104) using
`PSEUDONYMIZATION_KEY`. Only the first sixteen lowercase hexadecimal characters
are retained. The secret is represented as a Pydantic `SecretStr` and is never
included in exported models or errors.

The resulting privacy-safe collection has three explicit downstream sources:
identity-free collection metadata for tracing, identity-free organization
summaries for metrics, and pseudonymous user records for usage events and
previews. The in-memory JSON preview contains pseudonyms but no emails, raw
provider identifiers, organizational groups, or secret values.

Automated privacy contract tests cover the serialized sources intended for
future telemetry logs, metric attributes, trace attributes, and preview output.
Actual OpenTelemetry providers and exporters are not implemented yet; their
integration tests will additionally enforce these contracts in later
milestones.

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
