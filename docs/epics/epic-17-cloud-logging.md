# Epic: Cloud Logging Integration

> **Epic ID**: 17
> **Status**: Draft
> **Priority**: Medium
> **Estimated Effort**: 2-3 days
> **Dependencies**: Grafana Cloud Account (free tier), Docker with Loki plugin

---

## 1. Overview

### 1.1 Problem Statement

Annie currently lacks remote log visibility for production deployments:

- **No Remote Access**: Logs only viewable via SSH or `docker compose logs`
- **No Persistence**: Container restarts lose log history
- **No Alerting**: No proactive notification when errors occur
- **Blind Debugging**: Issues reported by users cannot be investigated without server access

This limits operational visibility and increases mean-time-to-resolution (MTTR) for production issues.

### 1.2 Solution

Implement environment-aware cloud logging using Grafana Cloud (free tier) with Loki:

1. **Production Logging**: Route container logs to Grafana Loki via Docker logging driver
2. **Environment Detection**: Single commands (`make start`, `make stop`) work across environments
3. **Proactive Alerting**: Configure alerts for critical errors, service failures, and cost thresholds
4. **Zero Code Changes**: All configuration via Docker Compose and environment variables

### 1.3 Success Criteria

| Metric | Target |
|--------|--------|
| Log delivery latency | <5s from container to Grafana |
| Dev experience unchanged | `make start` works identically |
| Prod startup safety | Fails fast if Loki plugin missing |
| Alert delivery | <1 min from error to notification |
| Free tier compliance | <50GB logs/month |

---

## 2. Architecture

### 2.1 Environment-Aware Startup Flow

```
make start (or make stop, make logs)
         ↓
    ENV variable check
         ↓
    ┌────────────────┬────────────────┐
    │   ENV=dev      │   ENV=prod     │
    │   (default)    │                │
    └───────┬────────┴───────┬────────┘
            ↓                ↓
    Standard Docker      Check Loki Plugin
    Compose startup      Check LOKI_URL
            ↓                ↓
    Local logging        docker-compose.yml +
    (json-file)          docker-compose.prod.yml
                              ↓
                         Loki logging driver
                              ↓
                         Grafana Cloud
```

### 2.2 Production Logging Flow

```
Container stdout/stderr
         ↓
    Loki Docker Driver
         ↓ HTTPS POST
    Grafana Cloud Loki
    (logs-prod-us-central1.grafana.net)
         ↓
    ┌─────────────────────────────────┐
    │      Grafana Cloud UI           │
    │  - LogQL queries                │
    │  - Dashboards                   │
    │  - Alert rules                  │
    └─────────────────────────────────┘
         ↓ (on alert trigger)
    Email / Webhook notification
```

### 2.3 File Structure

```
annie/
├── docker-compose.yml           # Base config (unchanged)
├── docker-compose.prod.yml      # Production overrides (NEW)
├── scripts/
│   └── run_docker.sh            # ENV-aware startup (MODIFIED)
├── Makefile                     # Unchanged interface
└── .env                         # Add LOKI_URL for prod
```

---

## 3. Stories

### Story 17.1: Production Docker Compose Override

**Priority**: P0
**Estimate**: 0.5 days

Create `docker-compose.prod.yml` with Loki logging configuration for all services.

**File**: `docker-compose.prod.yml`

**Content**:
```yaml
# docker-compose.prod.yml
# Production overrides - Grafana Loki logging
# Usage: docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

x-loki-logging: &loki-logging
  driver: loki
  options:
    loki-url: "${LOKI_URL}"
    loki-retries: "5"
    loki-batch-size: "400"
    loki-timeout: "2s"

services:
  backend:
    logging:
      <<: *loki-logging
      options:
        loki-url: "${LOKI_URL}"
        loki-external-labels: "service=backend,env=prod,project=annie"

  mcp-server:
    logging:
      <<: *loki-logging
      options:
        loki-url: "${LOKI_URL}"
        loki-external-labels: "service=mcp-server,env=prod,project=annie"

  telegram-bot:
    logging:
      <<: *loki-logging
      options:
        loki-url: "${LOKI_URL}"
        loki-external-labels: "service=telegram-bot,env=prod,project=annie"

  redis:
    logging:
      <<: *loki-logging
      options:
        loki-url: "${LOKI_URL}"
        loki-external-labels: "service=redis,env=prod,project=annie"
```

