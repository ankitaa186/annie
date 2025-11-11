# Story 1.1: Project Structure & Repository Setup

Status: done

## Story

As a developer,  
I want a properly structured project repository,  
so that I can organize code efficiently and follow best practices.

## Acceptance Criteria

1. **AC #1**: Given a fresh repository, when I check the directory structure, then it includes `backend/`, `mcp_server/`, `telegram_bot/`, `scripts/`, `docs/` directories
2. **AC #2**: Given the project structure, when I check the repository, then `.gitignore` exists with appropriate exclusions (Python, Docker, IDE files, `.env`, `__pycache__`, `*.pyc`)
3. **AC #3**: Given the project structure, when I check the repository, then `.dockerignore` exists with appropriate exclusions (`.git`, `docs`, `*.md`, `.env`)
4. **AC #4**: Given the repository, when I check Python structure, then virtual environment directories are excluded and `requirements.txt` structure is defined
5. **AC #5**: Given the repository, when I check documentation, then initial `README.md` exists with project overview and setup instructions

## Tasks / Subtasks

- [x] Task 1: Create directory structure (AC: #1)
  - [x] Create `backend/` directory
  - [x] Create `mcp_server/` directory
  - [x] Create `telegram_bot/` directory
  - [x] Create `scripts/` directory
  - [x] Verify `docs/` directory exists (already exists)
  - [x] Verify directory structure matches architecture requirements

- [x] Task 2: Create `.gitignore` file (AC: #2)
  - [x] Add Python exclusions (`__pycache__/`, `*.pyc`, `*.pyo`, `*.pyd`, `.Python`, `*.so`, `*.egg`, `*.egg-info/`, `dist/`, `build/`)
  - [x] Add virtual environment exclusions (`venv/`, `env/`, `.venv/`, `.env/`)
  - [x] Add Docker exclusions (`.dockerignore` already handled separately)
  - [x] Add IDE exclusions (`.vscode/`, `.idea/`, `*.swp`, `*.swo`, `*~`)
  - [x] Add OS exclusions (`.DS_Store`, `Thumbs.db`)
  - [x] Add environment file exclusion (`.env`)
  - [x] Add test coverage exclusions (`.coverage`, `htmlcov/`, `.pytest_cache/`)

- [x] Task 3: Create `.dockerignore` file (AC: #3)
  - [x] Exclude `.git/` directory
  - [x] Exclude `docs/` directory (documentation not needed in containers)
  - [x] Exclude `*.md` files (markdown files not needed in containers)
  - [x] Exclude `.env` file (environment variables passed via Docker Compose)
  - [x] Exclude test files (`tests/`, `*_test.py`, `test_*.py`)
  - [x] Exclude development files (`.gitignore`, `.dockerignore`, `Makefile`)

- [x] Task 4: Define Python structure and requirements (AC: #4)
  - [x] Create `backend/requirements.txt` placeholder (empty or with basic structure comment)
  - [x] Create `mcp_server/requirements.txt` placeholder (empty or with basic structure comment)
  - [x] Create `telegram_bot/requirements.txt` placeholder (empty or with basic structure comment)
  - [x] Verify virtual environment directories are excluded in `.gitignore`
  - [x] Document Python version requirement (3.12+) in README

- [x] Task 5: Create initial `README.md` (AC: #5)
  - [x] Add project overview (Annie - Personal AI Companion)
  - [x] Add project description referencing PRD
  - [x] Add directory structure explanation
  - [x] Add setup instructions (prerequisites: Docker, Docker Compose)
  - [x] Add quick start guide (reference to `run_docker.sh` - will be created in Story 1.5)
  - [x] Add links to key documentation (PRD, Architecture Plan)
  - [x] Add project status badge or note (V1.0 MVP in development)

## Dev Notes

### Architecture Alignment

This story establishes the foundational project structure that aligns with the Architecture Plan's service architecture:

- **Backend Service**: `backend/` directory will contain FastAPI application [Source: docs/02-architecture/ARCHITECTURE_PLAN.md#Backend-API-Service]
- **MCP Server Service**: `mcp_server/` directory will contain MCP protocol implementation [Source: docs/02-architecture/ARCHITECTURE_PLAN.md#MCP-Server-Service]
- **Telegram Bot Service**: `telegram_bot/` directory will contain Telegram bot implementation [Source: docs/02-architecture/ARCHITECTURE_PLAN.md#Telegram-Bot-Service]
- **Scripts**: `scripts/` directory for operational scripts (run_docker.sh, etc.)
- **Documentation**: `docs/` directory already exists with planning documents

### Project Structure Notes

**Directory Structure:**
```
annie/
├── backend/           # FastAPI backend service
├── mcp_server/        # MCP server with tools
├── telegram_bot/      # Telegram bot service
├── scripts/           # Operational scripts
├── docs/              # Documentation (already exists)
├── .gitignore         # Git exclusions
├── .dockerignore      # Docker build exclusions
├── README.md          # Project overview and setup
└── docker-compose.yml # (Will be created in Story 1.2)
```

**Alignment with Tech Spec:**
- Structure matches Epic 1 Tech Spec requirements [Source: .bmad-ephemeral/stories/tech-spec-epic-1.md#Services-and-Modules]
- All required directories for Docker services are present
- Structure supports hot-reload via Docker volume mounts (to be configured in Story 1.2)

**Naming Conventions:**
- Use kebab-case for directory names (`mcp_server` vs `mcp-server` - using underscore for Python module compatibility)
- Use lowercase for file names (`.gitignore`, `.dockerignore`)
- Follow Python package structure conventions for service directories

### Security Considerations

- `.env` file must be excluded from both `.gitignore` and `.dockerignore` [Source: .bmad-ephemeral/stories/tech-spec-epic-1.md#Security]
- Sensitive files should never be committed to version control
- Virtual environment directories excluded to prevent accidental commits

### Testing Standards

- No automated tests required for this story (structure validation)
- Manual verification: Check directory structure, verify ignore files work correctly
- Test: Create test files matching ignore patterns, verify they're excluded

### References

- **Epic Breakdown**: [Source: docs/epics-and-stories.md#Story-1.1]
- **Tech Spec**: [Source: .bmad-ephemeral/stories/tech-spec-epic-1.md]
- **Architecture Plan**: [Source: docs/02-architecture/ARCHITECTURE_PLAN.md]
- **PRD**: [Source: docs/01-product/PRODUCT_REQUIREMENTS.md]
- **V1 Detailed Tasks**: [Source: docs/04-implementation/V1_DETAILED_TASKS.md#Task-1.1]

### Learnings from Previous Story

First story in epic - no predecessor context.

## Dev Agent Record

### Context Reference

- `.bmad-ephemeral/stories/1-1-project-structure-repository-setup.context.xml`

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

**Story 1.1 Implementation Complete** ✅

**Completed Tasks:**
1. ✅ Directory structure created/verified: `backend/`, `mcp_server/`, `telegram_bot/`, `scripts/`, `docs/`
2. ✅ `.gitignore` file created with comprehensive exclusions (Python, virtual environments, IDE files, OS files, .env, test coverage)
3. ✅ `.dockerignore` file created with appropriate exclusions (.git, docs, *.md, .env, test files, development files)
4. ✅ `requirements.txt` files created in all service directories (backend/, mcp_server/, telegram_bot/)
5. ✅ `README.md` updated with project overview, description, directory structure, setup instructions, and documentation links

**Files Created:**
- `backend/requirements.txt` - Python requirements placeholder for backend service
- `mcp_server/requirements.txt` - Python requirements placeholder for MCP server
- `telegram_bot/requirements.txt` - Python requirements placeholder for Telegram bot

**Files Updated:**
- `.gitignore` - Enhanced with IDE exclusions (.vscode/, .idea/) and comprehensive Python/Docker/OS exclusions
- `.dockerignore` - Updated with all required exclusions for Docker builds
- `README.md` - Enhanced with project overview, directory structure explanation, setup instructions, and documentation links

**Verification:**
- ✅ All required directories exist and match architecture requirements
- ✅ `.gitignore` excludes all required patterns (Python, virtual environments, IDE, OS, .env, test coverage)
- ✅ `.dockerignore` excludes all required patterns (.git, docs, *.md, .env, test files, development files)
- ✅ All `requirements.txt` files exist with placeholder content
- ✅ `README.md` includes all required sections per acceptance criteria

**Next Steps:**
- Story 1.2: Docker Compose & Service Configuration (depends on Story 1.1)

### File List

**Created:**
- `backend/requirements.txt` (NEW)
- `mcp_server/requirements.txt` (NEW)
- `telegram_bot/requirements.txt` (NEW)

**Modified:**
- `.gitignore` (MODIFIED - enhanced with IDE exclusions and comprehensive patterns)
- `.dockerignore` (MODIFIED - updated with all required exclusions)
- `README.md` (MODIFIED - enhanced with project overview, structure, setup instructions, documentation links)
