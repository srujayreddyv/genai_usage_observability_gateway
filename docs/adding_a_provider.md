# Adding a provider

## Before implementation

Add a provider only when a current public analytics API exposes data that can
support the gateway's usage-observability purpose. Record the authoritative
documentation URLs, authentication mechanism, availability window, pagination,
rate limits, response fields, and error behavior. Do not infer undocumented
fields or adapt a runtime inference API as though it were an organization
analytics API.

Use synthetic fixtures and mocked HTTP in automated tests. Never use corporate
source code, internal endpoints, production payloads, real employee identities,
or committed credentials.

## Required implementation work

The architecture is extensible, but version 0.1 uses explicit typed provider
branches. A provider is not complete after merely satisfying the client
protocol. Make each of these deliberate changes.

### 1. Configuration

- Add the provider to `ProviderName`.
- Add only necessary settings to `AppSettings`, using `SecretStr` for secrets.
- Validate conditional requirements without echoing values in errors.
- Add placeholder-only entries to `.env.example` and document them.

### 2. Provider response models and client

- Create strict Pydantic response models with nonnegative count validation and
  unknown-field rejection where compatible with the public contract.
- Implement `AnalyticsClient[ProviderRecord]` with an asynchronous
  `get_usage_analytics(reporting_date)` method.
- Follow the documented authentication scheme exactly.
- Implement every required pagination page, bounded timeouts, and safe mappings
  for authentication, authorization, rate limit, date availability, transport,
  malformed response, and server failures.
- Keep base URLs and paths out of telemetry and error responses.

### 3. Normalization

- Add a provider-owned `ProviderUsageExtension`.
- Map only honest common concepts into `CommonUsageActivity`.
- Use `None` when a common signal is unavailable and `0` only when the provider
  exposes the signal and reports no activity.
- Preserve other useful values in the provider extension without renaming them
  into misleading universal concepts.
- Do not create token, cost, productivity, or content fields the provider does
  not expose.

### 4. Aggregation

- Define an explicit provider organization summary extension.
- Aggregate only additive values with clear semantics.
- Reject empty input, mixed dates, duplicates, incompatible provider records,
  missing extensions, and unavailable required common values.
- Avoid summing per-user distinct counts and calling the result an organization
  distinct count.

### 5. Privacy review and safe models

- Decide field by field what may cross the privacy boundary.
- Add a provider-specific privacy-safe extension containing only approved
  fields.
- Remove email, raw identifiers, organization groups, and other direct or
  unnecessary identifiers.
- Use the shared provider-namespaced HMAC pseudonymizer.
- Add serialization tests proving unsafe fixtures are absent from every output
  boundary.

### 6. Telemetry

- Reuse generic organization metrics only for genuinely common values.
- Give provider-specific metrics a provider namespace and documented units.
- Keep the metric attribute allowlist unchanged unless a separate privacy and
  cardinality review justifies a change.
- Add one provider-specific structured event body built from the protected
  record, not the normalized raw-identity record.
- Use the shared collection span and safe lifecycle event schema.

### 7. Workflow and service wiring

- Add a typed collection workflow or refactor the existing explicit workflows
  only when that preserves type safety and provider semantics.
- Wire the provider into `GatewayService` readiness, client construction,
  pseudonymizer requirements, collection selection, preview union, and safe API
  response union.
- Keep `POST /collect` provider-selected and keep raw or pseudonymous user
  records out of its response.

### 8. Tests and documentation

At minimum, test:

- protocol conformance and strict response validation;
- request method, URL, date, pagination, headers, timeout, and all pages;
- safe authentication, authorization, rate-limit, transport, date, malformed
  response, and server errors;
- normalization of every common and provider-specific field;
- aggregation calculations and rejection cases;
- stable provider-namespaced pseudonymization;
- absence of raw identities and secrets in logs, metrics, traces, previews,
  errors, and API responses;
- exactly one usage event per protected record and one workflow trace;
- provider selection, readiness, mock-free network tests, and preview behavior;
- format, lint, strict mypy, full pytest, coverage, and installed import checks.

Update the README, architecture, privacy model, roadmap, project status, and
public-documentation links. State explicitly whether a real provider credential
or connection was tested.

## Review checklist

- [ ] Public analytics documentation supports every implemented field.
- [ ] Authentication is documented rather than assumed.
- [ ] All network tests are mocked and all fixture identities are fictional.
- [ ] Common mappings have provider-independent meaning.
- [ ] Provider-only values stay in provider-owned extensions and telemetry.
- [ ] Raw identity exists only before privacy processing.
- [ ] All errors and telemetry pass the privacy allowlists.
- [ ] No token, cost, content, productivity, or production-work claims are
      invented.
- [ ] The complete local quality suite passes.
- [ ] Documentation describes validation gaps honestly.
