# GenAI Usage Observability Gateway

An extensible, privacy-conscious GenAI usage observability gateway that
collects enterprise AI usage analytics, normalizes provider data, applies
privacy controls, and exports organization metrics, pseudonymous usage events,
collection lifecycle events, and workflow traces through OpenTelemetry.

Anthropic Claude Enterprise is the first reference provider implementation. A
synthetic mock provider supports the complete local workflow and API without
external credentials.

## Goal and business problem

Enterprise GenAI tools can be licensed broadly while decision-makers still
lack a trustworthy view of adoption: how many people use the tools, whether
usage changes over time, which exposed capabilities are used, and whether
developer-oriented features receive observable activity. Provider analytics
APIs expose parts of that picture, but their schemas differ and sending raw
employee identities into another telemetry system creates avoidable privacy
risk.

This project explores a provider-extensible boundary that retrieves available
analytics, validates and normalizes only honest common concepts, removes raw
identity, aggregates organization totals, and exports privacy-conscious
OpenTelemetry signals. Adoption visibility can inform license and enablement
decisions, but it is only one input: the gateway does not turn activity counts
into conclusions about people or business outcomes.

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

## Architecture

```text
Provider analytics APIs
        |
Provider adapters and strict response validation
        |
Small common usage model + provider-owned extensions
        |
HMAC pseudonymization and explicit privacy-safe models
        |
Organization aggregation
        |
OpenTelemetry metrics, logs/events, and traces
        |
OTLP/HTTP -> operator-selected collector and backend
```

The provider protocol owns asynchronous retrieval for one UTC reporting date.
Each adapter also owns its response schema, normalization function, privacy-safe
extension, organization aggregation, and provider-specific telemetry. The
common model is deliberately small so future adapters are not forced to label
provider-only data as portable.

Signal choice follows data shape:

- Organization totals use metrics because they are identity-free, bounded,
  low-cardinality measurements suited to trend and utilization views.
- Pseudonymous per-user activity uses structured log events because each
  protected record is a discrete, inspectable observation, not a metric label.
- The complete collection uses one trace because retrieval, mapping, privacy,
  aggregation, emission, and preview generation form one operational workflow.

See [Architecture](docs/architecture.md) for component boundaries, data flow,
and the common-versus-provider-specific design.

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

| Variable | Purpose | Default |
| --- | --- | --- |
| `APP_ENVIRONMENT` | `development`, `test`, `staging`, or `production` | `development` |
| `ANALYTICS_PROVIDER` | Select `mock` or `anthropic` | `mock` |
| `PSEUDONYMIZATION_KEY` | Secret HMAC key; required for Anthropic and outside local environments | unset |
| `ANTHROPIC_ANALYTICS_API_KEY` | Claude Enterprise Analytics API key | unset |
| `ANTHROPIC_RESULT_LIMIT` | Upstream page size from 1 through 1000 | `100` |
| `ANTHROPIC_REQUEST_TIMEOUT_SECONDS` | Positive upstream request timeout, at most 120 seconds | `10` |
| `PREVIEW_ENABLED` | Explicit preview override; empty uses the environment default | environment-aware |
| `PREVIEW_OUTPUT_PATH` | Local development preview destination | `telemetry-output/usage-preview.json` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP/HTTP collector base URL | unset |
| `OTEL_EXPORTER_OTLP_HEADERS` | Percent-encoded OTLP header list; treat as secret | unset |