**Acceptance Criteria**:
- [ ] All four services configured with Loki logging
- [ ] YAML anchor used to avoid duplication
- [ ] Labels include service name, environment, and project
- [ ] File includes usage documentation in comments
- [ ] Validates with `docker compose -f docker-compose.yml -f docker-compose.prod.yml config`

---

### Story 17.2: Environment-Aware Startup Script

**Priority**: P0
**Estimate**: 0.5 days

Modify `scripts/run_docker.sh` to support ENV-based production mode with proper safety checks.

**File**: `scripts/run_docker.sh`

**New/Modified Functions**:

```bash
# Environment detection (add near top)
ENV="${ENV:-dev}"

# New function: Check Loki Docker plugin
check_loki_plugin() {
    if ! docker plugin ls 2>/dev/null | grep -q "loki.*true"; then
        echo -e "${RED}Error: Loki Docker plugin not installed or not enabled${NC}"
        echo ""
        echo "Install with:"
        echo "  docker plugin install grafana/loki-docker-driver:latest --alias loki --grant-all-permissions"
        echo ""
        echo "Or run in dev mode: ENV=dev make start"
        exit 1
    fi
    echo -e "${GREEN}✓ Loki Docker plugin installed${NC}"
}

# New function: Validate production environment variables
validate_prod_env() {
    if [ -z "$LOKI_URL" ] || [ "$LOKI_URL" = "REPLACE_ME" ]; then
        echo -e "${RED}Error: LOKI_URL required for production mode${NC}"
        echo ""
        echo "Set in .env:"
        echo "  LOKI_URL=https://<user-id>:<api-key>@logs-prod-us-central1.grafana.net/loki/api/v1/push"
        echo ""
        echo "Or run in dev mode: ENV=dev make start"
        exit 1
    fi
    echo -e "${GREEN}✓ LOKI_URL configured${NC}"
}

# Modified: start_services function
start_services() {
    echo ""

    if [ "$ENV" = "prod" ]; then
        echo -e "${GREEN}Starting Annie services (${YELLOW}production${GREEN} mode)...${NC}"
        echo ""
        $COMPOSE_CMD -f docker-compose.yml -f docker-compose.prod.yml up --build -d "$@"
        echo ""
        echo -e "${GREEN}✓ Services started with Loki logging enabled${NC}"
        echo "View logs at: https://grafana.com/orgs/<your-org>/stacks"
    else
        echo -e "${GREEN}Starting Annie services (${YELLOW}development${GREEN} mode)...${NC}"
        echo ""
        $COMPOSE_CMD up --build -d "$@"
        echo ""
        echo -e "${GREEN}✓ Services started in development mode${NC}"
    fi

    echo ""
    echo "Use 'make logs' to view logs"
    echo "Use 'make stop' to stop services"
}

# Modified: main function
main() {
    check_docker
    check_docker_compose
    create_env_file
    validate_env

    # Production-specific checks
    if [ "$ENV" = "prod" ]; then
        echo ""
        echo -e "${YELLOW}Production mode enabled (ENV=prod)${NC}"
        check_loki_plugin
        validate_prod_env
    fi

    start_services "$@"
}
```

**Acceptance Criteria**:
- [ ] ENV defaults to "dev" if not set
- [ ] Production mode checks for Loki plugin before starting
- [ ] Production mode validates LOKI_URL is set and not placeholder
- [ ] Clear error messages with remediation steps
- [ ] Uses correct compose files based on ENV
- [ ] Visual indication of which mode is active
- [ ] Existing dev workflow unchanged

