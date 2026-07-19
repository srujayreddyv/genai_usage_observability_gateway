# Roadmap

This roadmap describes possible directions, not commitments. The project is
pre-alpha reference software with no claim of production readiness, customer
use, enterprise deployment, or measured performance.

## Current validated scope

Version 0.1 currently includes:

- a strict synthetic mock provider with exactly five fictional users;
- a public-documentation-based Anthropic Claude Enterprise User Activity API
  adapter tested only through mocked HTTP;
- common and provider-specific normalization and organization aggregation;
- provider-namespaced HMAC-SHA256 pseudonymization;
- privacy-safe organization metrics, per-user structured events, lifecycle
  events, one trace per collection, and atomic development previews;
- console telemetry and configurable OTLP/HTTP exporters;
- FastAPI health, readiness, collection, and preview routes;
- a locked nonroot container definition and GitHub Actions quality workflow;
- comprehensive tests with a configured coverage floor.

No real Anthropic credential, live provider connection, real OTLP collector,
backend dashboard, or performance workload has been validated.

## Near-term hardening candidates

- Repeat clean-checkout, service, synthetic-output, telemetry-count, API,
  security, and repository validation for every release candidate.
- Exercise the container build on a supported Docker or Podman host and confirm
  the pushed GitHub Actions result.
- Add documentation checks for internal links, shell examples, and stale public
  API references.
- Define explicit release notes, compatibility policy, contribution guidance,
  and security reporting instructions before a public release.

## Operational research candidates

These would require design, privacy review, and tests before implementation:

- externally scheduled collection with bounded retries and idempotency;
- authentication and authorization for the HTTP surface;
- minimum cohort thresholds and stronger controls for small populations;
- pseudonymization key rotation and continuity strategy;
- configurable retention and deletion behavior for local artifacts;
- collector/backend integration examples using only public, local development
  infrastructure;
- capacity, latency, failure-mode, and exporter backpressure measurements with
  published reproducible methodology.

## Provider research candidates

OpenAI, Azure OpenAI, Google Gemini, GitHub Copilot, internal LLM gateways, and
other products may be evaluated only where suitable public organization
analytics documentation exists. Inclusion here does not mean that support is
planned or that these providers expose equivalent fields.

Each adapter must retain provider-specific meaning and pass the extension and
privacy process in [Adding a provider](adding_a_provider.md). Provider analytics
APIs may omit tokens, costs, content, or desired activity categories. Missing
data must remain unavailable rather than be inferred.

## Explicit non-goals

- prompt or response inspection;
- runtime LLM request tracing, evaluation, guardrails, or model routing;
- employee productivity measurement or individual performance scoring;
- proving that usage created production code or business value;
- inventing token consumption or cost estimates;
- a bundled observability backend, database, or frontend;
- automatic ingestion of arbitrary provider fields without schema and privacy
  review.

## Production-readiness questions

Before production use could be considered, a future version would need an
explicit threat model, deployment and upgrade strategy, access control,
multi-tenant isolation decision, scheduler and concurrency policy, retry and
idempotency design, secrets and key-rotation procedures, retention controls,
operational SLOs, load and failure testing, dependency and image scanning,
release provenance, and live integration validation. None of those outcomes is
claimed by the current project.