Use [.env.example](.env.example) only as a local template. It contains
placeholders, not usable credentials. Prefer a secret manager or runtime secret
injection outside local development.

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
- [`uv`](https://docs.astral.sh/uv/) 0.11 or newer

Install `uv` using its
[official installation instructions](https://docs.astral.sh/uv/getting-started/installation/),
then confirm it and Python 3.13 are available:

```shell
uv --version
uv python find 3.13
```

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

### Anthropic mode

Real Anthropic collection requires valid Claude Enterprise Analytics access;
an ordinary Admin API key is not interchangeable. Inject secrets at runtime:

```shell
export ANALYTICS_PROVIDER=anthropic
export PSEUDONYMIZATION_KEY='replace-with-a-secret-from-your-secret-manager'
export ANTHROPIC_ANALYTICS_API_KEY='replace-with-a-valid-analytics-key'
uv run uvicorn genai_usage_observability_gateway.app:app \
  --host 127.0.0.1 --port 8000 --no-access-log
```

The implementation has been tested with mocked HTTP only. These commands do
not imply that a real credential, account, or provider connection was tested by
this project.

## API examples

With the service running on `127.0.0.1:8000`:

```shell
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/live
curl http://127.0.0.1:8000/health/ready
curl -X POST \
  "http://127.0.0.1:8000/collect?reporting_date=2026-02-03"
curl http://127.0.0.1:8000/preview
```

`POST /collect` returns an organization summary only. In default development
mode the collection also writes a post-privacy preview, so the final request can
inspect the complete synthetic result. `GET /preview` returns a disabled status
when preview generation is off and a safe `404` error when it is enabled but no
artifact exists.

## Console and OTLP telemetry

Development without an OTLP endpoint writes console traces, metric export, and
compact JSON usage and lifecycle records. Run one collection and observe the
Uvicorn process output. Some metric exporters emit periodically, so allow the
process to flush on shutdown.

To target a collector that you operate, configure its base URL and optional
headers before startup:

```shell
export OTEL_EXPORTER_OTLP_ENDPOINT='https://collector.example.test:4318'
export OTEL_EXPORTER_OTLP_HEADERS='authorization=Bearer%20replace-me'
```

The gateway derives `/v1/traces`, `/v1/metrics`, and `/v1/logs`. The example
domain and credential are deliberately fictional. No collector is bundled or
hardcoded, and actual delivery cannot be verified without access to a real
collector.

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

## Project structure

```text
.
|-- .github/workflows/quality.yml  # CI quality and container checks
|-- docs/                          # architecture, privacy, extension, roadmap
|-- src/genai_usage_observability_gateway/
|   |-- providers/                 # provider protocols and response clients
|   |-- models/                    # common strict domain models
|   |-- normalization.py           # provider-to-common mappings
|   |-- privacy.py                 # pseudonymization and safe boundaries
|   |-- aggregation.py             # organization summaries
|   |-- telemetry.py               # shared OpenTelemetry runtime
|   |-- organization_metrics.py    # identity-free gauges
|   |-- usage_events.py            # pseudonymous structured events
|   |-- workflow.py                # traced collection orchestration
|   |-- preview.py                 # post-privacy atomic JSON preview
|   `-- app.py                     # FastAPI lifespan, routes, safe errors
|-- tests/                         # unit, integration-boundary, privacy tests
|-- Dockerfile
|-- pyproject.toml
`-- uv.lock
```

## Security and privacy considerations

- Treat provider keys, the pseudonymization key, and OTLP headers as secrets;
  rotate them according to the operator's policy and never commit them.
- Use HTTPS endpoints, outbound network controls, and an authenticated
  collector in any nonlocal deployment.
- A 16-character HMAC pseudonym is still linkable for the same key and provider.
  It reduces direct identity exposure; it is not anonymization.
- Restrict access to pseudonymous events and previews. They can still describe
  a person's activity pattern and may be sensitive under organizational policy
  or applicable law.
- Keep previews disabled outside a controlled development use case, minimize
  retention, and protect local filesystem permissions.
- Review a new provider's fields before allowing them beyond the privacy
  boundary. Unknown upstream fields are rejected rather than exported.

See [Privacy](docs/privacy.md) for the data classification, trust boundaries,
threats, guarantees, and operator responsibilities.

## Known limitations

- This is pre-alpha reference software, not a production-ready service and not
  evidence of deployment or adoption by any organization.
- The Anthropic boundary has only synthetic mocked-HTTP test coverage; no real
  provider credential or connection has been tested.
- No real OTLP collector delivery or backend visualization has been tested.
- Provider analytics availability and semantics are controlled by each
  provider. The implemented Anthropic API may not expose token or cost data,
  and the gateway does not invent either.
- The current service is stateless apart from optional local development
  preview output. It has no scheduler, durable job queue, authentication layer,
  authorization policy, rate limiter, database, or multi-tenant control plane.
- The HMAC key has no built-in rotation or pseudonym migration mechanism.
- Local container build verification depends on Docker or Podman; the current
  development host has neither, so CI is the intended Linux build boundary.

Detailed implementation limitations remain tracked in
[Project Status](docs/PROJECT_STATUS.md).

## Roadmap and provider extension

[Roadmap](docs/roadmap.md) separates validated current capabilities from
possible future work. It does not promise future provider support or production
readiness. [Adding a provider](docs/adding_a_provider.md) lists the concrete
schemas, normalization, privacy, aggregation, workflow, telemetry, service, and
test changes required for another public analytics API.

Future provider work must use public documentation, preserve provider-specific
meaning, mock all external requests in tests, and pass the same privacy
contracts. OpenAI, Azure OpenAI, Google Gemini, GitHub Copilot, and internal LLM
gateways are possible research directions only; they are not implemented in
version 0.1.

## License

Licensed under the [MIT License](LICENSE).
