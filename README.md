# GenAI Usage Observability Gateway

An extensible, privacy-conscious GenAI usage observability gateway that
collects enterprise AI usage analytics, normalizes provider data, applies
privacy controls, and exports organization metrics, pseudonymous usage events,
collection lifecycle events, and workflow traces through OpenTelemetry.

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

The project has ingestion, normalization, privacy, aggregation, and
OpenTelemetry lifecycle foundations and is not production-ready. See
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

Development preview persistence defaults on only when `APP_ENVIRONMENT` is
`development`; test, staging, and production default it off. Set
`PREVIEW_ENABLED` explicitly to override that environment-aware default and
`PREVIEW_OUTPUT_PATH` to choose the local JSON destination. Preview paths are
configuration only and are never attached to telemetry.

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
previews. The JSON preview contains pseudonyms but no emails, raw provider
identifiers, organizational groups, or secret values.

Automated privacy contract tests cover structured usage events, lifecycle
events, metric attributes, workflow spans, and preview output.

## OpenTelemetry foundation

The endpoint-free FastAPI application shell initializes one shared trace,
metric, and log provider set during its lifespan, then force-flushes and shuts
the providers down after the final lifespan lease. Repeated initialization is
idempotent and does not add duplicate exporters.

Development uses console exporters when no OTLP endpoint is configured. Set
`OTEL_EXPORTER_OTLP_ENDPOINT` to a collector's base HTTPS URL to use OTLP over
HTTP; the standard `/v1/traces`, `/v1/metrics`, and `/v1/logs` paths are derived
from that configured base. Optional `OTEL_EXPORTER_OTLP_HEADERS` values use
comma-separated, percent-encoded `key=value` pairs and remain secret-redacted.
No collector address is built into the application. Without an endpoint,
non-development environments initialize providers without exporters.

The shared resource uses the official `service.name`, `service.version`, and
current `deployment.environment.name` semantic conventions. `telemetry.source`
is a custom project attribute, not an official OpenTelemetry convention.

## Organization metrics

Each privacy-safe organization summary records 42 synchronous gauges: seven
generic normalized adoption and usage concepts under the custom
`genai.usage.organization` namespace, and 35 Anthropic-only product concepts
under the custom `anthropic.usage.organization` namespace. Gauges preserve the
latest absolute daily totals when a reporting date is collected more than once;
they do not incorrectly accumulate a retry as new activity.

Every datapoint has exactly four allowlisted dimensions: reporting date,
deployment environment, telemetry source, and provider. Metric attributes never
contain emails, raw or pseudonymous user identifiers, organizational groups,
file paths, API endpoints, or credential data. The metric and attribute names
owned by this project are custom telemetry and are not presented as official
OpenTelemetry semantic conventions.

## Structured usage events

Every post-privacy user record produces exactly one `genai_user_usage` event.
The body contains the reporting date, provider, pseudonymous identifier,
normalized common activity, and the explicitly approved Anthropic activity
extension. It never accepts emails, raw provider identifiers, organizational
groups, credentials, authentication headers, file paths, or API endpoints.

In development, each event is written as one compact JSON line. The same
structured body is emitted through the shared OpenTelemetry LoggerProvider with
`genai_user_usage` as the EventName, allowing configured OTLP/HTTP log export.
These are two destinations for one logical event and use an identical payload.

## Collection workflow tracing

`AnthropicCollectionWorkflow` runs provider retrieval and validation,
normalization, privacy processing, aggregation, metric and event emission, and
preview generation with optional persistence inside one
`genai.usage.collection` span. Completed spans contain only the provider,
bounded client type, reporting date, record count, and collection status.

Successful spans retain the default unset OpenTelemetry status and record a
`success` collection status. Failures record the exception once through the
OpenTelemetry API, set the span status to error, mark the collection `failed`,
and re-raise the original exception. Exception messages and stack traces are
replaced with fixed privacy-safe event values so credentials, identities, or
local source paths cannot enter trace data.

## Collection lifecycle events

Each collection emits named `collection_started`, `records_mapped`,
`aggregation_completed`, `preview_written`, and `collection_completed`
OpenTelemetry log events in order. A failed collection emits
`collection_failed` instead of later success checkpoints. Normal checkpoints
use INFO severity; failure uses ERROR severity without copying the exception or
its message into the log record.

Lifecycle attributes are limited to custom project fields for reporting date,
provider, bounded client type, collection status, cumulative monotonic duration
in whole milliseconds, and record count once mapping has completed. Records are
emitted inside the collection span and inherit its trace context. Development
also receives one compact JSON line per lifecycle event. `preview_written` is
emitted after the privacy-safe preview payload is produced and, when configured,
after its atomic file replacement succeeds.

## Development preview

The readable preview document contains the reporting date, collection timestamp
normalized to UTC, provider, pseudonymous user usage records, and identity-free
organization snapshot. It is built only from the post-privacy collection
boundary.

When enabled, missing parent directories are created and the complete JSON
document is written to a securely created temporary sibling. The file is
flushed before `os.replace` atomically replaces the configured destination, so
a failed write cannot leave a partially updated preview. Generated preview
files and the default `telemetry-output/` directory are ignored by Git.

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
