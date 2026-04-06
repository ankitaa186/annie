# Security Audit: Multi-User Data Isolation

**Date:** 2026-04-06
**Scope:** Static code analysis of all user data flows across Annie's microservices
**Methodology:** 6 parallel domain-specific audits + 2 independent verification passes
**Audited Surfaces:** Redis state, API auth/authZ, memory system, Telegram identity flow, LLM context/streaming, file handling
**Threat Model:** Users interact exclusively via the Telegram bot (primary assessment). Full network exposure analysis included as secondary context.

---

## Executive Summary

Annie's architecture has **sound foundational patterns** for user isolation -- conversation data is Redis-keyed by user/conversation ID, the `inject_user_id` utility prevents LLM-driven identity confusion, LLM clients are stateless per-request, and file handling uses in-memory processing without shared mutable state.

### Telegram-Only Threat Model (Primary)

When Telegram is the sole user-facing entry point, Annie's data isolation is **strong**:
- Telegram provides tamper-proof user identity (`from_user.id` from Telegram servers)
- Whitelist (`AUTHORIZED_USER_IDS`) rejects unauthorized users before any backend call
- `inject_user_id` overrides LLM-hallucinated user IDs at the tool boundary
- All Redis keys are namespaced by `user_id` or `conversation_id`
- Users never see or interact with `conversation_id` values or backend API endpoints

**In this model: 0 CRITICAL, 0 HIGH, 3 MEDIUM, 5 LOW findings.**

The main gaps are: Home Assistant tools lack per-user scoping, `inject_user_id` is a single point of enforcement without defense-in-depth, and backend port exposure creates infrastructure risk.

### Full Network Exposure Model (Secondary)

If the backend API is reachable by untrusted clients (port 8001 is exposed in `docker-compose.yml`), the risk profile escalates significantly: **1 CRITICAL, 4 HIGH, 7 MEDIUM, 8 LOW findings.** Several endpoints lack authentication entirely, and the JWT signature is not verified.

### Risk Summary

**Telegram-Only Model:**

| Severity | Count | Key Theme |
|----------|-------|-----------|
| CRITICAL | 0 | -- |
| HIGH | 0 | -- |
| MEDIUM | 3 | HA tools not user-scoped, backend port exposure (infra), inject_user_id single-point-of-enforcement |
| LOW | 5 | Memory scoping depends on external service, shared outbox queue, filename injection, terminal admin audit trail, authorized IDs in logs |

**Full Network Exposure Model:**

| Severity | Count | Key Theme |
|----------|-------|-----------|
| CRITICAL | 1 | SSE stream endpoint: zero authentication |
| HIGH | 4 | Legacy IDOR endpoint, exposed backend without service auth, unverified JWT, debugpy RCE |
| MEDIUM | 7 | No user_id validation, rate limit bypass, MCP tools trust caller, dev mode bypass, filename prompt injection, auth ID leakage, HA tools not user-scoped |
| LOW | 8 | Various minor isolation gaps (see detailed findings) |

---

## Telegram-Only Threat Model: User A vs User B

When multiple whitelisted Telegram users interact with Annie, the following analysis applies. Findings from the full network model that are not exploitable via Telegram are demoted accordingly.

### How Annie Prevents Cross-User Data Access Today

| Defense Layer | Mechanism | Effectiveness |
|--------------|-----------|--------------|
| **Identity** | `message.from_user.id` from Telegram servers | Tamper-proof; cannot be spoofed by users |
| **Authorization** | `AuthenticationModule` whitelist checked on every handler | Rejects unauthorized users before backend calls |
| **Tool Call Scoping** | `inject_user_id()` overwrites LLM-provided user_ids | Prevents prompt injection identity spoofing |
| **Redis Key Isolation** | Keys namespaced: `session:{user_id}`, `profile:{user_id}`, `conversation:{conv_id}` | Strong per-user separation |
| **LLM Client Isolation** | Fresh `LLMClient()` + `MCPClient()` per request | No shared state between concurrent users |
| **File Isolation** | In-memory BytesIO processing, no temp files, no shared state | No cross-user file access |
| **Conversation Ownership** | `resume_conversation()` checks `owner_id != user_id` | Prevents conversation hijacking |

