# Architecture

## Purpose and boundaries

GenAI Usage Observability Gateway is a pre-alpha reference implementation for
collecting organization usage analytics without inspecting prompts, responses,
or personal content. It translates a provider-owned analytics surface into
privacy-conscious OpenTelemetry signals while retaining provider-specific
meaning.

The project observes adoption and activity signals. It is not an LLM request
proxy, prompt tracer, model-quality evaluator, cost calculator, productivity
system, or proof that production work was created.

## Collection data flow

```text
Provider Analytics API or synthetic provider
                    |
                    v
      AnalyticsClient protocol
                    |
                    v
 Strict provider response models
                    |
                    v
  NormalizedUsageRecord
  + provider-owned extension
                    |
                    v
 HMAC pseudonymization and explicit
 privacy-safe collection models
          /         |          \
         v          v           v
 organization   per-user      collection
 aggregation    safe records  metadata
         |          |           |
         v          v           v
      metrics    log events    one trace
          \         |          /
                    v
       console or OTLP/HTTP exporters
```

The FastAPI service selects one provider from validated settings. One request
to `POST /collect` creates one provider-specific workflow for one UTC reporting
date. The workflow retrieves every provider page, normalizes records, crosses
the privacy boundary, aggregates organization totals, emits telemetry, creates
the in-memory preview, and optionally persists it atomically.

## Component responsibilities

### Configuration and HTTP boundary

`config.py` validates environment selection, provider selection, secrets,
preview behavior, upstream pagination and timeouts, and OTLP configuration.
Pydantic hides configuration input in validation errors. `app.py` owns the
FastAPI lifespan, fixed route inventory, response models, and secret-safe error
mapping. Generated API documentation is disabled.

### Provider adapter boundary

`AnalyticsClient[ProviderRecordT]` is a covariant asynchronous protocol with a
provider property and `get_usage_analytics(reporting_date)`. An adapter owns:

1. authentication and request construction;
2. pagination, timeout, and upstream failure handling;
3. strict response validation;
4. mapping to the small common activity model;
5. typed provider-specific extensions; and
6. tests that mock the network boundary.

The mock adapter is a real participant in the same architecture, but its data
and telemetry remain labeled `mock`. The Anthropic adapter is the first
reference to a real public provider API. No other provider is implemented.

### Common model and provider extensions

The common record includes a reporting date, provider, raw boundary identity,
an explicit active-user value, and only portable counts for chat interactions,
developer sessions, and accepted or rejected tool actions. Optional counts
distinguish an unavailable signal from an available signal whose value is zero.

Product-specific fields remain in strict extension types. For example, Claude
Code commits and lines changed, Cowork actions, Design sessions, Office product
activity, Science activity, and web searches are not declared universal GenAI
concepts. This prevents schema convenience from changing data meaning.

### Privacy boundary

Raw provider identity is allowed only through provider ingestion,
normalization, and construction of the protected collection. The privacy module
replaces the raw provider identifier with the first 16 hexadecimal characters
of a provider-namespaced HMAC-SHA256 value. Email and organization groups are
not copied into privacy-safe types.

Downstream components accept only one of three safe shapes:

- identity-free organization summaries for metrics;
- pseudonymous user records for structured usage events and previews; or
- identity-free, low-cardinality collection metadata for traces and lifecycle
  events.

See [Privacy](privacy.md) for guarantees and limitations.

### Aggregation

Aggregation requires a nonempty, single-provider, single-date collection with
unique provider user identifiers. It computes identity-free common totals and
typed provider-specific additive totals. Unsupported values are not invented,
and ambiguous per-user distinct counts are not mislabeled as organization-wide
distinct counts.

### Telemetry

The FastAPI lifespan leases one shared OpenTelemetry Resource and trace, metric,
and log provider set. Initialization is reference-counted and idempotent;
shutdown force-flushes each provider.

Organization measurements use synchronous gauges because a recollection for
the same date should replace an absolute value instead of accumulating a retry.
Metric attributes are limited to reporting date, deployment environment,
telemetry source, and provider.

Each protected user produces one structured `genai_user_usage` log event. A
log event is appropriate because the body is a discrete, pseudonymous record
whose rich provider extension must not become high-cardinality metric labels.

One `genai.usage.collection` trace covers the complete workflow. Ordered
lifecycle log events describe safe operational checkpoints and share the
active trace context. Exceptions are recorded with fixed privacy-safe type,
message, and stack-trace values before the original exception is re-raised.

`genai.*`, `anthropic.*`, and `telemetry.source` names are custom project
telemetry, not official OpenTelemetry semantic conventions. Official resource
attributes are used only where their documented meaning applies.

### Preview

The preview is created after privacy processing. When persistence is enabled,
the writer creates a temporary sibling, flushes and synchronizes the complete
UTF-8 JSON document, and atomically replaces the destination. Preview paths do
not enter telemetry. Persistence defaults off outside development.

## Runtime and deployment model

The service has no database, frontend, scheduler, durable queue, or bundled
collector. Apart from an optional development preview it is stateless. The
container uses the locked production dependency set and a numeric nonroot user.
OTLP/HTTP is configured with an operator-selected base URL; no destination is
hardcoded.

That small runtime does not make the project production-ready. Authentication,
authorization, tenant isolation, scheduling, retry policy, capacity testing,
operational retention controls, and real provider and collector validation are
outside the current implementation.

## Extension seams

The central protocol and small normalized model are provider-neutral, but the
current version intentionally uses explicit typed branches for the two
supported providers. Adding another provider therefore requires deliberate
changes across provider models, normalization, privacy review, aggregation,
telemetry, workflow orchestration, configuration, service selection, and tests.
This is safer than dynamically exporting fields that have not received a
privacy and semantics review. See [Adding a provider](adding_a_provider.md).