---

### Story 17.3: Makefile Updates for Environment Consistency

**Priority**: P0
**Estimate**: 0.25 days

Update Makefile to pass ENV to all relevant commands and ensure `stop`/`logs` work correctly in prod.

**File**: `Makefile`

**Changes**:

```makefile
# Add/modify in DOCKER section

# Compose file selection based on ENV
COMPOSE_FILES = $(if $(filter prod,$(ENV)),-f docker-compose.yml -f docker-compose.prod.yml,)

stop: ## Stop all Docker services
	@echo "Stopping Annie services..."
	@$(COMPOSE_CMD) $(COMPOSE_FILES) down
	@echo "Services stopped."

logs: ## View logs (use SERVICE=name for specific service, ENV=prod for production)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Viewing logs from all services..."; \
		$(COMPOSE_CMD) $(COMPOSE_FILES) logs -f; \
	else \
		echo "Viewing logs from $(SERVICE)..."; \
		$(COMPOSE_CMD) $(COMPOSE_FILES) logs -f $(SERVICE); \
	fi

rebuild: ## Rebuild Docker containers
	@echo "Rebuilding containers..."
	@$(COMPOSE_CMD) $(COMPOSE_FILES) build --no-cache
	@echo "Containers rebuilt."

health: ## Check service health
	@echo "Checking service health..."
	@$(COMPOSE_CMD) $(COMPOSE_FILES) ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

shell: ## Access service shell (use SERVICE=name)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE variable is required"; \
		echo "Usage: make shell SERVICE=backend"; \
		exit 1; \
	fi
	@echo "Accessing $(SERVICE) shell..."
	@$(COMPOSE_CMD) $(COMPOSE_FILES) exec $(SERVICE) /bin/bash || $(COMPOSE_CMD) $(COMPOSE_FILES) exec $(SERVICE) /bin/sh

# Add new target for Loki plugin check
check-loki: ## Verify Loki Docker plugin is installed
	@if docker plugin ls 2>/dev/null | grep -q "loki.*true"; then \
		echo "✓ Loki plugin installed and enabled"; \
	else \
		echo "✗ Loki plugin not installed"; \
		echo "Install with: docker plugin install grafana/loki-docker-driver:latest --alias loki --grant-all-permissions"; \
		exit 1; \
	fi
```

**Update Help Section**:
```makefile
help: ## Show this help message
	@echo "Annie Development Commands"
	@echo "=========================="
	@echo ""
	@echo "  Environment: Use ENV=prod for production mode (e.g., make start ENV=prod)"
	@echo ""
	# ... rest of help
```

**Acceptance Criteria**:
- [ ] COMPOSE_FILES variable correctly selects override file for prod
- [ ] `make stop ENV=prod` stops production containers
- [ ] `make logs ENV=prod` tails production containers
- [ ] `make rebuild ENV=prod` rebuilds with prod config
- [ ] `make health ENV=prod` shows prod container status
- [ ] `make check-loki` validates plugin installation
- [ ] Help text mentions ENV variable

---

### Story 17.4: Environment Configuration

**Priority**: P0
**Estimate**: 0.25 days

Add Loki configuration to environment files and documentation.

**Files**:
- `env.example`
- `CLAUDE.md`

**env.example additions**:
```bash
# ============================================================================
# Cloud Logging - Grafana Loki (Epic 17)
# ============================================================================

# Loki Push URL (required for ENV=prod)
# Get from: Grafana Cloud -> Loki -> Details -> URL
# Format: https://<user-id>:<api-key>@<host>/loki/api/v1/push
LOKI_URL=

# Note: The Loki Docker plugin must be installed for production logging:
#   docker plugin install grafana/loki-docker-driver:latest --alias loki --grant-all-permissions
```