### Remaining Gaps (Telegram-Only)

#### TG-1: Home Assistant Tools Not User-Scoped — MEDIUM

**Files:** `mcp_server/tools/home_assistant.py`

HA tools use a single shared configuration (`HA_URL`, `HA_ACCESS_TOKEN`, `HA_CONTROL_ALLOWLIST`). No `user_id` parameter exists. If User A says "turn off the lights" and User B says "turn on the lights", they control the **same physical devices**. The voice cooldown is global (`annie:voice_message:last_sent`) -- one user's voice message blocks all others for 60 seconds.

**Impact:** In multi-user/multi-household deployments, any user could control another's home devices via the LLM.

#### TG-2: inject_user_id Is a Single Point of Enforcement — MEDIUM

**Files:** `backend/api/utils.py:46-81`, `backend/api/routes/stream.py:1034-1038`

All MCP tools accept `user_id` as a regular parameter. The MCP server performs **no independent authentication**. Security relies entirely on `inject_user_id()` overriding the user_id before every tool call. If any future code path calls MCP tools without going through this function, user isolation breaks silently.

**Recommendation:** Add user_id validation at the MCP server level as a second line of defense.

#### TG-3: Backend Port Exposed to Host Network — MEDIUM

**File:** `docker-compose.yml`

The backend port is exposed to the host. While Telegram users can't directly reach it, any co-located process, compromised container, or network-adjacent machine can call the backend API with arbitrary user_ids. This is an infrastructure hardening issue.

**Recommendation:** Remove the `ports` mapping or restrict to `127.0.0.1:8001:8000`.

#### TG-4: Memory Retrieval Scoping Depends on External Service — LOW

Memory operations correctly pass `user_id` to `agentic-memories`, but whether that service enforces user scoping on search queries is outside this codebase. If the external service ignores the user_id filter, memories could leak across users.

#### TG-5: Shared Telegram Outbox Queue — LOW

`telegram:outbox` is a single global Redis queue for proactive messages. Each message contains the correct `chat_id` for delivery, but a bug in the delivery worker could theoretically route User A's proactive message to User B.

#### TG-6: Filename Prompt Injection — LOW

Filenames are embedded unsanitized in LLM prompts (`chatgpt_provider.py`). A user could name a file to attempt prompt hijacking, but `inject_user_id` still scopes tool calls to that user only. Risk is behavioral, not data isolation.

#### TG-7: Terminal Tool Admin Audit Trail — LOW

If multiple users are admins, the terminal tool (`mcp_server/tools/terminal.py`) executes host commands with no per-admin audit distinguishing who triggered what.

#### TG-8: Authorized User IDs Logged on Auth Failure — LOW

`telegram_bot/auth.py` logs the complete list of all authorized Telegram user IDs when rejecting unauthorized users. An attacker with log access could harvest these IDs.

---

## Full Network Exposure Model

The findings below apply when the backend API is reachable by untrusted clients (e.g., port 8001 exposed without firewall). **These are demoted to informational context if Telegram is truly the only entry point**, but are documented for defense-in-depth and future architecture changes.

---

## CRITICAL Findings (Network Exposure Model)

### C-1: SSE Stream Endpoint Has No Authentication or Ownership Verification

**Verified by:** Primary audit (LLM Context + API Auth + Redis) + Verification Agent A
**File:** `backend/api/routes/stream.py`

The `GET /api/stream/{conversation_id}` endpoint performs zero authentication or ownership verification. It accepts any `conversation_id`, loads conversation context from Redis, and streams the full LLM response. Anyone with network access to the backend who knows or guesses a `conversation_id` can eavesdrop on the full response stream including user profile data, portfolio, memories, and file attachments.

