# Project Status

## Current state

Milestones 1 through 14 are complete. The project now has a validated Python
foundation, strict provider and common usage models, complete synthetic mock and
Anthropic collection paths, an explicit privacy boundary, identity-free
organization aggregation, and a FastAPI service for health, readiness,
collection, and development preview access. The mock provider completes the
same normalized, pseudonymized, aggregated, traced, and observable lifecycle as
the real-provider adapter while retaining its own schema and provider label.

Shared OpenTelemetry trace, metric, and log providers support development
console output or configured OTLP/HTTP export. Every collection uses one
`genai.usage.collection` span, emits ordered privacy-safe lifecycle events,
records low-cardinality organization gauges, and emits one pseudonymous usage
event per protected user. Preview output is generated only after privacy
processing, can be atomically persisted in development, and defaults off in
every other environment. The API returns organization summaries only from the
collection route and uses secret-safe JSON errors at every HTTP boundary. A
locked multi-stage container runs the ASGI service as a numeric nonroot user,
and GitHub Actions enforces the complete local quality gate set and validates
the container build.

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
- FastAPI lifespan initialization with generated documentation endpoints
  disabled
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
  and explicitly approved provider activity in each event
- One compact JSON line per event during local development
- Direct OpenTelemetry Logs API emission with the required EventName and INFO
  severity through the shared LoggerProvider
- Identical structured bodies across local JSON and OpenTelemetry destinations
- No raw identities, groups, secrets, credentials, authentication headers,
  paths, or endpoints in actual emitted event bodies or attributes
- In-memory log-export tests covering exact counts, complete safe fields,
  EventName, severity, JSON parity, provider validation, and privacy
- In-memory Anthropic and mock collection workflows spanning provider retrieval
  and validation, normalization, privacy processing, aggregation, telemetry
  emission, and preview generation
- Exactly one `genai.usage.collection` span for each complete workflow
- Bounded trace attributes for provider, client type, reporting date, record
  count, and collection status only
- Explicit `success` and `failed` collection status values with record counts on
  successful spans
- Usage-event trace correlation proving telemetry emission occurs inside the
  collection span
- Error status, one OpenTelemetry exception event, and same-instance exception
  propagation on workflow failure
- Privacy-safe fixed exception type, message, and stack-trace fields preventing
  source paths or sensitive exception details from entering trace data
- Successful and failed in-memory span-export tests covering output generation,
  status, attributes, event count, trace privacy, and provider mismatch
- Strict lifecycle event schema limited to reporting date, provider, bounded
  client type, collection status, cumulative duration, and record count
- Ordered `collection_started`, `records_mapped`, `aggregation_completed`,
  `preview_written`, and `collection_completed` success checkpoints
- Alternative ERROR-severity `collection_failed` event with no exception body,
  message, credential, configuration, identity, endpoint, or path data
- Cumulative workflow durations measured with a monotonic nanosecond clock and
  emitted as nonnegative whole milliseconds
- Record counts omitted before mapping, included on every later checkpoint, and
  retained on failures occurring after mapping
- Direct OpenTelemetry EventName emission through the shared LoggerProvider and
  compact JSON lifecycle records in development
- Lifecycle events correlated to the active collection trace and independently
  scoped from pseudonymous per-user usage events
- In-memory and local-stream tests covering event order, exact attribute
  allowlists, duration values, severity, status consistency, trace correlation,
  success, early failure, post-mapping failure, and privacy
- Strict preview document with top-level reporting date, UTC collection
  timestamp, provider, pseudonymous usage records, and organization snapshot
- Environment-aware preview enablement that defaults on in development and off
  in test, staging, and production while allowing an explicit override
- Configurable preview destination kept out of spans, logs, metrics, and events
- Missing preview parent-directory creation using the configured local path
- Secure temporary sibling creation, UTF-8 readable JSON output, explicit
  flushing and filesystem synchronization, and same-filesystem atomic replace
- Failure cleanup that removes temporary artifacts while preserving an existing
  complete destination when replacement fails
- Workflow persistence after privacy processing and before the correlated
  `preview_written` lifecycle checkpoint
- Temporary-directory tests covering required fields, UTC normalization,
  readable formatting, atomic success and failure, descriptor cleanup,
  environment defaults, workflow integration, and absence of raw identities,
  groups, and secrets
- Mock normalization and aggregation preserving synthetic product semantics
  without presenting mock records or metrics as Anthropic data
- Mock post-privacy collections, organization summaries, usage events,
  lifecycle events, traces, and development previews
- Local development and test fallback namespace for mock-only pseudonymization
  when no real secret is configured
- `GET /` service metadata and exact endpoint inventory
- `GET /health` process health and provider-independent `GET /health/live`
- `GET /health/ready` selected-provider configuration validation without secret
  values or upstream network access
- Required date query validation for `POST /collect`
- Provider-selected collection execution returning only a privacy-safe
  organization summary and no per-user records
- Parsed `GET /preview` responses with explicit disabled behavior and `404` for
  an enabled but absent artifact
- Consistent JSON error envelopes for input, configuration, provider
  authentication, authorization, rate limiting, availability, server, schema,
  preview, collection, HTTP, and unexpected failures
- Safe HTTP errors that never echo validation input, exception details,
  credentials, authentication headers, keys, local paths, request URLs, or
  provider response bodies
- API contract and provider-service tests covering all routes, status mappings,
  provider selection, mock collection, and preview loading
- Locked Uvicorn ASGI runtime dependency for local and container execution
- Multi-stage Python 3.13 container build using the pinned official uv image
- Non-editable production dependency installation with no source tree or build
  tool copied into the final runtime image
- Numeric nonroot runtime user and group `10001`
- Credential-free container defaults using mock mode with preview persistence
  and HTTP access logging disabled
- Focused `.dockerignore` excluding Git metadata, environment files, virtual
  environments, tests, caches, coverage, documentation, and generated output
- Least-privilege GitHub Actions workflow for pushes, pull requests, and manual
  runs with concurrency cancellation
- Locked dependency synchronization, Ruff formatting and lint checks, strict
  mypy, complete pytest execution, XML and terminal coverage reporting, an 85%
  coverage floor, and application import validation in CI
- Independent container build job proving the packaged application imports as
  nonroot user `10001`
- Deliberate omission of Compose because no required companion services exist

## Validation

Validated with an isolated `uv`-managed CPython 3.13.13 environment:

- Dependency lock and synchronization completed successfully
- Ruff formatting check passed
- Ruff lint check passed
- mypy strict type checking passed
- pytest passed: 239 tests
- Source coverage: 100% (1473 statements)
- Installed-package import validation passed and reported version `0.1.0`

## Known limitations

- The Anthropic client currently uses the single-day, ungrouped User Activity
  query needed by the gateway; newer range, filtering, grouping, and ordering
  API options are intentionally outside this milestone.
- Normalized records intentionally retain raw identity only until the privacy
  boundary; downstream code must consume privacy-safe collection models.
- Preview files remain local development artifacts. When explicitly enabled,
  the API reads only the configured preview file and validates its complete
  privacy-safe schema before returning it.
- The Anthropic integration has been tested only with synthetic mocked HTTP
  responses. No real Analytics API credential or provider connection has been
  tested.
- No real OTLP collector delivery has been tested.
- The container build cannot be executed on the current development host
  because no Docker or Podman engine is installed; the GitHub Actions container
  job is the reproducible Linux validation boundary.

## Next recommended milestone

Milestone 15: expand the README and add focused architecture, privacy,
provider-extension, and roadmap documents without overstating production
readiness, real-provider testing, or real collector delivery.
