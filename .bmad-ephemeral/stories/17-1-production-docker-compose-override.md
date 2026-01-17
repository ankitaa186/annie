# Story 17.1: Production Docker Compose Override

**Epic:** 17 - Cloud Logging Integration
**Status:** Drafted
**Priority:** P0
**Estimate:** 0.5 days

---

## User Story

**As a** developer/operator,
**I want** a Docker Compose override file for production logging,
**So that** container logs are shipped to Grafana Cloud Loki without modifying the base configuration.

---

## Acceptance Criteria

| ID | Criterion | Test Method |
|----|-----------|-------------|
| AC-17.1.1 | `docker-compose.prod.yml` exists and configures Loki logging driver for all 4 services (backend, mcp-server, telegram-bot, redis) | File inspection |
| AC-17.1.2 | YAML anchor (`x-loki-logging`) used to avoid configuration duplication | YAML lint |
| AC-17.1.3 | Each service has labels: `service`, `env=prod`, `project=annie` | Config validation |
| AC-17.1.4 | File includes usage documentation in header comments | Code review |
| AC-17.1.5 | `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` validates without errors | Command execution |

---

## Technical Design

### File Location
`docker-compose.prod.yml` (project root)

### Implementation

```yaml
# docker-compose.prod.yml
# Production overrides - Grafana Loki logging
#
# Usage:
#   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
#
# Prerequisites:
#   1. Install Loki Docker plugin:
#      docker plugin install grafana/loki-docker-driver:latest --alias loki --grant-all-permissions
#   2. Set LOKI_URL in .env:
#      LOKI_URL=https://<user-id>:<api-key>@logs-prod-us-central1.grafana.net/loki/api/v1/push
#
# Environment: Production only (ENV=prod)

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

---

## Dependencies

- Base `docker-compose.yml` must exist (already present)
- No Python dependencies
- External: Grafana Cloud account, Loki Docker plugin

---

## Definition of Done

- [ ] File created at `docker-compose.prod.yml`
- [ ] All 4 services configured with Loki logging
- [ ] YAML anchor used for DRY configuration
- [ ] Header comments document usage and prerequisites
- [ ] `docker compose config` validates successfully
- [ ] Story marked as done in sprint-status.yaml
