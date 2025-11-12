# Contributing to Annie

Thank you for your interest in contributing to Annie! This document provides guidelines for contributing to the project.

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Getting Started](#getting-started)
3. [Development Process](#development-process)
4. [Coding Standards](#coding-standards)
5. [Testing Guidelines](#testing-guidelines)
6. [Documentation](#documentation)
7. [Pull Request Process](#pull-request-process)
8. [Issue Guidelines](#issue-guidelines)

## Code of Conduct

### Our Pledge

We are committed to providing a welcoming and inspiring community for all. Please be respectful and constructive in your interactions.

### Expected Behavior

- Use welcoming and inclusive language
- Be respectful of differing viewpoints
- Accept constructive criticism gracefully
- Focus on what is best for the community
- Show empathy towards other community members

### Unacceptable Behavior

- Trolling, insulting comments, or personal attacks
- Public or private harassment
- Publishing others' private information
- Other conduct which could reasonably be considered inappropriate

## Getting Started

### Prerequisites

1. Read the [Development Setup Guide](./docs/04-implementation/DEVELOPMENT_SETUP_GUIDE.md)
2. Set up your local development environment
3. Familiarize yourself with the [Architecture Plan](./docs/02-architecture/ARCHITECTURE_PLAN.md)
4. Review existing [Issues](https://github.com/yourusername/annie/issues)

### Finding Something to Work On

**Good First Issues**:
- Look for issues tagged `good-first-issue`
- Documentation improvements
- Test coverage improvements
- Bug fixes

**Areas Needing Help**:
- Backend API implementation
- MCP tool development
- Telegram bot features
- Testing and quality assurance
- Documentation

## Development Process

### 1. Fork and Clone

```bash
# Fork the repository on GitHub
# Then clone your fork
git clone https://github.com/YOUR_USERNAME/annie.git
cd annie

# Add upstream remote
git remote add upstream https://github.com/yourusername/annie.git
```

### 2. Create a Branch

```bash
# Update your fork
git checkout main
git pull upstream main

# Create a feature branch
git checkout -b feature/your-feature-name

# Or for bug fixes
git checkout -b fix/bug-description
```

**Branch Naming Convention**:
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation changes
- `test/` - Test additions/improvements
- `refactor/` - Code refactoring
- `chore/` - Maintenance tasks

### 3. Make Changes

- Follow the [Coding Standards](#coding-standards)
- Write tests for new functionality
- Update documentation as needed
- Keep commits focused and atomic

### 4. Test Your Changes

```bash
# Run all tests
make test

# Run specific tests
pytest tests/test_your_feature.py -v

# Check code formatting
black --check .

# Check linting
pylint backend/ mcp_server/ telegram_bot/
```

### 5. Commit Changes

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```bash
# Format: <type>(<scope>): <description>

git commit -m "feat(backend): add user authentication"
git commit -m "fix(mcp): resolve tool execution timeout"
git commit -m "docs(api): update endpoint documentation"
git commit -m "test(backend): add unit tests for chat endpoint"
```

**Commit Types**:
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation only
- `style` - Code style changes (formatting, etc.)
- `refactor` - Code refactoring
- `test` - Adding or updating tests
- `chore` - Maintenance tasks
- `perf` - Performance improvements

### 6. Push and Create PR

```bash
# Push to your fork
git push origin feature/your-feature-name

# Create Pull Request on GitHub
```

## Coding Standards

### Python Style Guide

**Follow PEP 8** with these specifics:

```python
# Line length: 88 characters (Black default)
# Indentation: 4 spaces
# Quotes: Double quotes for strings

# Good
def process_message(user_id: str, message: str) -> dict:
    """Process a chat message and return response.
    
    Args:
        user_id: Unique user identifier
        message: User message content
        
    Returns:
        Response dictionary with conversation_id and response text
    """
    result = {
        "conversation_id": generate_id(),
        "response": "Hello!"
    }
    return result

# Bad
def ProcessMessage(userId, msg):
    return {'conversationId': generate_id(), 'response': 'Hello!'}
```

### Type Hints

**Always use type hints**:

```python
from typing import Optional, Dict, List, Any

async def retrieve_memories(
    user_id: str,
    query: str,
    limit: int = 5
) -> Dict[str, Any]:
    """Retrieve memories from agentic-memories."""
    ...
```

### Docstrings

**Use Google-style docstrings**:

```python
def calculate_affection_score(
    messages: List[dict],
    sentiment: float
) -> float:
    """Calculate user affection score.
    
    Args:
        messages: List of conversation messages
        sentiment: Sentiment analysis score (-1 to 1)
    
    Returns:
        Affection score (0-100)
    
    Raises:
        ValueError: If sentiment is out of range
    """
    if not -1 <= sentiment <= 1:
        raise ValueError("Sentiment must be between -1 and 1")
    ...
```

### Code Formatting

**Use Black for formatting**:

```bash
# Format all files
black .

# Format specific file
black backend/api/main.py

# Check without modifying
black --check .
```

### Linting

**Use Pylint**:

```bash
# Lint all code
pylint backend/ mcp_server/ telegram_bot/

# Lint specific file
pylint backend/api/main.py

# Ignore specific warnings (use sparingly)
# pylint: disable=line-too-long
```

### Import Organization

```python
# Standard library
import os
import sys
from typing import Optional, Dict

# Third-party
import httpx
from fastapi import FastAPI, Request

# Local
from backend.core.llm_client import LLMClient
from backend.models import Message
```

## Testing Guidelines

### Test Structure

```
tests/
├── unit/                  # Unit tests
│   ├── test_llm_client.py
│   ├── test_mcp_client.py
│   └── test_state_manager.py
├── integration/           # Integration tests
│   ├── test_backend_api.py
│   └── test_mcp_tools.py
└── e2e/                   # End-to-end tests
    └── test_chat_flow.py
```

### Writing Tests

**Use pytest**:

```python
import pytest
from backend.core.llm_client import LLMClient

@pytest.fixture
async def llm_client():
    """Create LLM client for testing."""
    client = LLMClient(provider="grok4")
    yield client
    await client.close()

@pytest.mark.asyncio
async def test_llm_stream_chat(llm_client):
    """Test LLM streaming chat."""
    messages = [{"role": "user", "content": "Hello!"}]
    
    chunks = []
    async for chunk in llm_client.stream_chat(messages):
        chunks.append(chunk)
    
    assert len(chunks) > 0
    assert chunks[-1].get("done") is True

def test_affection_score_calculation():
    """Test affection score calculation."""
    score = calculate_affection_score(
        messages=[{"role": "user", "content": "I love this!"}],
        sentiment=0.8
    )
    assert 0 <= score <= 100
    assert score > 50  # Positive sentiment
```

### Test Coverage

**Aim for 80%+ coverage**:

```bash
# Run with coverage
pytest --cov=backend --cov=mcp_server --cov=telegram_bot tests/

# Generate HTML report
pytest --cov=backend --cov-report=html tests/

# View report
open htmlcov/index.html
```

### Mock External Services

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
@patch('httpx.AsyncClient.post')
async def test_store_memory(mock_post):
    """Test memory storage with mocked API."""
    mock_post.return_value = AsyncMock(
        status_code=200,
        json=lambda: {"memories_created": 3}
    )
    
    tool = MemoriesMCPTool()
    result = await tool.store_memory("user_123", [])
    
    assert result["memories_created"] == 3
    mock_post.assert_called_once()
```

## Documentation

### Code Documentation

- **All functions**: Docstring with description, args, returns
- **All classes**: Docstring with purpose and attributes
- **Complex logic**: Inline comments explaining why

### API Documentation

- Update `docs/03-technical/API_SPECIFICATIONS.md` for API changes
- Include request/response examples
- Document error cases

### Architecture Documentation

- Update architecture docs for significant changes
- Include diagrams where helpful
- Explain design decisions

## Pull Request Process

### Before Submitting

1. ✅ Code follows style guide
2. ✅ All tests pass
3. ✅ New tests added for new features
4. ✅ Documentation updated
5. ✅ Commits follow conventional format
6. ✅ Branch is up to date with main

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing completed

## Checklist
- [ ] Code follows style guide
- [ ] Self-review completed
- [ ] Comments added for complex logic
- [ ] Documentation updated
- [ ] No new warnings

## Related Issues
Closes #123
```

### Review Process

1. **Automated Checks**: CI/CD runs tests and linting
2. **Code Review**: Maintainer reviews changes
3. **Feedback**: Address review comments
4. **Approval**: Maintainer approves PR
5. **Merge**: PR merged to main

### After Merge

- Delete your feature branch
- Pull latest main
- Update your fork

```bash
git checkout main
git pull upstream main
git push origin main
git branch -d feature/your-feature-name
```

## Issue Guidelines

### Reporting Bugs

**Include**:
- Clear, descriptive title
- Steps to reproduce
- Expected vs actual behavior
- Environment (OS, Python version, Docker version)
- Logs/screenshots if applicable

**Template**:
```markdown
**Bug Description**
Clear description of the bug

**Steps to Reproduce**
1. Step one
2. Step two
3. Step three

**Expected Behavior**
What should happen

**Actual Behavior**
What actually happens

**Environment**
- OS: macOS 14
- Python: 3.12
- Docker: 24.0.0
- Annie Version: 1.0.0

**Logs**
```
Paste relevant logs
```

### Suggesting Features

**Include**:
- Clear use case
- Proposed solution
- Alternative solutions considered
- Implementation complexity estimate

### Asking Questions

- Check existing documentation first
- Search existing issues
- Use GitHub Discussions for questions
- Provide context and what you've tried

## Community

### Communication Channels

- **GitHub Issues**: Bug reports, feature requests
- **GitHub Discussions**: Questions, ideas, general discussion
- **Pull Requests**: Code contributions

### Response Times

- **Bugs**: Aim to respond within 48 hours
- **Features**: Aim to respond within 1 week
- **PRs**: Aim to review within 3-5 days

### Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md
- Mentioned in release notes
- Credited in commit history

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Questions?

Feel free to:
- Open an issue
- Start a discussion
- Reach out to maintainers

Thank you for contributing to Annie! 🎉

