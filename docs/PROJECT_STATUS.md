# Project Status

## Current state

Milestones 1 through 9 are complete. The project now has a validated Python
foundation, cached application configuration, strict common usage models, an
asynchronous provider protocol, a synthetic mock analytics client, and a strict
Anthropic Claude Enterprise User Activity API client. Anthropic records can now
be normalized, pseudonymized, aggregated into identity-free organization
summaries, and rendered as privacy-safe in-memory previews. An endpoint-free
FastAPI shell now manages shared OpenTelemetry trace, metric, and log providers
with console or configured OTLP/HTTP exporters. Privacy-safe organization
gauges cover generic normalized concepts and explicitly namespaced Anthropic
concepts. Each protected user record now emits one structured
`genai_user_usage` event to local JSON and the OpenTelemetry log pipeline. No
workflow spans, lifecycle logs, or API endpoints have been implemented yet.

## Completed

- Python 3.13 project metadata managed with `uv`
- `src`-layout application package
- Ruff formatting and lint configuration
- mypy strict type-checking configuration
- pytest configuration and package import test
- Repository hygiene rules and placeholder-only environment example
- MIT license and initial project documentation
- Pydantic v2 and `pydantic-settings` runtime dependencies
- Immutable, cached application settings loaded from environment variables
- Mock and Anthropic provider selection
- Environment-aware pseudonymization and provider credential requirements
- Secret-safe settings representations and validation errors
- Strict normalized identity and common observable activity models
- Generic provider-specific extension model boundary
- Optional activity counts that distinguish unavailable signals from zero
- Comprehensive configuration and domain model tests
- Covariant asynchronous `AnalyticsClient` provider protocol
- Strict mock-provider response models that reject unknown fields and coercion
- Exactly five unique fictional users generated for any requested reporting date
- Synthetic developer and non-developer activity patterns
- Synthetic users with zero, one, and multiple fictional groups
- Accepted and rejected edit-tool action counts
- Chat, Claude Code, Cowork, Design, Office, Science, and web-search activity
- Automated checks that mock records contain no prompt or response fields
- Asynchronous HTTPX integration for the public Claude Enterprise User Activity
  API
- Dedicated Analytics API key configuration, distinct from Admin API keys
- Documented `x-api-key` authentication and Anthropic API-version header
- Configurable request timeout and 1 through 1000 result-limit validation
- Single UTC reporting-date requests for the public data-availability window
- Complete opaque-cursor pagination with repeated-cursor protection
- Strict validation of documented chat, Claude Code, Cowork, Design, Office,
  Science, and web-search response fields
- Secret-safe authentication, authorization, rate-limit, unavailable-date,
  transport, malformed-response, and server-failure errors
- Fully mocked HTTP tests covering request construction and multiple pages
- Anthropic-to-common normalization for identity, chat messages, Claude Code
  sessions, tool actions, and the documented daily active-user definition
- Strict Anthropic usage extension preserving all supported product categories
- Explicit omission of grouping metadata from the normalized provider extension
- No invented token, cost, prompt, response, or productivity fields
- Generic organization-summary extension boundary for future provider totals
- Additive Anthropic totals for Claude Code, Cowork, Design, Office, Science,
  and web-search activity
- Organization summaries containing no individual identity or group fields
- Empty-input, mixed-date, duplicate-user, incompatible-provider, and
  unavailable-common-metric rejection
- Tool-action acceptance rates constrained to zero through one, including zero
  when no tool actions occurred
- Provider-namespaced HMAC-SHA256 pseudonymization using
  `PSEUDONYMIZATION_KEY`
- Stable pseudonyms limited to the required first sixteen lowercase hexadecimal
  characters
- Secret-redacted pseudonymizer construction and validation errors
- Explicit privacy-safe Anthropic extension that rejects identity and group
  fields
