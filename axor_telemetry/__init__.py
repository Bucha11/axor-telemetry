"""
axor-telemetry
──────────────
Anonymous telemetry pipeline for axor-core. Opt-in only.

Public surface:
- MinHashEmbedder    — pure-Python 128-dim char-3 MinHash fingerprint
- FileTelemetrySink  — JSONL queue at ~/.axor/telemetry_queue.jsonl
- HTTPTelemetrySink  — POST batches with retry-on-next-start
- TelemetryPipeline  — trace → anonymize → dispatch
- TelemetryConfig    — resolved mode + endpoint from env + config.toml
"""

from axor_telemetry.embedder import MinHashEmbedder
from axor_telemetry.sinks.file_sink import FileTelemetrySink
from axor_telemetry.sinks.http_sink import HTTPTelemetrySink
from axor_telemetry.pipeline import TelemetryPipeline
from axor_telemetry.config import TelemetryConfig, TelemetryMode

__version__ = "0.1.0"

__all__ = [
    "MinHashEmbedder",
    "FileTelemetrySink",
    "HTTPTelemetrySink",
    "TelemetryPipeline",
    "TelemetryConfig",
    "TelemetryMode",
    "__version__",
]
