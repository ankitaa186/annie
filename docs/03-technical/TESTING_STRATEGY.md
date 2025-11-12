# Testing Strategy

## Overview

This document outlines the testing strategy for Annie chatbot, including test types, coverage targets, and testing tools.

## Testing Philosophy

### Principles

1. **Test Early, Test Often** - Write tests alongside code
2. **Test Behavior, Not Implementation** - Focus on what, not how
3. **Maintainable Tests** - Tests should be easy to read and update
4. **Fast Feedback** - Unit tests run quickly, integration tests run reasonably fast
5. **Comprehensive Coverage** - 80%+ code coverage target

### Test Pyramid

```
           ┌────────┐
           │  E2E   │  10%
           │ Tests  │
      ┌────┴────────┴────┐
      │   Integration    │  30%
      │     Tests        │
 ┌────┴──────────────────┴────┐
 │       Unit Tests            │  60%
 │                             │
 └─────────────────────────────┘
```

**Ratio**: 60% Unit, 30% Integration, 10% E2E

## Test Types

### Unit Tests

**Purpose**: Test individual functions/classes in isolation

**Characteristics**:
- Fast (< 1s per test)
- No external dependencies
- Use mocks for external services
- High coverage (90%+)

**Example**:
```python
# tests/unit/test_llm_client.py
import pytest
from unittest.mock import AsyncMock, patch
from backend.core.llm_client import LLMClient

@pytest.mark.asyncio
@patch('httpx.AsyncClient.post')
async def test_stream_chat(mock_post):
    """Test LLM streaming with mock"""
    # Setup mock
    mock_post.return_value = AsyncMock(
        status_code=200,
        aiter_lines=AsyncMock(return_value=[
            'data: {"content":"Hello"}',
            'data: [DONE]'
        ])
    )
    
    # Test
    client = LLMClient(provider="grok4")
    chunks = []
    async for chunk in client.stream_chat([{"role": "user", "content": "Hi"}]):
        chunks.append(chunk)
    
    # Assert
    assert len(chunks) > 0
    assert chunks[0]["content"] == "Hello"
    mock_post.assert_called_once()
```

**Coverage Areas**:
- LLM Client (backend/core/llm_client.py)
- MCP Client (backend/core/mcp_client.py)
- State Manager (backend/core/state_manager.py)
- MCP Tools (mcp_server/tools/)
- Utilities and helpers

### Integration Tests

**Purpose**: Test interactions between components

**Characteristics**:
- Moderate speed (1-5s per test)
- Real Redis/Docker, mocked external APIs
- Focus on component interactions
- Good coverage (70%+)

**Example**:
```python
# tests/integration/test_backend_mcp.py
import pytest
from backend.core.mcp_client import MCPClient

@pytest.mark.asyncio
@pytest.mark.integration
async def test_mcp_tool_execution():
    """Test MCP client calling real MCP server"""
    client = MCPClient(container_name="annie-mcp-server-test")
    
    # Execute tool
    result = await client.call_tool(
        "internet_search",
        {"query": "Python programming"}
    )
    
    # Assert
    assert "results" in result
    assert len(result["results"]) > 0
    assert all("url" in r for r in result["results"])
```

**Coverage Areas**:
- Backend ↔ MCP Server communication
- Backend ↔ Redis state management
- Telegram Bot ↔ Backend API
- MCP Tools ↔ External APIs (mocked)

### End-to-End (E2E) Tests

**Purpose**: Test complete user flows

**Characteristics**:
- Slow (5-30s per test)
- All services running
- Real external services (or staging)
- Focus on critical paths
- Lower coverage (key flows only)

**Example**:
```python
# tests/e2e/test_chat_flow.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_complete_chat_flow():
    """Test complete chat flow from message to response"""
    async with AsyncClient(base_url="http://localhost:8000") as client:
        # Send message
        response = await client.post(
            "/api/v1/chat",
            json={
                "user_id": "e2e_test_user",
                "platform": "test",
                "message": "What's the weather?"
            }
        )
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert "conversation_id" in data
        assert "response" in data
        assert len(data["response"]) > 0
        
        # Verify tools were used
        assert "tools_used" in data
        assert "internet_search" in data["tools_used"]
        
        # Verify memory stored
        # ... additional checks
```

**Coverage Areas**:
- User sends message → Response received
- Tool execution in context
- Memory storage and retrieval
- Error handling and recovery
- Cross-platform functionality

## Testing Tools

### pytest

**Primary testing framework**

**Installation**:
```bash
pip install pytest pytest-asyncio pytest-cov pytest-mock
```