- Pseudonymous user records containing no email or raw provider identifier
- Identity-free organization summary and collection metadata sources
- Cross-record validation for dates, providers, counts, and pseudonym uniqueness
- Deterministic in-memory JSON preview containing only privacy-safe data
- Automated proofs that raw identities and group data are absent from serialized
  log, metric-attribute, trace-attribute, and preview sources
- FastAPI lifespan application shell with no routes or generated documentation
  endpoints
- One shared OpenTelemetry Resource for trace, metric, and log providers
- Official `service.name`, `service.version`, and current
  `deployment.environment.name` resource conventions
- Explicitly documented custom `telemetry.source` resource attribute
- Reference-counted, idempotent telemetry initialization across lifespan entries
- Explicit force-flush and clean shutdown for logger, meter, and tracer providers
- Development console export for logs, metrics, and traces
- Configurable OTLP/HTTP export with derived standard per-signal paths
- No built-in collector endpoint or implicit network destination
- Optional percent-encoded OTLP headers with secret-safe validation errors
- Provider initialization without exporters outside development when no OTLP
  endpoint is configured
- Lifecycle tests covering resource sharing, initialization, flush, shutdown,
  console, disabled, and mocked OTLP modes
- Synchronous gauges for absolute daily totals so collection retries replace
  rather than accumulate organization values
- Seven custom `genai.usage.organization` gauges limited to genuinely normalized
  common user, activity, session, tool-action, and acceptance concepts
- Thirty-five custom `anthropic.usage.organization` gauges preserving Claude
  Code, Cowork, Design, Office, Science, and web-search semantics
- Explicit custom metric definitions with names, UCUM-compatible annotated
  units, and descriptions
- Exactly four allowlisted metric dimensions: reporting date, deployment
  environment, telemetry source, and provider
- No raw or pseudonymous identifiers, emails, groups, paths, endpoints, or
  credential data in actual emitted metric attributes
- In-memory OpenTelemetry SDK tests proving all 42 metric names, values, units,
  last-value behavior, provider consistency, attribute allowlisting, and privacy
- Strict `genai_user_usage` body schema built only from post-privacy records
- Exactly one structured usage event per protected user record in a collection
- Reporting date, provider, pseudonymous identifier, normalized common activity,
  and explicitly approved Anthropic activity in each event
- One compact JSON line per event during local development
- Direct OpenTelemetry Logs API emission with the required EventName and INFO
  severity through the shared LoggerProvider
- Identical structured bodies across local JSON and OpenTelemetry destinations
- No raw identities, groups, secrets, credentials, authentication headers,
  paths, or endpoints in actual emitted event bodies or attributes
- In-memory log-export tests covering exact counts, complete safe fields,
  EventName, severity, JSON parity, provider validation, and privacy

## Validation

Validated with an isolated `uv`-managed CPython 3.13.13 environment:

- Dependency lock and synchronization completed successfully
- Ruff formatting check passed
- Ruff lint check passed
- mypy strict type checking passed
- pytest passed: 164 tests
- Source coverage: 100% (836 statements)
- Installed-package import validation passed and reported version `0.1.0`

## Known limitations

- The Anthropic client currently uses the single-day, ungrouped User Activity
  query needed by the gateway; newer range, filtering, grouping, and ordering
  API options are intentionally outside this milestone.
- Normalized records intentionally retain raw identity only until the privacy
  boundary; downstream code must consume privacy-safe collection models.
- Preview rendering is currently in-memory only. No API endpoint or local file
  workflow exposes it yet.
- OpenTelemetry providers, exporters, organization metrics, and pseudonymous
  usage events are implemented, but collection spans and lifecycle log records
  are not.
- Only the Anthropic provider has a normalization and aggregation adapter; the
  synthetic mock provider remains an ingestion fixture for local development.
- The Anthropic integration has been tested only with synthetic mocked HTTP
  responses. No real Analytics API credential or provider connection has been
  tested.
- No real OTLP collector delivery has been tested.

## Next recommended milestone

Milestone 10: trace each complete collection workflow with one
`genai.usage.collection` span, safe operational attributes, explicit success and
failure status, exception recording, and original-exception propagation.
