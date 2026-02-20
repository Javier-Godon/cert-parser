# Scheduler

## Overview

cert-parser runs as a long-lived process that executes the pipeline at configurable intervals. The scheduler is built on APScheduler's `BlockingScheduler` — the simplest approach for a single-purpose application.

## Architecture

```
main.py (composition root)
    │
    ├── Creates adapters
    ├── Wires pipeline via partial()
    │
    └── create_scheduler(pipeline_fn, interval_hours, run_on_startup)
            │
            ├── Creates BlockingScheduler
            ├── Adds job with IntervalTrigger
            ├── Optionally runs pipeline immediately (run_on_startup=True)
            ├── Registers SIGINT/SIGTERM handlers
            └── Returns scheduler (main.py calls .start())
```

## create_scheduler()

```python
def create_scheduler(
    pipeline_fn: Callable[[], Result[int]],
    interval_hours: int = 6,
    run_on_startup: bool = True,
) -> BlockingScheduler:
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pipeline_fn` | `Callable[[], Result[int]]` | — | Zero-argument callable (the fully-wired pipeline) |
| `interval_hours` | `int` | `6` | Hours between scheduled executions |
| `run_on_startup` | `bool` | `True` | Execute pipeline once immediately on startup |

### How It Works

1. Creates a `BlockingScheduler` instance
2. Creates a `LoggingExecutionContext` for structured observability
3. Defines an inner `_job()` function that:
   - Wraps the pipeline call in the execution context
   - Logs success (`scheduler.job_completed`, `rows_stored=N`)
   - Logs failure (`scheduler.job_failed`, `failure=...`)
4. Adds the job with `IntervalTrigger(hours=interval_hours)`
5. If `run_on_startup=True`, calls `_job()` immediately
6. Registers signal handlers for graceful shutdown
7. Returns the scheduler (caller must call `.start()`)

## Job Execution

Each job invocation:

```python
def _job() -> None:
    result = ctx.execute(pipeline_fn)      # LoggingExecutionContext wraps
    if result.is_success():
        log.info("scheduler.job_completed", rows_stored=result.value())
    else:
        log.error("scheduler.job_failed", failure=str(result.error()))
```

The `LoggingExecutionContext` from the railway framework adds:
- Operation name logging (`MasterListSync`)
- Execution timing (start, duration)
- Automatic success/failure logging

**Key**: Job failures do NOT crash the scheduler. The pipeline returns `Result.failure`, which is logged. The scheduler continues and will retry on the next interval.

## Signal Handling

```python
def _register_shutdown_signals(scheduler: BlockingScheduler) -> None:
    def _shutdown(signum: int, frame: object) -> None:
        sig_name = signal.Signals(signum).name
        log.info("scheduler.shutdown_requested", signal=sig_name)
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)   # Ctrl+C
    signal.signal(signal.SIGTERM, _shutdown)  # Docker stop, kill
```

### Signals Handled

| Signal | Source | Behavior |
|--------|--------|----------|
| `SIGINT` | Ctrl+C, keyboard interrupt | Log + shutdown + exit(0) |
| `SIGTERM` | `docker stop`, `kill pid` | Log + shutdown + exit(0) |

### Why `wait=False`?

`scheduler.shutdown(wait=False)` stops the scheduler immediately without waiting for running jobs to complete. Since the pipeline can take minutes (HTTP download + DB transaction), waiting could cause deployment delays. The transactional replace pattern ensures data consistency even if interrupted mid-write.

## Startup Behavior

When `run_on_startup=True` (the default):

```
Application starts
    │
    ├── Configuration loaded
    ├── Adapters created
    ├── Pipeline wired
    │
    ├── scheduler created
    │   ├── Pipeline runs IMMEDIATELY ← startup run
    │   ├── logs success or failure
    │   └── Signal handlers registered
    │
    └── scheduler.start()  ← enters blocking loop
            │
            ├── wait interval_hours...
            ├── Pipeline runs (scheduled)
            ├── wait interval_hours...
            ├── Pipeline runs (scheduled)
            └── ... (until SIGINT/SIGTERM)
```

When `run_on_startup=False`:

```
Application starts
    │
    └── scheduler.start()  ← enters blocking loop immediately
            │
            ├── wait interval_hours...
            ├── Pipeline runs (first execution)
            └── ...
```

## Why BlockingScheduler?

Other options considered:

| Scheduler | Why Not |
|-----------|---------|
| `BackgroundScheduler` | Needs a separate main thread to keep the process alive. Adds complexity for no benefit. |
| `AsyncIOScheduler` | cert-parser is fully synchronous. Async would add unnecessary complexity. |
| `cron` (system) | External dependency. Harder to deploy in Docker. No structured logging. |
| `celery` | Massive overkill — requires a message broker. This app has one job. |

`BlockingScheduler` is the simplest: it blocks the main thread and manages timing. Perfect for a single-purpose application.

## Docker Deployment

The scheduler is designed for Docker:

```dockerfile
CMD ["python", "-m", "cert_parser.main"]
```

Docker lifecycle:
- `docker run` → `main()` →  pipeline runs (startup) → scheduler loop
- `docker stop` → SIGTERM → graceful shutdown → exit(0)
- `docker restart` → new startup run → scheduler loop

## Testing the Scheduler

### What's Testable

- `create_scheduler()` — verify it returns a configured scheduler
- `_job()` behavior — verify logging on success/failure
- Job registration — verify trigger interval
- Startup run behavior — verify pipeline is called immediately

### What's Not Testable (by design)

- `_register_shutdown_signals()` — the signal handler calls `sys.exit(0)`, which can't be safely tested in pytest
- `scheduler.start()` — blocks forever (the blocking loop)

Coverage for `scheduler.py`: **88%** — the 12% gap is the signal handler body and the blocking loop, both untestable by design.

## Configuration Reference

| Setting | Env Variable | Default | Description |
|---------|-------------|---------|-------------|
| `interval_hours` | `SCHEDULER_INTERVAL_HOURS` | `6` | Hours between runs |
| `run_on_startup` | `RUN_ON_STARTUP` | `true` | Execute on startup |