**Configuration** (`pytest.ini`):
```ini
[pytest]
python_files = test_*.py
python_classes = Test*
python_functions = test_*
testpaths = tests
asyncio_mode = auto
markers =
    unit: Unit tests
    integration: Integration tests
    e2e: End-to-end tests
    slow: Slow running tests
```

### pytest-asyncio

**For async test support**

**Usage**:
```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result == expected
```

### pytest-mock

**For mocking**

**Usage**:
```python
def test_with_mock(mocker):
    mock = mocker.patch('module.function')
    mock.return_value = "mocked"
    # Test code
```

### pytest-cov

**For coverage reporting**

**Usage**:
```bash
pytest --cov=backend --cov=mcp_server --cov-report=html tests/
```

### httpx

**For API testing**

**Usage**:
```python
async with httpx.AsyncClient() as client:
    response = await client.get("http://localhost:8000/health")
    assert response.status_code == 200
```

### Docker Compose (Test Environment)

**For integration/E2E tests**

**Setup**:
```yaml
# docker-compose.test.yml
services:
  redis-test:
    image: redis:7.2-alpine
    ports:
      - "6380:6379"
  
  mcp-server-test:
    build: .
    container_name: annie-mcp-server-test
```

## Test Structure

### Directory Layout

```
tests/
├── conftest.py              # Shared fixtures
├── unit/                    # Unit tests
│   ├── backend/
│   │   ├── test_llm_client.py
│   │   ├── test_mcp_client.py
│   │   └── test_state_manager.py
│   ├── mcp_server/
│   │   └── test_tools.py
│   └── telegram_bot/
│       └── test_handlers.py
├── integration/             # Integration tests
│   ├── test_backend_mcp.py
│   ├── test_backend_redis.py
│   └── test_telegram_backend.py
└── e2e/                     # E2E tests
    ├── test_chat_flow.py
    └── test_memory_flow.py
```

### Fixtures

**Shared fixtures** (`tests/conftest.py`):
```python
import pytest
from backend.core.llm_client import LLMClient
from backend.core.mcp_client import MCPClient

@pytest.fixture
async def llm_client():
    """Create LLM client for testing"""
    client = LLMClient(provider="grok4")
    yield client
    await client.close()

@pytest.fixture
async def mcp_client():
    """Create MCP client for testing"""
    client = MCPClient(container_name="annie-mcp-server-test")
    yield client

@pytest.fixture
def sample_messages():
    """Sample conversation messages"""
    return [
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there!"}
    ]

@pytest.fixture
async def redis_client():
    """Create Redis client for testing"""
    import redis.asyncio as redis
    client = redis.from_url("redis://localhost:6380/0")
    yield client
    await client.flushdb()  # Clean up
    await client.close()
```

## Coverage Targets

### Overall Coverage

**Target**: 80%+ overall code coverage

**Measured by**:
```bash
pytest --cov=backend --cov=mcp_server --cov=telegram_bot \
       --cov-report=term-missing \
       --cov-report=html \
       tests/
```

### Per-Module Targets

| Module | Target Coverage | Priority |
|--------|----------------|----------|
| backend/core/llm_client.py | 90% | High |
| backend/core/mcp_client.py | 90% | High |
| backend/core/state_manager.py | 85% | High |
| backend/api/routes/ | 80% | Medium |
| mcp_server/tools/ | 85% | High |
| telegram_bot/ | 75% | Medium |

### What to Exclude

- Configuration files
- Migration scripts
- Test files themselves
- Generated code

**Configuration** (`.coveragerc`):
```ini
[run]
omit =
    tests/*
    */migrations/*
    */config.py
    */conftest.py
    */__pycache__/*
    */venv/*

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
    if TYPE_CHECKING:
```

## Testing Workflows

### Local Development

**Run before committing**:
```bash
# Format code
black .

# Lint code
pylint backend/ mcp_server/ telegram_bot/

# Run unit tests
pytest tests/unit/ -v

# Run with coverage
pytest --cov=backend tests/unit/
```

### Pre-Push

**Run before pushing**:
```bash
# All tests
make test

# Or manually
pytest tests/ -v
```

### CI/CD Pipeline

**GitHub Actions workflow**:
```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio pytest-cov
      
      - name: Run linting
        run: |
          black --check .
          pylint backend/ mcp_server/ telegram_bot/
      
      - name: Run unit tests
        run: pytest tests/unit/ -v --cov=backend --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Mocking Strategies

### External APIs

**LLM APIs**:
```python
@patch('httpx.AsyncClient.post')
async def test_llm_call(mock_post):
    mock_post.return_value = AsyncMock(
        status_code=200,
        json=lambda: {"choices": [{"message": {"content": "Hello"}}]}
    )
    # Test code
