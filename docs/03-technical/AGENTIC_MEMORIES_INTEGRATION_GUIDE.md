# agentic-memories Integration Guide

## Overview

This guide provides detailed instructions for integrating Annie with the [agentic-memories](https://github.com/yourusername/agentic-memories) service.

## Prerequisites

### Running agentic-memories

**Location**: `/Users/Ankit/dev/agentic-memories`

**Status**: Service must be running before starting Annie

**Quick Start**:
```bash
cd ~/dev/agentic-memories
./run_docker.sh
```

**Verify**:
```bash
curl http://localhost:8080/health
# Should return: {"status":"ok",...}
```

## Service Configuration

### Environment Variables

In Annie's `.env`:
```bash
AGENTIC_MEMORIES_URL=http://host.docker.internal:8080
```

**Why `host.docker.internal`?**
- Annie runs in Docker
- agentic-memories runs on host machine
- `host.docker.internal` allows Docker containers to access host services

**Alternative** (if both in same Docker network):
```bash
AGENTIC_MEMORIES_URL=http://agentic-memories:8080
```

## API Endpoints Used

### 1. Store Memories

**Endpoint**: `POST /v1/store`

**Purpose**: Store conversation history as structured memories

**Usage in Annie**:
```python
async def store_conversation(user_id: str, history: list):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{AGENTIC_MEMORIES_URL}/v1/store",
            json={
                "user_id": user_id,
                "history": history
            },
            timeout=30.0
        )
        return response.json()
```

**Request Format**:
```json
{
  "user_id": "user_123",
  "history": [
    {
      "role": "user",
      "content": "I bought 100 shares of AAPL at $150"
    },
    {
      "role": "assistant",
      "content": "That's a great investment!"
    }
  ]
}
```

**Response**:
```json
{
  "memories_created": 3,
  "ids": ["mem_abc", "mem_def", "mem_ghi"],
  "summary": "Stored: 1 episodic, 1 emotional, 1 portfolio."
}
```

### 2. Retrieve Memories (Simple)

**Endpoint**: `GET /v1/retrieve`

**Purpose**: Fast semantic search

**Usage in Annie**:
```python
async def retrieve_memories(user_id: str, query: str, limit: int = 5):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{AGENTIC_MEMORIES_URL}/v1/retrieve",
            params={
                "user_id": user_id,
                "query": query,
                "limit": limit
            },
            timeout=10.0
        )
        return response.json()
```

**Response**:
```json
{
  "results": [
    {
      "id": "mem_xyz",
      "content": "User bought 100 shares of AAPL",
      "score": 0.95,
      "layer": "short-term",
      "metadata": {
        "portfolio": "{\"ticker\":\"AAPL\",\"shares\":100}"
      }
    }
  ],
  "count": 5
}
```

### 3. Retrieve Memories (Persona-Aware)

**Endpoint**: `POST /v1/retrieve`

**Purpose**: Advanced retrieval with persona awareness

**Usage in Annie** (Stock Trader Persona):
```python
async def retrieve_financial_memories(user_id: str, query: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{AGENTIC_MEMORIES_URL}/v1/retrieve",
            json={
                "user_id": user_id,
                "query": query,
                "persona_context": {
                    "forced_persona": "finance"
                },
                "granularity": "episodic",
                "include_narrative": True,
                "limit": 5
            },
            timeout=15.0
        )
        return response.json()
```

**Response**:
```json
{
  "persona": {
    "selected": "finance",
    "confidence": 0.92
  },
  "results": {
    "memories": [...],
    "narrative": "User has been building a tech-focused portfolio...",
    "raw_summary": "...",
    "episodic_summary": "...",
    "arc_summary": "..."
  }
}
```

### 4. Portfolio Summary

**Endpoint**: `GET /v1/portfolio/summary`

**Purpose**: Get structured portfolio data

**Usage in Annie**:
```python
async def get_portfolio(user_id: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{AGENTIC_MEMORIES_URL}/v1/portfolio/summary",
            params={"user_id": user_id},
            timeout=10.0
        )
        return response.json()
```

**Response**:
```json
{
  "user_id": "user_123",
  "holdings": [
    {
      "ticker": "AAPL",
      "shares": 100,
      "avg_price": 175,
      "position": "long",
      "intent": "buy"
    }
  ],
  "counts_by_asset_type": {
    "public_equity": 1
  }
}
```

### 5. Streaming Memory Orchestrator

**Endpoint**: `POST /v1/orchestrator/message`

**Purpose**: Stream messages through adaptive orchestrator

**Usage in Annie**:
```python
async def stream_with_memories(
    conversation_id: str,
    user_id: str,
    role: str,
    content: str
):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{AGENTIC_MEMORIES_URL}/v1/orchestrator/message",
            json={
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "metadata": {"user_id": user_id},
                "flush": True
            },
            timeout=10.0
        )
        return response.json()
```

**Response**:
```json
{
  "injections": [
    {
      "memory_id": "mem_xyz",
      "content": "User holds 100 shares of AAPL",
      "source": "long_term",
      "channel": "inline",
      "score": 0.91
    }
  ]
}
```

## MCP Tool Implementation

### MemoriesMCPTool Class

**Location**: `mcp_server/tools/memories.py`

```python
import httpx
import os

class MemoriesMCPTool:
    def __init__(self, api_url: str = None):
        self.api_url = api_url or os.getenv(
            "AGENTIC_MEMORIES_URL",
            "http://host.docker.internal:8080"
        )
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def store_memory(self, user_id: str, history: list):
        """Store conversation as memories"""
        try:
            response = await self.client.post(
                f"{self.api_url}/v1/store",
                json={"user_id": user_id, "history": history}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {
                "error": f"HTTP {e.response.status_code}",
                "message": str(e)
            }
        except Exception as e:
            return {
                "error": "MEMORY_STORE_FAILED",
                "message": str(e)
            }
    
    async def retrieve_memories(
        self,
        user_id: str,
        query: str,
        persona: str = None,
        granularity: str = "episodic",
        limit: int = 5
    ):
        """Retrieve memories with optional persona awareness"""
        try:
            if persona:
                # Persona-aware retrieval
                response = await self.client.post(
                    f"{self.api_url}/v1/retrieve",
                    json={
                        "user_id": user_id,
                        "query": query,
                        "persona_context": {"forced_persona": persona},
                        "granularity": granularity,
                        "include_narrative": True,
                        "limit": limit
                    }
                )
            else:
                # Simple retrieval
                response = await self.client.get(
                    f"{self.api_url}/v1/retrieve",
                    params={
                        "user_id": user_id,
                        "query": query,
                        "limit": limit
                    }
                )
            
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {
                "error": f"HTTP {e.response.status_code}",
                "message": str(e)
            }
        except Exception as e:
            return {
                "error": "MEMORY_RETRIEVE_FAILED",
                "message": str(e)
            }
    
    async def get_portfolio_summary(self, user_id: str):
        """Get portfolio summary"""
        try:
            response = await self.client.get(
                f"{self.api_url}/v1/portfolio/summary",
                params={"user_id": user_id}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {
                "error": f"HTTP {e.response.status_code}",
                "message": str(e)
            }
        except Exception as e:
            return {
                "error": "PORTFOLIO_FETCH_FAILED",
                "message": str(e)
            }
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
```

## Conversation Flow

### Basic Flow

```
1. User sends message via Telegram
   ↓
2. Backend API receives message
   ↓
3. Backend retrieves relevant memories:
   - Call MCP Server → Memories Tool
   - Memories Tool → agentic-memories API
   ↓
4. Backend constructs LLM context with memories
   ↓
5. LLM generates response
   ↓
6. Backend stores conversation:
   - Call MCP Server → Memories Tool
   - Memories Tool → agentic-memories API
   ↓
7. Response sent to user
```

### With Stock Trader Persona

```
1. User asks: "How is my portfolio doing?"
   ↓
2. Backend detects financial query
   ↓
3. Backend retrieves portfolio data:
   - retrieve_memories(persona="finance")
   - get_portfolio_summary()
   ↓
4. LLM context includes:
   - Portfolio holdings
   - Financial memories
   - Market context
   ↓
5. LLM generates financial analysis
   ↓
6. Stores conversation with portfolio context
```

## Error Handling

### Connection Errors

```python
async def call_agentic_memories_with_retry(
    method: str,
    endpoint: str,
    max_retries: int = 3,
    **kwargs
):
    for attempt in range(max_retries):
        try:
            response = await client.request(
                method,
                f"{AGENTIC_MEMORIES_URL}{endpoint}",
                **kwargs
            )
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            raise
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
            raise
```

### Graceful Degradation

```python
async def retrieve_memories_safe(user_id: str, query: str):
    """Retrieve memories with fallback"""
    try:
        return await retrieve_memories(user_id, query)
    except Exception as e:
        logger.warning(f"Memory retrieval failed: {e}")
        # Continue without memories
        return {"results": [], "count": 0}
```

## Testing Integration

### Health Check

```bash
# Check agentic-memories is accessible from Annie
docker exec -it annie-backend curl http://host.docker.internal:8080/health
```

### Manual Test

```bash
# Store memory
curl -X POST http://localhost:8080/v1/store \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "history": [
      {"role": "user", "content": "I like Python"},
      {"role": "assistant", "content": "Python is great!"}
    ]
  }'

# Retrieve memory
curl "http://localhost:8080/v1/retrieve?user_id=test_user&query=Python&limit=5"
```

### Integration Test

```python
import pytest
from memories_tool import MemoriesMCPTool

@pytest.mark.asyncio
async def test_agentic_memories_integration():
    tool = MemoriesMCPTool()
    
    # Store memory
    store_result = await tool.store_memory(
        user_id="test_user",
        history=[
            {"role": "user", "content": "I like Python"},
            {"role": "assistant", "content": "Python is great!"}
        ]
    )
    assert "memories_created" in store_result
    
    # Retrieve memory
    retrieve_result = await tool.retrieve_memories(
        user_id="test_user",
        query="Python"
    )
    assert "results" in retrieve_result
    assert len(retrieve_result["results"]) > 0
    
    await tool.close()
```

## Monitoring

### Key Metrics

- **Memory Store Latency**: Time to store conversation
- **Memory Retrieve Latency**: Time to retrieve memories
- **Memory Store Success Rate**: % successful stores
- **Memory Retrieve Success Rate**: % successful retrievals
- **Memory Cache Hit Rate**: % cache hits

### Logging

```python
logger.info(
    "Memory stored",
    extra={
        "user_id": user_id,
        "memories_created": result["memories_created"],
        "duration_ms": duration
    }
)

logger.warning(
    "Memory retrieval failed",
    extra={
        "user_id": user_id,
        "query": query,
        "error": str(e)
    }
)
```

## Performance Optimization

### Caching

```python
from functools import lru_cache
import hashlib

class CachedMemoriesTool:
    def __init__(self):
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes
    
    async def retrieve_memories_cached(
        self,
        user_id: str,
        query: str
    ):
        cache_key = f"{user_id}:{query}"
        
        # Check cache
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_ttl:
                return cached_data
        
        # Fetch from API
        result = await self.retrieve_memories(user_id, query)
        
        # Cache result
        self.cache[cache_key] = (result, time.time())
        
        return result
```

### Batch Operations

```python
async def store_multiple_conversations(conversations: list):
    """Store multiple conversations in parallel"""
    tasks = [
        store_memory(conv["user_id"], conv["history"])
        for conv in conversations
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

## Troubleshooting

### Issue: Connection Refused

**Symptom**: `Connection refused to host.docker.internal:8080`

**Solution**:
```bash
# 1. Verify agentic-memories is running
curl http://localhost:8080/health

# 2. Check Docker network
docker network inspect bridge

# 3. Try alternative URL
AGENTIC_MEMORIES_URL=http://172.17.0.1:8080  # Docker bridge IP
```

### Issue: Slow Response Times

**Symptom**: Memory retrieval takes > 5 seconds

**Solution**:
- Check agentic-memories logs for slow queries
- Add caching layer in Annie
- Use simple retrieval instead of persona-aware
- Reduce limit parameter

### Issue: Service Unavailable

**Symptom**: 503 Service Unavailable

**Solution**:
- Check agentic-memories health
- Implement graceful degradation
- Add circuit breaker pattern

## References

- agentic-memories README: `/Users/Ankit/dev/agentic-memories/README.md`
- agentic-memories Integration Guide: `/Users/Ankit/dev/agentic-memories/CHATBOT_INTEGRATION_GUIDE.md`
- Annie Architecture Plan: `../02-architecture/ARCHITECTURE_PLAN.md`