**Conversation IDs** use `conv_` + 16 hex chars from UUID4 (64 bits entropy). While brute-force is infeasible, IDs could leak through logs or network monitoring.

**Recommendation:** Require authenticated user identity on the stream endpoint. Compare `request.state.user_id` against the conversation owner. For Telegram bot requests, use a short-lived single-use token issued by `/api/chat`.

---

## HIGH Findings (Network Exposure Model)

### H-1: Legacy Conversation History Endpoint — IDOR via URL Path Parameter

**File:** `backend/api/routes/chat.py`

The `GET /api/conversations/{user_id}` legacy endpoint takes `user_id` as a URL path parameter with no authentication. Any caller can read any user's complete conversation history. The newer `conversations.py` router has proper auth, but this legacy endpoint remains active.

**Recommendation:** Remove this legacy endpoint or add authentication.

### H-2: Backend API Exposed Without Service-to-Service Auth

**Files:** `docker-compose.yml`, `telegram_bot/backend_client.py`, `backend/api/middleware/cloudflare_auth.py`

The backend port is exposed to the host. The Telegram bot sends `user_id` as a plain JSON field with no shared secret. The Cloudflare auth middleware passes through requests without CF headers. Any process on the host can impersonate any user.

**Recommendation:** Remove port exposure or add a shared secret header for service-to-service auth.

### H-3: Cloudflare JWT Signature Not Verified

**File:** `backend/api/middleware/cloudflare_auth.py`

JWT is decoded with `verify_signature=False`. Safe only if Cloudflare is the sole ingress. Since the backend is directly reachable (H-2), an attacker can craft a JWT with arbitrary claims.

**Recommendation:** Verify JWT signatures or restrict backend to Docker-internal access.

### H-4: Debugpy Remote Debugger Bound to 0.0.0.0 with Port Exposed

**Files:** `backend/api/main.py`, `docker-compose.yml`

Debug ports are exposed unconditionally in docker-compose.yml. When `ENVIRONMENT=dev` (the default), debugpy listens on `0.0.0.0`, enabling arbitrary code execution.

**Recommendation:** Move debug port mappings to a `docker-compose.dev.yml` override.

---

## MEDIUM Findings (Network Exposure Model)

### M-1: No Input Validation on user_id Format

`user_id` is a freeform `str` with only an emptiness check. No regex, length limit, or character restrictions. Redis keys are built via `f"session:{user_id}"`.

**Recommendation:** Add `pattern=r"^[a-zA-Z0-9_-]{1,64}$"` to the Pydantic field validator.

### M-2: Rate Limiting Bypassed for Unauthenticated Requests

All Telegram-sourced requests and any direct HTTP calls bypass rate limiting entirely.

**Recommendation:** Add IP-based rate limiting as a fallback.

### M-3: MCP Tools Have No Independent Authentication

All MCP tools accept `user_id` as a regular parameter with no server-side enforcement. The MCP server port is also exposed. The `terminal` tool grants host command execution gated only by `is_admin(user_id)`.

**Recommendation:** Add service-to-service auth for MCP calls.

### M-4: Dev Mode Auto-Authentication Bypass

When `ENVIRONMENT=dev` (the default), any request with `Accept: application/json` is auto-authenticated as the dev user which is also in `ADMIN_USER_IDS`. If `ENVIRONMENT` is not set in production, admin access is granted to any HTTP client.

**Recommendation:** Remove the `dev` default. Require explicit `ENVIRONMENT` setting.

### M-5: Filename Not Sanitized — Prompt Injection Vector

Filenames are accepted without sanitization and embedded directly in LLM prompts.

**Recommendation:** Add filename validator: strip path traversal characters, null bytes, newlines, and limit length.

### M-6: Authorized User IDs Logged on Auth Failure

