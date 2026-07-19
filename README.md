# GenAI Usage Observability Gateway

An extensible, privacy-conscious GenAI usage observability gateway that
collects enterprise AI usage analytics, normalizes provider data, applies
privacy controls, and exports organization metrics, pseudonymous usage events,
collection lifecycle events, and workflow traces through OpenTelemetry.

Anthropic Claude Enterprise is the first reference provider implementation. A
synthetic mock provider supports the complete local workflow and API without
external credentials.

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

The project has a tested FastAPI collection surface plus ingestion,
normalization, privacy, aggregation, preview, and OpenTelemetry foundations. It
is not production-ready. See
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

In development and test, mock mode uses an application-owned synthetic
pseudonymization namespace when `PSEUDONYMIZATION_KEY` is unset. Real provider
workflows and nonlocal environments never receive that fallback.

## Mock provider

`MockAnalyticsClient` implements the asynchronous provider protocol using only
synthetic data. Each requested date returns exactly five fictional users with
varied activity and group membership, including developer and non-developer
patterns, accepted and rejected edit-tool actions, and an inactive user. The
mock adapter carries those records through normalization, privacy processing,
organization aggregation, metrics, usage and lifecycle events, tracing, and
preview generation while keeping the provider labeled `mock`.

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

Provider adapters map only genuinely portable concepts into the common record:
provider identity, chat messages, developer sessions, accepted and rejected
edit-tool actions, and an explicit provider-appropriate active-user signal. All
other product activity remains typed in its provider-owned extension instead of
being forced into misleading generic fields. The Anthropic adapter uses the
provider's documented daily active-user definition; the mock adapter uses only
its declared synthetic schema.

Organization aggregation rejects empty inputs, mixed reporting dates, duplicate
provider users, incompatible providers, and unavailable required common
metrics. It emits identity-free common totals plus additive, explicitly typed
provider activity totals for Claude Code, Cowork, Design, Office, Science, and
web search. Distinct provider fields that cannot be honestly summed into an
organization-wide distinct value remain available on the per-user extension
but are not mislabeled as organization-level distinct counts.

No token, cost, prompt, response, productivity, or production-code values are
created or inferred by normalization or aggregation.

## Privacy boundary

Raw email addresses and provider user identifiers stop at the ingestion and
normalization boundary. Before preview or future telemetry processing, each
provider user identifier is namespaced by provider and pseudonymized with
[HMAC-SHA256](https://www.rfc-editor.org/rfc/rfc2104) using the configured
`PSEUDONYMIZATION_KEY` or the mock-only local fallback described above. Only the
first sixteen lowercase hexadecimal characters are retained. Key material is
represented as a Pydantic `SecretStr` and is never included in exported models
or errors.

The resulting privacy-safe collection has three explicit downstream sources:
identity-free collection metadata for tracing, identity-free organization
summaries for metrics, and pseudonymous user records for usage events and
previews. The JSON preview contains pseudonyms but no emails, raw provider
identifiers, organizational groups, or secret values.

Automated privacy contract tests cover structured usage events, lifecycle
events, metric attributes, workflow spans, and preview output.

## OpenTelemetry foundation

The FastAPI application initializes one shared trace, metric, and log provider
set during its lifespan, then force-flushes and shuts the providers down after
the final lifespan lease. Repeated initialization is idempotent and does not add
duplicate exporters.

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

Each privacy-safe organization summary records seven generic synchronous gauges
under the custom `genai.usage.organization` namespace. Anthropic summaries also
record 35 provider-only product gauges under the custom
`anthropic.usage.organization` namespace; mock summaries do not masquerade as
Anthropic telemetry. Gauges preserve the latest absolute daily totals when a
reporting date is collected more than once; they do not incorrectly accumulate
a retry as new activity.

Every datapoint has exactly four allowlisted dimensions: reporting date,
deployment environment, telemetry source, and provider. Metric attributes never
contain emails, raw or pseudonymous user identifiers, organizational groups,
file paths, API endpoints, or credential data. The metric and attribute names
owned by this project are custom telemetry and are not presented as official
OpenTelemetry semantic conventions.

## Structured usage events

Every post-privacy user record produces exactly one `genai_user_usage` event.
The body contains the reporting date, provider, pseudonymous identifier,
normalized common activity, and the explicitly approved provider activity
extension. It never accepts emails, raw provider identifiers, organizational
groups, credentials, authentication headers, file paths, or API endpoints.

In development, each event is written as one compact JSON line. The same
structured body is emitted through the shared OpenTelemetry LoggerProvider with
`genai_user_usage` as the EventName, allowing configured OTLP/HTTP log export.
These are two destinations for one logical event and use an identical payload.

## Collection workflow tracing

The Anthropic and mock collection workflows run provider retrieval and
validation, normalization, privacy processing, aggregation, metric and event
emission, and preview generation with optional persistence inside one
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

## FastAPI service

The importable ASGI application is
`genai_usage_observability_gateway.app:app`. It exposes only these routes;
interactive documentation and the OpenAPI route remain disabled:

- `GET /` returns service metadata and the endpoint inventory.
- `GET /health` reports process health.
- `GET /health/live` reports liveness without contacting a provider.
- `GET /health/ready` validates selected-provider configuration without
  returning configured values.
- `POST /collect?reporting_date=YYYY-MM-DD` executes one complete collection and
  returns only the privacy-safe organization summary, never user records.
- `GET /preview` returns parsed post-privacy preview JSON when enabled, a clear
  disabled response when off, and `404` when the configured artifact is absent.

Errors use one JSON envelope with a stable code, safe message, and retryable
flag. Validation, configuration, provider authentication and authorization,
rate limiting, upstream availability and schema failures, preview failures, and
unexpected collection failures are mapped without copying exception details,
request values, headers, credentials, paths, or provider response bodies.

## Development setup

Prerequisites:

- Python 3.13
- [`uv`](https://docs.astral.sh/uv/)

Create the environment and install locked dependencies:

```shell
uv sync --locked --dev
```

Start the service in credential-free mock mode:

```shell
uv run uvicorn genai_usage_observability_gateway.app:app \
  --host 127.0.0.1 --port 8000 --no-access-log
```

Then request one synthetic reporting date:

```shell
curl -X POST "http://127.0.0.1:8000/collect?reporting_date=2026-02-03"
```

The response is an organization summary for exactly five fictional users. It
does not contain the pseudonymous per-user events, raw identifiers, emails, or
fictional group membership processed inside the workflow.

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

## Container

Build and run the service without Compose:

```shell
docker build -t genai-usage-observability-gateway .
docker run --rm -p 8000:8000 genai-usage-observability-gateway
```

The multi-stage image installs the locked production dependency set into a
non-editable virtual environment, copies only that environment into the runtime
stage, and runs as numeric user and group `10001`. Its credential-free default
is synthetic mock mode with preview persistence and HTTP access logs disabled.
For Anthropic or nondevelopment use, supply the required settings at runtime;
never bake environment files, keys, or OTLP headers into an image.

No Compose configuration is included because the gateway is stateless and does
not require a database, frontend, collector, or other companion service.

## Continuous integration

The GitHub Actions quality workflow uses Python 3.13 and the locked dependency
graph. It checks formatting, linting, strict static typing, the complete test
suite with terminal and XML coverage reporting plus an 85% minimum, and package
importability. A separate job builds the container and verifies that its
application imports while running as user `10001`.

## License

Licensed under the [MIT License](LICENSE).
