# axor-telemetry

Anonymous telemetry pipeline for [axor-core](https://github.com/Bucha11/axor-core).

**Opt-in only.** Nothing is sent without explicit user consent.

## What gets sent (when consent is given)

- `signal_chosen` (e.g. `focused_generative`)
- `classifier_used`, `confidence`
- MinHash fingerprint of the raw input (128 ints, non-reversible)
- `tokens_spent`, `policy_adjusted`
- `axor_version`

**Not sent:** raw task text, file contents, user or session identifiers,
tool arguments, secrets.

## Install

```bash
pip install axor-telemetry[core]
```

## CLI

```bash
python -m axor_telemetry consent   # interactive opt-in
python -m axor_telemetry status    # show current config
python -m axor_telemetry preview   # show the last queued record
python -m axor_telemetry on        # non-interactive: set local mode
python -m axor_telemetry off       # disable
```

Config lives at `~/.axor/config.toml` under `[telemetry]`.

## Modes

| mode     | behavior |
|----------|----------|
| `off`    | Default. Pipeline does nothing. |
| `local`  | Writes to `~/.axor/telemetry_queue.jsonl`. Never sent anywhere. |
| `remote` | Writes local queue + ships batches to `telemetry.useaxor.net/v1/records`. Retry-on-next-start if offline. |

## Programmatic usage

```python
from axor_telemetry import TelemetryPipeline, MinHashEmbedder, FileTelemetrySink

pipeline = TelemetryPipeline(
    embedder=MinHashEmbedder(),
    sink=FileTelemetrySink(queue_path="~/.axor/telemetry_queue.jsonl"),
)
```

Inject `pipeline` into `GovernedSession` (see axor-cli integration).