```

**agentic-memories API**:
```python
@patch('httpx.AsyncClient.post')
async def test_store_memory(mock_post):
    mock_post.return_value = AsyncMock(
        status_code=200,
        json=lambda: {"memories_created": 3}
    )
    # Test code
```

### Docker Containers

**MCP Server** (use test container):
```python
@pytest.fixture(scope="session")
def mcp_server_container():
    """Start MCP server test container"""
    container = docker.from_env().containers.run(
        "annie-mcp-server:test",
        detach=True,
        name="annie-mcp-server-test",
        remove=True
    )
    yield container
    container.stop()
```

### Database

**Redis**:
```python
@pytest.fixture
async def redis_client():
    """Redis client with separate test database"""
    client = redis.from_url("redis://localhost:6379/15")  # Test DB
    yield client
    await client.flushdb()
    await client.close()
```

## Performance Testing

### Load Testing

**Tool**: Locust

**Example** (`tests/performance/locustfile.py`):
```python
from locust import HttpUser, task, between

class AnnieUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def send_message(self):
        self.client.post(
            "/api/v1/chat",
            json={
                "user_id": f"user_{self.environment.runner.user_count}",
                "platform": "test",
                "message": "Hello!"
            }
        )
```

**Run**:
```bash
locust -f tests/performance/locustfile.py --host http://localhost:8000
```

### Benchmarking

**Tool**: pytest-benchmark

**Example**:
```python
import pytest

def test_affection_calculation(benchmark):
    """Benchmark affection score calculation"""
    result = benchmark(
        calculate_affection_score,
        messages=sample_messages,
        sentiment=0.5
    )
    assert 0 <= result <= 100
```

## Continuous Testing

### Test Automation

- **Pre-commit hooks**: Run linting and formatting
- **CI/CD**: Run full test suite on push
- **Scheduled tests**: Run E2E tests daily
- **Coverage tracking**: Monitor coverage trends

### Test Reporting

**Tools**:
- **Codecov**: Coverage tracking
- **Allure**: Test reports
- **pytest-html**: HTML reports

**Generate report**:
```bash
pytest --html=report.html --self-contained-html tests/
```

## Best Practices

### Writing Good Tests

1. **Descriptive Names**: `test_user_receives_response_when_sending_message`
2. **Arrange-Act-Assert**: Clear test structure
3. **One Assertion Per Test**: Focus on one thing
4. **Independent Tests**: Tests don't depend on each other
5. **Fast Tests**: Unit tests run quickly

### Test Data Management

**Use fixtures** for test data:
```python
@pytest.fixture
def sample_user():
    return {
        "user_id": "test_user_123",
        "platform": "telegram",
        "affection_score": 50.0
    }
```

**Use factories** for complex data:
```python
class UserFactory:
    @staticmethod
    def create(user_id=None, **kwargs):
        return {
            "user_id": user_id or f"user_{random.randint(1000, 9999)}",
            "platform": kwargs.get("platform", "telegram"),
            "affection_score": kwargs.get("affection_score", 0.0)
        }
```

### Avoiding Flaky Tests

- **No time dependencies**: Use freezegun for time-based tests
- **Proper cleanup**: Clean up resources in fixtures
- **Retry mechanisms**: For network-dependent tests
- **Deterministic data**: Use fixed test data

## Troubleshooting Tests

### Debugging Failed Tests

```bash
# Run specific test
pytest tests/unit/test_llm_client.py::test_stream_chat -v

# Run with debugging
pytest --pdb tests/unit/test_llm_client.py

# Show print statements
pytest -s tests/unit/test_llm_client.py

# Show locals on failure
pytest --showlocals tests/unit/test_llm_client.py
```

### Common Issues

**Import errors**:
```bash
# Set PYTHONPATH
export PYTHONPATH=/path/to/annie
pytest tests/
```

**Async errors**:
```python
# Use pytest.mark.asyncio
@pytest.mark.asyncio
async def test_async():
    result = await async_function()
```

**Fixture errors**:
```python
# Check fixture scope
@pytest.fixture(scope="function")  # or "module", "session"
def my_fixture():
    ...
```

## References

- pytest Documentation: https://docs.pytest.org
- pytest-asyncio: https://pytest-asyncio.readthedocs.io
- Coverage.py: https://coverage.readthedocs.io
- Testing Best Practices: https://docs.python-guide.org/writing/tests/

