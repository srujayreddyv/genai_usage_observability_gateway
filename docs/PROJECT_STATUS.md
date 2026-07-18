# Project Status

## Current state

Milestones 1 through 4 are complete. The project now has a validated Python
foundation, cached application configuration, strict common usage models, an
asynchronous provider protocol, a synthetic mock analytics client, and a strict
Anthropic Claude Enterprise User Activity API client. No normalization
workflow, API service, privacy processing, or telemetry export has been
implemented yet.

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

## Validation

Validated with an isolated `uv`-managed CPython 3.13.13 environment:

- Dependency lock and synchronization completed successfully
- Ruff formatting check passed
- Ruff lint check passed
- mypy strict type checking passed
- pytest passed: 83 tests
- Source coverage: 100% (354 statements)
- Installed-package import validation passed and reported version `0.1.0`

## Known limitations

- Provider response records are not normalized into the common domain model yet.
- The Anthropic client currently uses the single-day, ungrouped User Activity
  query needed by the gateway; newer range, filtering, grouping, and ordering
  API options are intentionally outside this milestone.
- The Anthropic integration has been tested only with synthetic mocked HTTP
  responses. No real Analytics API credential or provider connection has been
  tested.
- No real OTLP collector delivery has been tested.

## Next recommended milestone

Milestone 5: map Anthropic provider records into honest common normalized usage
records, preserve provider-specific capabilities in an Anthropic extension,
and implement validated organization aggregation calculations.
