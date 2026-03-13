# Cloud Logging Baseline and Alerts

This guide defines a practical baseline for the new request correlation and observability logs.

Provider-agnostic baseline (recommended source of truth): `OBSERVABILITY_BASELINE.md`

## Scope

The filters below target these log patterns already emitted by the app:

- `http.request ... request_id=...`
- `security.guard denied ... request_id=...`
- `security.csrf denied ... request_id=...`
- `auth.login failed ... request_id=...`
- `attendance.import ... request_id=...`
- `attendance.request.process ... request_id=...`
- `attendance.approve_all ... request_id=...`
- `ot.request|ot.process|ot.approval.view ... request_id=...`
- `payroll.calculate|payroll.process|payroll.recalculate ... request_id=...`

## Baseline Queries

Replace `YOUR_SERVICE_NAME` with your Cloud Run service (or remove that line for broader search).

### 1) Request trace by request_id

```text
resource.type="cloud_run_revision"
resource.labels.service_name="YOUR_SERVICE_NAME"
textPayload:"request_id=REQ_ID"
```

### 2) Error and slow request summary

```text
resource.type="cloud_run_revision"
resource.labels.service_name="YOUR_SERVICE_NAME"
textPayload:"http.request"
(
  textPayload:"status=4" OR
  textPayload:"status=5" OR
  textPayload:"duration_ms="
)
```

### 3) Security denials and auth failures

```text
resource.type="cloud_run_revision"
resource.labels.service_name="YOUR_SERVICE_NAME"
(
  textPayload:"security.guard denied" OR
  textPayload:"security.csrf denied" OR
  textPayload:"auth.login failed"
)
```

### 4) Attendance and import flow health

```text
resource.type="cloud_run_revision"
resource.labels.service_name="YOUR_SERVICE_NAME"
(
  textPayload:"attendance.import" OR
  textPayload:"attendance.request.process" OR
  textPayload:"attendance.approve_all"
)
```

### 5) OT approval flow health

```text
resource.type="cloud_run_revision"
resource.labels.service_name="YOUR_SERVICE_NAME"
(
  textPayload:"ot.request" OR
  textPayload:"ot.process" OR
  textPayload:"ot.approval.view"
)
```

### 6) Payroll flow health

```text
resource.type="cloud_run_revision"
resource.labels.service_name="YOUR_SERVICE_NAME"
(
  textPayload:"payroll.calculate" OR
  textPayload:"payroll.process" OR
  textPayload:"payroll.recalculate"
)
```

## Baseline Alert Policies

Start with conservative thresholds to reduce false positives. Tune after 7-14 days.

### Alert A: Elevated 5xx responses

- Filter:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="YOUR_SERVICE_NAME"
textPayload:"http.request"
textPayload:"status=5"
```

- Condition: count >= 5 in 5 minutes
- Severity: Critical
- Notification: on-call channel (Pager/Phone + Slack)

### Alert B: Security denial spike

- Filter:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="YOUR_SERVICE_NAME"
(
  textPayload:"security.guard denied" OR
  textPayload:"security.csrf denied"
)
```

- Condition: count >= 10 in 10 minutes
- Severity: Warning
- Notification: Slack/Email

### Alert C: Payroll operation failures

- Filter:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="YOUR_SERVICE_NAME"
(
  textPayload:"payroll.process failed" OR
  textPayload:"payroll.process error" OR
  textPayload:"payroll.recalculate failed"
)
```

- Condition: count >= 1 in 10 minutes
- Severity: Critical
- Notification: on-call + finance owner

### Alert D: Attendance import failures

- Filter:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="YOUR_SERVICE_NAME"
textPayload:"attendance.import failed"
```

- Condition: count >= 1 in 15 minutes
- Severity: Warning
- Notification: HR ops channel

## Runbook Notes

- Always pivot with `request_id` first for incident triage.
- Correlate request summary (`http.request`) with domain events (`payroll.*`, `attendance.*`, `ot.*`).
- If Alert B fires but no 4xx/5xx spike, check bot traffic and auth/session expiration patterns before escalation.

## Suggested Weekly Tuning

- Review top 10 frequent warnings.
- Adjust thresholds so expected noise does not page on-call.
- Promote any repeated business-impacting warning to a dedicated alert.