**CLAUDE.md additions** (in Development Commands section):
```markdown
### Environment Modes

Annie supports two environment modes controlled by the `ENV` variable:

| Mode | Command | Logging | Use Case |
|------|---------|---------|----------|
| Development | `make start` | Local (docker logs) | Local development |
| Production | `make start ENV=prod` | Grafana Cloud Loki | Production deployment |

**Production Setup**:
1. Install Loki Docker plugin: `docker plugin install grafana/loki-docker-driver:latest --alias loki --grant-all-permissions`
2. Set `LOKI_URL` in `.env` (get from Grafana Cloud -> Loki -> Details)
3. Run with: `make start ENV=prod`

All commands respect ENV: `make stop ENV=prod`, `make logs ENV=prod`, etc.
```

**Acceptance Criteria**:
- [ ] LOKI_URL added to env.example with documentation
- [ ] Installation instructions for Loki plugin included
- [ ] CLAUDE.md documents environment modes
- [ ] Command examples for both modes

---

### Story 17.5: Grafana Alerting Configuration

**Priority**: P1
**Estimate**: 0.5 days

Document and provide example alert rules for Grafana Cloud.

**File**: `docs/operations/ALERTING.md`

**Content**:
```markdown
# Annie Alerting Configuration

## Grafana Cloud Alerts (Free Tier)

Grafana Cloud free tier includes 50 alert rules. Recommended alerts for Annie:

### Critical Alerts

| Alert Name | LogQL Query | Condition | Notification |
|------------|-------------|-----------|--------------|
| Service Error Spike | `sum(count_over_time({project="annie"} \|= "ERROR" [5m]))` | > 10 | Email |
| Memory Storage Failed | `{service="backend"} \|= "MemoryClient" \|= "failed"` | > 0 | Email |
| Redis Connection Lost | `{project="annie"} \|= "redis" \|= "connection" \|= "error"` | > 0 | Email |
| Container Restart | `{project="annie"} \|= "container" \|= "restart"` | > 0 | Email |

### Warning Alerts

| Alert Name | LogQL Query | Condition | Notification |
|------------|-------------|-----------|--------------|
| LLM Latency High | `{service="backend"} \| json \| duration_ms > 5000` | > 5/hour | Email |
| Tool Call Failures | `{service="mcp-server"} \|= "error" \|= "tool"` | > 3/hour | Email |
| Rate Limit Warnings | `{project="annie"} \|= "rate_limit"` | > 1 | Email |

### Cost Monitoring

| Alert Name | LogQL Query | Condition | Notification |
|------------|-------------|-----------|--------------|
| Grok Live Search Cost | `{service="backend"} \| json \| event="live_search_used"` | > 100/day | Email |

## Setting Up Alerts

1. Navigate to Grafana Cloud -> Alerting -> Alert Rules
2. Click "New Alert Rule"
3. Enter LogQL query from table above
4. Set condition threshold
5. Configure notification channel (email is free)
6. Set evaluation interval (1m recommended)

## Example Alert Rule (YAML export)

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
```
```

**Acceptance Criteria**:
- [ ] Document created with recommended alerts
- [ ] LogQL queries tested and working
- [ ] Step-by-step setup instructions
- [ ] YAML export provided for automation
- [ ] Links to relevant Grafana documentation

---

### Story 17.6: Integration Testing & Validation

**Priority**: P1
**Estimate**: 0.5 days

Validate the complete setup works end-to-end.

**Test Checklist**:

```markdown
## Manual Validation Checklist

### Development Mode
- [ ] `make start` works without ENV set
- [ ] `make logs` shows container output
- [ ] `make stop` stops all containers
- [ ] No Loki-related errors

### Production Mode Prerequisites
- [ ] `make check-loki` passes
- [ ] LOKI_URL set in .env
- [ ] Grafana Cloud account accessible

### Production Mode
- [ ] `make start ENV=prod` starts with Loki logging
- [ ] Logs appear in Grafana Cloud within 10 seconds
- [ ] Labels visible: service, env, project
- [ ] `make stop ENV=prod` stops containers
- [ ] `make logs ENV=prod` still shows local logs during runtime

