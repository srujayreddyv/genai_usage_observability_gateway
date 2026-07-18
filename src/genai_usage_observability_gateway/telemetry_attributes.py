"""Custom telemetry attributes owned by this project."""

from opentelemetry.semconv.attributes.deployment_attributes import (
    DEPLOYMENT_ENVIRONMENT_NAME as OTEL_DEPLOYMENT_ENVIRONMENT_NAME,
)

# Official OpenTelemetry semantic-convention attribute.
DEPLOYMENT_ENVIRONMENT_NAME = OTEL_DEPLOYMENT_ENVIRONMENT_NAME

# These names are custom project telemetry, not OpenTelemetry semantic conventions.
TELEMETRY_SOURCE = "telemetry.source"
TELEMETRY_SOURCE_VALUE = "provider_analytics_api"
REPORTING_DATE_ATTRIBUTE = "genai.usage.reporting_date"
PROVIDER_ATTRIBUTE = "genai.usage.provider.name"

ORGANIZATION_METRIC_ATTRIBUTE_KEYS = frozenset(
    {
        REPORTING_DATE_ATTRIBUTE,
        DEPLOYMENT_ENVIRONMENT_NAME,
        TELEMETRY_SOURCE,
        PROVIDER_ATTRIBUTE,
    }
)
