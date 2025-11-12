# Story 1.3: Environment Configuration & Secrets Management

Status: done

## Story

As a developer,  
I want environment configuration and secrets management,  
so that I can securely configure Annie without hardcoding sensitive data.

## Acceptance Criteria

1. **AC #1**: Given the project, when I check `env.example`, then it includes all required environment variables with descriptions:
   - LLM API keys (Grok-4, ChatGPT-5)
   - Telegram bot token
   - Brave Search API key
   - Stock API key
   - agentic-memories service URL
   - Redis configuration
   - Service ports and URLs

2. **AC #2**: Given environment setup, when I run `./run_docker.sh`, then it interactively creates `.env` file from `env.example` if missing

3. **AC #3**: Given environment variables, when services start, then all required variables are validated and missing variables cause clear error messages

4. **AC #4**: Given environment variables, when I check security, then sensitive values (API keys, tokens) are never logged or exposed in error messages

5. **AC #5**: Given environment configuration, when services start, then environment-specific values (dev/staging/prod) can be configured via `.env` file

6. **AC #6**: Given the `.env` file, when I check `.gitignore`, then `.env` is excluded from version control

## Tasks / Subtasks

- [ ] Task 1: Enhance env.example with all required variables (AC: #1)
  - [ ] Review docker-compose.yml to identify all environment variables used
  - [ ] Add LLM provider configuration (LLM_PROVIDER, GROK_API_KEY, CHATGPT_API_KEY)
  - [ ] Add Telegram bot token (TELEGRAM_BOT_TOKEN)
  - [ ] Add tool API keys (BRAVE_SEARCH_API_KEY, STOCK_API_KEY)
  - [ ] Add agentic-memories service URL (AGENTIC_MEMORIES_URL)
  - [ ] Add Redis configuration (REDIS_HOST, REDIS_PORT)
  - [ ] Add service ports and URLs (BACKEND_PORT, BACKEND_URL)
  - [ ] Add logging configuration (LOG_LEVEL)
  - [ ] Add environment type (ENVIRONMENT=dev/staging/prod)
  - [ ] Add descriptive comments for each variable group
  - [ ] Add usage instructions at the top of the file
  - [ ] Verify all variables match docker-compose.yml references

- [ ] Task 2: Create run_docker.sh script with .env generation (AC: #2)
  - [ ] Create `scripts/run_docker.sh` script
  - [ ] Add shebang and error handling
  - [ ] Check if Docker is installed and version is compatible
  - [ ] Check if Docker Compose is available
  - [ ] Check if `.env` file exists
  - [ ] If `.env` missing, prompt user to create from `env.example`
  - [ ] Copy `env.example` to `.env` if user confirms
  - [ ] Provide instructions for filling in values
  - [ ] Validate `.env` file has required variables (non-empty)
  - [ ] Run `docker-compose up` with appropriate flags
  - [ ] Make script executable: `chmod +x scripts/run_docker.sh`

- [ ] Task 3: Create environment validation module (AC: #3, #4)
  - [ ] Create `backend/api/config.py` module
  - [ ] Define required environment variables per service
  - [ ] Create validation function that checks required variables
  - [ ] Create error messages that don't expose sensitive values
  - [ ] Mask sensitive values in error messages (show only first/last chars)
  - [ ] Create `mcp_server/config.py` module with validation
  - [ ] Create `telegram_bot/config.py` module with validation
  - [ ] Add validation calls in service startup code (placeholders for now)
  - [ ] Test validation with missing variables
  - [ ] Test validation with invalid values

- [ ] Task 4: Verify .gitignore excludes .env (AC: #6)
  - [ ] Check `.gitignore` file
  - [ ] Verify `.env` is in the exclusion list
  - [ ] Verify `.env.local`, `.env.*.local` patterns are excluded
  - [ ] Document that .env exclusion is already configured

- [ ] Task 5: Document environment configuration (AC: #5)
  - [ ] Update README.md with environment setup instructions
  - [ ] Document how to create `.env` from `env.example`
  - [ ] Document environment-specific configuration (dev/staging/prod)
  - [ ] Document required vs optional variables
  - [ ] Add troubleshooting section for common env issues

- [ ] Task 6: Test environment configuration (AC: #1, #2, #3, #5)
  - [ ] Test `env.example` includes all required variables
  - [ ] Test `run_docker.sh` creates `.env` interactively when missing
  - [ ] Test validation fails with clear messages when variables missing
  - [ ] Test sensitive values are masked in error messages
  - [ ] Test environment-specific values work (ENVIRONMENT variable)
  - [ ] Verify `.env` is not tracked by git

## Dev Notes

### Architecture Alignment

This story implements environment configuration that aligns with the Architecture Plan:

- **Secrets Management**: Environment variables for V1 (as per architecture) [Source: docs/02-architecture/ARCHITECTURE_PLAN.md#Security-Architecture]
- **Configuration Management**: `.env` file pattern for local development [Source: docs/02-architecture/ARCHITECTURE_PLAN.md#Configuration-Management]
- **Security**: `.env` excluded from version control, sensitive data masking [Source: docs/02-architecture/ARCHITECTURE_PLAN.md#Security-Architecture]

### Learnings from Previous Stories

**From Story 1.1:**
- `.gitignore` already configured with `.env` exclusion [Source: .bmad-ephemeral/stories/1-1-project-structure-repository-setup.md]
- `scripts/` directory exists for operational scripts

**From Story 1.2:**
- `docker-compose.yml` references environment variables that need documentation
- Environment variables are passed to services via Docker Compose
- Services expect specific variable names (GROK_API_KEY, CHATGPT_API_KEY, etc.)

**Reuse:**
- Use existing `.gitignore` configuration
- Reference `docker-compose.yml` for variable names
- Follow existing `env.example` structure (enhance it)

**Patterns to Establish:**
- Environment variable naming: UPPER_SNAKE_CASE
- Required variables: Validate on service startup
- Sensitive values: Mask in logs and error messages (show only first 4 and last 4 chars)

### Project Structure Notes

**Environment Files:**
- `env.example` - Template file with all variables and descriptions (committed to git)
- `.env` - Actual environment file with real values (excluded from git)
- `scripts/run_docker.sh` - Script to set up and run Docker Compose

**Configuration Modules:**
- `backend/api/config.py` - Backend environment configuration and validation
- `mcp_server/config.py` - MCP server environment configuration and validation
- `telegram_bot/config.py` - Telegram bot environment configuration and validation

**Alignment with Tech Spec:**
- Matches Epic 1 Tech Spec Environment Variables Schema [Source: .bmad-ephemeral/stories/tech-spec-epic-1.md#Environment-Variables-Schema]
- Validation pattern matches tech spec requirements

### Environment Variables Required

**Backend Service:**
- `LOG_LEVEL` (optional, default: INFO)
- `REDIS_HOST` (optional, default: redis)
- `REDIS_PORT` (optional, default: 6379)
- `MCP_SERVER_NAME` (optional, default: mcp-server)
- `GROK_API_KEY` (required if using Grok)
- `CHATGPT_API_KEY` (required if using ChatGPT)
- `AGENTIC_MEMORIES_URL` (required)
- `BACKEND_PORT` (optional, default: 8000)

**MCP Server Service:**
- `LOG_LEVEL` (optional, default: INFO)
- `BRAVE_SEARCH_API_KEY` (required for internet access tool)
- `STOCK_API_KEY` (required for stock trader tool)
- `AGENTIC_MEMORIES_URL` (required)

**Telegram Bot Service:**
- `LOG_LEVEL` (optional, default: INFO)
- `TELEGRAM_BOT_TOKEN` (required)
- `BACKEND_URL` (optional, default: http://backend:8000)

**Redis Service:**
- No environment variables needed (uses defaults)

### Security Considerations

- **Secrets Masking**: Never log full API keys or tokens
- **Error Messages**: Don't expose sensitive values in error messages
- **Validation**: Validate required variables on startup, fail fast with clear messages
- **Git Exclusion**: Ensure `.env` is never committed (already in `.gitignore`)

### Testing Standards

**Manual Verification:**
- `cat env.example` - Verify all variables documented
- `./scripts/run_docker.sh` - Test interactive `.env` creation
- Remove `.env` and run script - Verify prompts user
- Test with missing variables - Verify clear error messages
- Test with invalid values - Verify validation errors

**Security Testing:**
- Test error messages don't expose full API keys
- Test logs don't contain sensitive values
- Verify `.env` is not tracked by git: `git status`

### References

- **Epic Breakdown**: [Source: docs/epics-and-stories.md#Story-1.3]
- **Tech Spec**: [Source: .bmad-ephemeral/stories/tech-spec-epic-1.md#Environment-Variables-Schema]
- **Architecture Plan**: [Source: docs/02-architecture/ARCHITECTURE_PLAN.md#Security-Architecture]
- **V1 Detailed Tasks**: [Source: docs/04-implementation/V1_DETAILED_TASKS.md#Task-1.6]
- **Previous Stories**: 
  - [Source: .bmad-ephemeral/stories/1-1-project-structure-repository-setup.md]
  - [Source: .bmad-ephemeral/stories/1-2-docker-compose-service-configuration.md]

## Dev Agent Record

### Context Reference

- `.bmad-ephemeral/stories/1-3-environment-configuration-secrets-management.context.xml`

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

**Story 1.3 Implementation Complete** ✅

**Completed Tasks:**
1. ✅ Enhanced `env.example` with all required environment variables matching docker-compose.yml
2. ✅ Created `scripts/run_docker.sh` with interactive .env file generation
3. ✅ Created environment validation modules for all services (backend/api/config.py, mcp_server/config.py, telegram_bot/config.py)
4. ✅ Implemented sensitive value masking (shows first 4 and last 4 characters)
5. ✅ Verified .gitignore excludes .env file (already configured)
6. ✅ Updated README.md with comprehensive environment setup instructions

**Acceptance Criteria Met:**
- ✅ AC #1: env.example includes all required variables with descriptions
- ✅ AC #2: run_docker.sh interactively creates .env from env.example if missing
- ✅ AC #3: Validation modules check required variables and provide clear error messages
- ✅ AC #4: Sensitive values are masked in error messages (mask_sensitive_value function)
- ✅ AC #5: Environment-specific configuration supported via ENVIRONMENT variable
- ✅ AC #6: .env is excluded from version control (verified in .gitignore)

**Files Created:**
- `env.example` - Enhanced template with all variables and descriptions
- `scripts/run_docker.sh` - Interactive Docker startup script
- `backend/api/config.py` - Backend environment configuration and validation
- `mcp_server/config.py` - MCP server environment configuration and validation
- `telegram_bot/config.py` - Telegram bot environment configuration and validation

**Files Modified:**
- `README.md` - Added comprehensive environment setup section

**Verification:**
- ✅ env.example includes all variables from docker-compose.yml
- ✅ run_docker.sh syntax validated
- ✅ All config modules load successfully
- ✅ Sensitive value masking works correctly (tested: "secret-key-12345" → "secr...2345")
- ✅ .env is correctly ignored by git

### File List

**Created Files:**
- `env.example` (enhanced)
- `scripts/run_docker.sh`
- `backend/api/config.py`
- `mcp_server/config.py`
- `telegram_bot/config.py`

**Modified Files:**
- `README.md`