### Error Handling
- [ ] `make start ENV=prod` fails gracefully if Loki plugin missing
- [ ] `make start ENV=prod` fails gracefully if LOKI_URL not set
- [ ] Error messages include remediation steps

### Alert Validation
- [ ] Create test alert rule in Grafana
- [ ] Trigger alert (e.g., generate ERROR log)
- [ ] Verify email notification received
```

**Acceptance Criteria**:
- [ ] All checklist items verified
- [ ] No regressions in development workflow
- [ ] Documentation matches actual behavior

---

## 4. Technical Considerations

### 4.1 Grafana Cloud Free Tier Limits

| Resource | Free Tier Limit | Annie Estimate |
|----------|-----------------|----------------|
| Logs | 50 GB/month | ~1-5 GB/month |
| Log retention | 14 days | Sufficient |
| Metrics | 10,000 series | Not used (yet) |
| Alert rules | 50 | 5-10 needed |
| Users | 3 | 1 |

### 4.2 Loki Docker Plugin

**Installation**:
```bash
docker plugin install grafana/loki-docker-driver:latest --alias loki --grant-all-permissions
```

**Verification**:
```bash
docker plugin ls
# Should show: loki:latest  Loki Logging Driver  true
```

**Troubleshooting**:
```bash
# Enable plugin if disabled
docker plugin enable loki

# View plugin logs
docker plugin inspect loki
```

### 4.3 Log Volume Estimation

| Service | Est. Lines/Day | Est. Size/Day |
|---------|----------------|---------------|
| Backend | 10,000 | 5 MB |
| MCP Server | 5,000 | 2 MB |
| Telegram Bot | 2,000 | 1 MB |
| Redis | 500 | 0.2 MB |
| **Total** | **17,500** | **~8 MB/day** |

Monthly estimate: ~250 MB (well under 50 GB limit)

### 4.4 Security Considerations

| Concern | Mitigation |
|---------|------------|
| LOKI_URL contains credentials | Added to .gitignore via .env |
| Sensitive data in logs | Already masked via SENSITIVE_VARS |
| Network exposure | HTTPS only, Grafana Cloud handles TLS |

---

## 5. Dependencies

### 5.1 External Services

| Service | Required | Cost | Purpose |
|---------|----------|------|---------|
| Grafana Cloud | Yes | Free | Log aggregation, alerting |
| Loki Docker Plugin | Yes | Free | Log shipping |

### 5.2 Grafana Cloud Setup

1. Sign up at https://grafana.com/products/cloud/ (free tier)
2. Navigate to: Connections -> Hosted Logs -> Loki
3. Copy the push URL (includes embedded credentials)
4. Add to `.env` as `LOKI_URL`

---

## 6. Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Grafana Cloud outage | Low | Low | Logs still in container, queryable locally |
| Free tier exceeded | Low | Very Low | Volume estimates show 0.5% of limit |
| Plugin compatibility | Medium | Low | Docker 20.10+ tested, documented requirements |
| Credential exposure | High | Low | .env in .gitignore, never commit |

---

## 7. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Log delivery latency | <5s p95 | Grafana query timestamp delta |
| Setup time for new env | <10 min | Manual test |
| Dev workflow impact | Zero | Existing commands unchanged |
| Alert response time | <5 min | Time from error to investigation |
| Monthly log volume | <5 GB | Grafana Cloud usage dashboard |

---

## 8. Future Considerations

- **Prometheus Metrics**: Add container resource metrics (CPU, memory) using Grafana Agent
- **Distributed Tracing**: Integrate with Langfuse traces in Grafana
- **Log-based Dashboards**: Pre-built dashboards for Annie operations
- **PagerDuty/Slack Integration**: Upgrade alerting channels
- **Log Sampling**: Reduce volume for high-traffic scenarios
- **Multi-environment**: Staging environment with separate Loki instance
