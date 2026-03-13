# Observability Baseline (Provider-Agnostic)

This document defines a cloud-neutral baseline for request tracing, error detection, and operational alerting.

Use this as the source of truth when moving between providers (GCP, AWS, Azure, self-hosted).

## Goals

- Keep incident triage fast using a single `request_id` across all logs.
- Detect business-critical failures early with low-noise alerts.
- Preserve stable event names so query logic is portable.

## Required Log Fields

Every request-scoped log should include at least:

- `request_id`
- `event`
- `severity`
- `timestamp`
- `path` (if HTTP related)
- `method` (if HTTP related)
- `status` (if HTTP related)

## Canonical Event Families

Use these event names as portable search anchors:

- `http.request`
- `security.guard denied`
- `security.csrf denied`
- `auth.login failed`
- `attendance.import`
- `attendance.request.process`
- `attendance.approve_all`
- `ot.request`
- `ot.process`
- `ot.approval.view`
- `payroll.calculate`
- `payroll.process`
- `payroll.recalculate`

## Generic Query Templates

Adjust syntax for your logging backend, but keep intent unchanged.

### 1) Trace one request end-to-end

```text
WHERE log CONTAINS "request_id=<REQ_ID>"
ORDER BY timestamp ASC
```

### 2) Slow or failing HTTP requests

```text
WHERE event = "http.request"
AND (
  status >= 400
  OR duration_ms >= <SLOW_REQUEST_THRESHOLD_MS>
)
```

### 3) Security denials and auth failures

```text
WHERE event IN (
  "security.guard denied",
  "security.csrf denied",
  "auth.login failed"
)
```

### 4) Payroll failure signals only

```text
WHERE log CONTAINS "payroll.recalculate failed"
   OR log CONTAINS "payroll.process failed"
   OR log CONTAINS "payroll.process error"
```

### 5) Attendance import failures only

```text
WHERE log CONTAINS "attendance.import failed"
```

## Baseline Alert Intents

Tune thresholds after 7-14 days of production traffic.

### Alert A: 5xx spike

- Signal: failing `http.request` with status 5xx
- Initial threshold: count >= 5 in 5 minutes
- Severity: Critical

### Alert B: security denial spike

- Signal: `security.guard denied` or `security.csrf denied`
- Initial threshold: count >= 10 in 10 minutes
- Severity: Warning

### Alert C: payroll failures

- Signal: `payroll.recalculate failed`, `payroll.process failed`, `payroll.process error`
- Initial threshold: count >= 1 in 10 minutes
- Severity: Critical

### Alert D: attendance import failures

- Signal: `attendance.import failed`
- Initial threshold: count >= 1 in 15 minutes
- Severity: Warning

## Portability Checklist

When changing cloud/VPS provider:

1. Preserve app log format and event names.
2. Recreate these 4 baseline alerts in the new monitoring stack.
3. Run smoke incidents:
   - one synthetic 401/403
   - one synthetic payroll failure event
   - one synthetic attendance import failure event
4. Confirm notification channels receive each test alert.

## Provider-Specific Mapping

- Google Cloud: see `CLOUD_LOGGING_BASELINE.md`.
- Other providers: implement equivalent filters using the same event anchors and alert intents above.
