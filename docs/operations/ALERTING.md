# Annie Alerting Configuration

This document provides alerting configuration for Annie using Grafana Cloud's free tier.

## Prerequisites

1. **Grafana Cloud Account**: Sign up at https://grafana.com/products/cloud/ (free tier)
2. **Cloud Logging Enabled**: Complete Epic 17 setup (`ENV=prod` with Loki logging)
3. **Logs Flowing**: Verify logs appear in Grafana Cloud Explore

## Grafana Cloud Free Tier Limits

| Resource | Free Tier Limit | Annie Usage |
|----------|-----------------|-------------|
| Logs | 50 GB/month | ~250 MB/month |
| Log Retention | 14 days | Sufficient |
| Alert Rules | 50 | 5-10 needed |
| Notification Channels | Unlimited | Email (free) |

## Recommended Alert Rules

### Critical Alerts

These alerts require immediate attention.

| Alert Name | LogQL Query | Condition | Severity |
|------------|-------------|-----------|----------|
| Service Error Spike | `sum(count_over_time({project="annie"} \|= "ERROR" [5m]))` | > 10 errors/5min | Critical |
| Memory Storage Failed | `{service="backend"} \|= "MemoryClient" \|= "failed"` | Any occurrence | Critical |
| Redis Connection Lost | `{project="annie"} \|= "redis" \|= "connection" \|= "error"` | Any occurrence | Critical |
| Container Restart | `{project="annie"} \|= "container" \|= "restart"` | Any occurrence | Critical |
| LLM API Failure | `{service="backend"} \|= "LLM" \|= "error"` | > 5/hour | Critical |

### Warning Alerts

These alerts indicate potential issues that should be monitored.

| Alert Name | LogQL Query | Condition | Severity |
|------------|-------------|-----------|----------|
| LLM Latency High | `{service="backend"} \| json \| duration_ms > 5000` | > 5/hour | Warning |
| Tool Call Failures | `{service="mcp-server"} \|= "error" \|= "tool"` | > 3/hour | Warning |
| Rate Limit Warnings | `{project="annie"} \|= "rate_limit"` | Any occurrence | Warning |
| Proactive Worker Failure | `{service="backend"} \|= "proactive" \|= "error"` | > 3/hour | Warning |

### Cost Monitoring Alerts

Track usage that may impact costs.

| Alert Name | LogQL Query | Condition | Severity |
|------------|-------------|-----------|----------|
| Grok Live Search High Usage | `{service="backend"} \| json \| event="live_search_used"` | > 100/day | Info |
| Gemini API High Usage | `{service="backend"} \|= "gemini" \|= "completion"` | > 500/day | Info |

## Setting Up Alerts in Grafana Cloud

### Step 1: Access Alert Rules

1. Log in to Grafana Cloud: https://grafana.com
2. Navigate to: **Alerting** → **Alert Rules**
3. Click **+ New Alert Rule**

### Step 2: Configure Alert Rule

1. **Rule name**: e.g., "Annie Service Error Spike"
2. **Define query and alert condition**:
   - Data source: `grafanacloud-<your-stack>-logs`
   - Query: Paste LogQL from tables above
   - Condition: Set threshold (e.g., "Is above 10")
3. **Set evaluation behavior**:
   - Folder: Create "Annie" folder
   - Evaluation group: "annie-critical" or "annie-warning"
   - Evaluation interval: 1m (recommended)
   - Pending period: 0s for critical, 5m for warning
4. **Configure labels and notifications**:
   - Severity label: `critical` or `warning`
   - Summary annotation: Describe the alert
5. **Save**

### Step 3: Configure Notification Channel

1. Navigate to: **Alerting** → **Contact points**
2. Click **+ Add contact point**
3. For email (free):
   - Name: "Annie Alerts Email"
   - Type: Email
   - Addresses: your-email@example.com
4. **Save**

### Step 4: Link Contact Point to Alerts

1. Navigate to: **Alerting** → **Notification policies**
2. Edit the default policy or create specific policies
3. Set contact point to "Annie Alerts Email"
4. **Save**

## Example Alert Rule YAML

Export this YAML to automate alert creation:

