# Changelog

## 0.2.0 — 2026-04-29

### Added
- `HTTPTelemetrySink(auth_token=…)` — sends `X-Axor-Token` header on each
  POST so a server with `INGEST_SHARED_SECRET` configured will accept
  the request.

### Changed
- File and HTTP sinks no longer wrap their I/O in `asyncio.to_thread`.
  Some restricted runtimes (e.g., agentic sandboxes that pre-create
  thread pools) hung on executor startup; the writes are short-lived
  and serialized on the sink's own lock anyway, so the `to_thread`
  hop bought correctness against a problem we never had. The
  "queue write commits before send returns" guarantee is preserved.

### Constraints
- Optional extras `[core]` and `[dev]` capped:
  `axor-core>=0.3.0,<0.5` (was `>=0.3.0`).

## 0.1.0 — 2026-04-24

Initial release.

### Added
- Opt-in anonymous telemetry pipeline. Default `mode=off`; records ship only
  after explicit `consent` / `on --remote`.
- `MinHashEmbedder` — char-3-gram → 128-dim integer fingerprint
  (non-reversible).
- `TelemetryPipeline` orchestrating classify → fingerprint → sink.
- `FileTelemetrySink` — local JSONL queue.
- `HTTPTelemetrySink` — POSTs to the telemetry server with retry-on-next-start.
- Wire-format converter (`serialize.py`) that excludes raw text, paths, and
  secrets — only signal labels, classifier metadata, token counts, and the
  fingerprint go on the wire.
- Config at `~/.axor/telemetry.toml` and the `axor-telemetry` CLI.

### Notes
- Not imported by axor-core directly; wired by adapter packages via
  duck-typed pipeline interfaces.
