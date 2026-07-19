# Privacy model

## Philosophy

The gateway starts from data minimization: collect only fields exposed by a
documented analytics API and needed for usage observability, then remove direct
identity before telemetry export. It never retrieves or analyzes prompts,
responses, attachments, or personal content.

Usage observability is not employee surveillance or a productivity score.
Activity may reflect many contexts and cannot determine whether work was
personal or professional, valuable or wasteful, human- or AI-authored, or
deployed to production. Operators must not reinterpret these signals as proof
of individual performance.

## Data classification and lifecycle

### Ingestion and normalization boundary

Provider user identifiers and email addresses may exist transiently because a
provider response includes them. The stable provider user identifier is used
for duplicate detection and pseudonymization; email is not exported. Provider
grouping fields may be validated at ingestion, but are intentionally omitted
from normalized provider extensions.

Raw identity must not leave this boundary through logs, metrics, traces,
previews, errors, or API responses.

### Privacy transformation

The gateway computes:

```text
HMAC-SHA256(PSEUDONYMIZATION_KEY, "<provider>:<provider_user_id>")[:16]
```

The provider namespace prevents the same raw identifier at two providers from
automatically producing the same pseudonym. The secret is held as a Pydantic
`SecretStr` and is not serialized. Outside development and test, a configured
key is required. Local mock mode may use a fixed application-owned synthetic
namespace because every mock identity is fictional; real-provider workflows
never use that fallback.

### Export boundary

Only explicit strict models cross the boundary:

- organization summaries contain no individual or group fields;
- usage events and previews contain a 16-character pseudonym instead of raw
  identity;
- traces and lifecycle events contain only provider, bounded client type,
  reporting date, record count, collection status, and safe duration values;
- metric dimensions contain only reporting date, deployment environment,
  telemetry source, and provider.

Unknown fields are rejected. Error handlers return stable safe messages instead
of copying exception details, upstream bodies, request values, credentials,
URLs, or local paths.

## Prompts and responses

Prompt and response inspection is both unnecessary for the project's goal and
a substantially higher-risk data practice. Adoption questions can be explored
using documented counts and activity categories. The gateway therefore has no
prompt schema, response schema, content capture, content redaction pipeline, or
runtime request proxy. A future contribution that requires content inspection
would be a different product boundary, not a routine provider adapter.

## Guarantees enforced by the implementation

- HMAC-SHA256 pseudonyms are provider-namespaced and validated as exactly 16
  lowercase hexadecimal characters.
- Privacy-safe models have no email, raw identifier, or group fields.
- Organization metrics use an exact low-cardinality attribute allowlist.
- Usage and lifecycle event bodies are strict and reject extra fields.
- Trace attributes are bounded, and recorded exception details are replaced
  with fixed safe values.
- Preview generation accepts post-privacy collections and writes atomically.
- Tests serialize actual telemetry and preview outputs and search for raw
  synthetic identities, groups, paths, endpoints, secrets, and headers.

These are application-level controls, not a claim of formal anonymity,
regulatory compliance, or complete protection against every inference.

## Residual risks

Pseudonymization is not anonymization. With a stable key, the same provider user
is linkable across reporting dates. Activity patterns, rare combinations, or
external knowledge could support re-identification. Truncating the HMAC also
creates a nonzero collision risk, and this version rejects collisions observed
inside a collection rather than providing a migration strategy.

Organization totals can still be sensitive when an organization or reporting
cohort is very small. The gateway does not implement minimum cohort thresholds,
differential privacy, field-level consent, regional policy enforcement,
retention deletion, access control, or HMAC key rotation. It also cannot govern
copies retained by an external collector or backend.

## Operator responsibilities

Before nonlocal use, an operator should:

1. establish a lawful and transparent purpose for the analytics;
2. confirm provider terms and applicable privacy, labor, and records policies;
3. provision provider, HMAC, and OTLP credentials through a secret manager;
4. use HTTPS, outbound restrictions, and an authenticated collector;
5. restrict access to events, previews, traces, and dashboards;
6. define retention, deletion, incident response, and key-rotation procedures;
7. review small-cohort and re-identification risks;
8. disable development previews unless explicitly needed; and
9. prevent activity telemetry from becoming an individual productivity score.

Every new provider field requires a fresh review of necessity, meaning,
cardinality, sensitivity, aggregation behavior, and allowed destination before
it is added to a privacy-safe extension.

## Testing a privacy change

A privacy-related change should include negative tests that attempt to insert
raw identity, groups, secrets, paths, endpoints, and unknown fields. Run the
complete quality suite documented in the README, inspect serialized output, and
review the full Git diff before committing. Mock upstream responses and use
fictional `.example.com` or `.example.test` data only.