```yaml
apiVersion: 1
groups:
  - name: annie-critical
    folder: Annie
    interval: 1m
    rules:
      - title: Service Error Spike
        condition: C
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: grafanacloud-logs
            model:
              expr: sum(count_over_time({project="annie"} |= "ERROR" [5m]))
              queryType: range
          - refId: C
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: __expr__
            model:
              conditions:
                - evaluator:
                    params: [10]
                    type: gt
              type: threshold
        for: 0s
        labels:
          severity: critical
        annotations:
          summary: High error rate detected in Annie services

      - title: Memory Storage Failed
        condition: C
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: grafanacloud-logs
            model:
              expr: count_over_time({service="backend"} |= "MemoryClient" |= "failed" [5m])
              queryType: range
          - refId: C
            datasourceUid: __expr__
            model:
              conditions:
                - evaluator:
                    params: [0]
                    type: gt
              type: threshold
        for: 0s
        labels:
          severity: critical
        annotations:
          summary: Memory storage to agentic-memories failed

      - title: Redis Connection Lost
        condition: C
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: grafanacloud-logs
            model:
              expr: count_over_time({project="annie"} |= "redis" |= "connection" |= "error" [5m])
              queryType: range
          - refId: C
            datasourceUid: __expr__
            model:
              conditions:
                - evaluator:
                    params: [0]
                    type: gt
              type: threshold
        for: 0s
        labels:
          severity: critical
        annotations:
          summary: Redis connection error detected

  - name: annie-warning
    folder: Annie
    interval: 1m
    rules:
      - title: LLM Latency High
        condition: C
        data:
          - refId: A
            relativeTimeRange:
              from: 3600
              to: 0
            datasourceUid: grafanacloud-logs
            model:
              expr: count_over_time({service="backend"} | json | duration_ms > 5000 [1h])
              queryType: range
          - refId: C
            datasourceUid: __expr__
            model:
              conditions:
                - evaluator:
                    params: [5]
                    type: gt
              type: threshold
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: LLM responses taking longer than 5 seconds
```

## Useful LogQL Queries

### Error Investigation

```logql
# All errors in last hour
{project="annie"} |= "ERROR" | json

# Errors by service
sum by (service) (count_over_time({project="annie"} |= "ERROR" [1h]))

# Error details with stack traces
{project="annie"} |= "error" | json | line_format "{{.timestamp}} [{{.service}}] {{.message}}"
```

### Performance Monitoring

```logql
# Slow LLM responses (>5s)
{service="backend"} | json | duration_ms > 5000

# Average response time by service
avg_over_time({service="backend"} | json | unwrap duration_ms [1h]) by (service)

# Tool call latency
{service="mcp-server"} | json | line_format "{{.tool_name}}: {{.duration_ms}}ms"
```

### Cost Tracking

```logql
# Grok Live Search usage
{service="backend"} | json | event="live_search_used"

# Token usage by model
{service="backend"} | json | event="llm_completion" | line_format "{{.model}}: {{.tokens_used}}"
```

### Service Health

```logql
# Service startup/shutdown events
{project="annie"} |= "Starting" or |= "Stopped" or |= "shutdown"

# Memory operations
{service="backend"} |= "memory" | json

# Profile cache operations
{service="backend"} |= "profile" | json
```

## Troubleshooting

### Logs Not Appearing in Grafana

1. **Check Loki plugin is installed:**
   ```bash
   docker plugin ls | grep loki
   ```

2. **Verify LOKI_URL is set:**
   ```bash
   grep LOKI_URL .env
   ```

3. **Check container logs locally:**
   ```bash
   make logs ENV=prod
   ```

4. **Verify network connectivity:**
   ```bash
   curl -v "https://logs-prod-us-central1.grafana.net/ready"
   ```

### Alert Not Firing

1. Check LogQL query returns results in Explore
2. Verify evaluation interval and pending period
3. Check notification policy routes correctly
4. Verify contact point is configured

### High Log Volume

If approaching 50GB/month limit:

1. Filter high-volume DEBUG logs in LogQL
2. Reduce log retention requirements
3. Consider log sampling for non-critical services

## Future Enhancements

- **Telegram Notifications**: Add webhook contact point to send alerts to Telegram
- **PagerDuty Integration**: For on-call escalation
- **Grafana Dashboards**: Pre-built dashboards for Annie operations
- **Prometheus Metrics**: Add container resource monitoring