The complete list of all authorized Telegram user IDs is logged when rejecting unauthorized users.

**Recommendation:** Log only the count of authorized users, not the actual IDs.

### M-7: Home Assistant Tools Not User-Scoped

All HA tools use shared configuration with no user isolation. (Same as TG-1.)

---

## LOW Findings (Network Exposure Model)

| ID | Finding | Notes |
|----|---------|-------|
| L-1 | Files stored in Redis with 5-min TTL (contradicts "process-and-discard" docs) | Keyed by conversation_id, low risk |
| L-2 | SCAN operations cross user boundaries in background workers | By design but fragile user_id extraction via `str.replace` |
| L-3 | Global `active_streams` dict allows DoS (100 streams shared across all users) | No per-user stream limit |
| L-4 | Media group buffer lacks explicit user_id check on append | Telegram-assigned IDs prevent collision in practice |
| L-5 | `flushed:{conversation_id}` marker not user-scoped | UUID collision negligible |
| L-6 | Health endpoint exposes internal architecture details without auth | In BYPASS_PATHS, returns component inventory |
| L-7 | User message first 100 chars sent to Langfuse trace metadata | Expected for observability but is user PII |
| L-8 | Global voice cooldown key blocks all users for 60s | Multi-user DoS for voice only |

---

## Positive Findings (What Annie Gets Right)

These patterns are well-designed and should be preserved:

| Pattern | Why It Works |
|---------|-------------|
| `inject_user_id()` overrides LLM-provided user_ids | Prevents prompt injection identity spoofing |
| LLM client is stateless per-request | Fresh `LLMClient()` and `MCPClient()` per stream, no shared state |
| Conversation history keyed by unique conversation_id | Messages cannot cross-contaminate |
| `resume_conversation()` validates ownership | `owner_id != user_id` check prevents conversation hijacking |
| File processing uses in-memory BytesIO (no temp files) | No disk persistence, no cross-user file access |
| Provider failover is stateless | Same messages list, fresh provider instance |
| User ID from Telegram is server-side (from_user.id) | Trusted source, cannot be spoofed by Telegram users |
| Base64 file content never logged | Only metadata logged (filename, size, mime_type) |
| Redis keys consistently namespaced | `session:{user_id}`, `profile:{user_id}`, `portfolio:{user_id}` |

---

## Remediation Priority

### Immediate (Before Multi-User Deployment)

1. **TG-1**: Scope HA tools per user if multi-household is planned
2. **TG-2**: Add user_id validation at the MCP server level (defense-in-depth)
3. **TG-3**: Remove backend port exposure or bind to `127.0.0.1`

### Short-Term (Infrastructure Hardening)

4. **H-2/H-3**: Add service-to-service auth or restrict to Docker-internal networking
5. **M-1**: Add user_id format validation
6. **M-5**: Sanitize filenames before embedding in LLM prompts
7. **H-4**: Move debug ports to dev-only compose override

### Longer-Term

8. **C-1/H-1**: Add auth to stream endpoint and remove legacy conversation endpoint
9. **M-2/M-3**: Rate limiting + MCP server auth
10. **M-6**: Fix auth ID logging

---

## Threat Model Summary

```
TELEGRAM USER (only entry point)
       |
       | Telegram API (tamper-proof from_user.id)
       v
  Telegram Bot
  [Whitelist check] ──── Rejected if not authorized
       |
       | HTTP (Docker internal network)
       | user_id in JSON body (trusted: bot is sole caller)
       v
  Backend API (port 8001 - also exposed to host)
  [inject_user_id before every tool call]
       |
       | Docker exec (stdio) / HTTP
       v
  MCP Server (trusts caller's user_id)
       |
       v
  External Services (agentic-memories, HA, etc.)
```

**Core architectural assumption:** The Telegram bot is the sole caller of the backend API. This holds in the current deployment but should be hardened with service-to-service auth for defense-in-depth.
