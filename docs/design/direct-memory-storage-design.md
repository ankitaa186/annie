# Direct Memory Storage - Technical Design

> **Status**: Reviewed
> **Author**: Claude Code
> **Date**: 2025-12-27
> **Reviewed**: 2025-12-27 (BMad Party Mode)
> **Epic**: Performance Optimization

---

## 1. Executive Summary

### Problem Statement

The `store_memory` MCP tool currently takes **60-100+ seconds** to complete because it calls the `/v1/store` endpoint in agentic-memories, which triggers a full LangGraph pipeline with multiple LLM calls (summarization, extraction, categorization, embedding).

This blocks user responses while the LLM waits for the tool to return, causing unacceptable UX:

```
User: "I just bought a house in Seattle"
         ↓
Gemini thinks: "This is important, I should remember this"
         ↓
Gemini calls store_memory → blocks 60-100s waiting for LangGraph
         ↓
User waits 60-100s staring at "🔧 Calling store_memory..."
```

### Solution Overview

1. **Inform LLM** that automatic background memory extraction already runs on all messages
2. **Add fast direct storage API** to agentic-memories for explicit critical memories
3. **Add delete memory API** to agentic-memories for removing incorrect memories
4. **Update Annie's MCP tools** to use the new fast endpoints

### Expected Outcome

| Metric | Before | After |
|--------|--------|-------|
| `store_memory` latency | 60-100s | 1-2s |
| `delete_memory` latency | N/A | <1s |
| User perceived wait time | 60-100s | 2-5s |
| LLM calls for storage | 3-5 | 0 |

---

## 2. Current Architecture

### 2.1 Current Flow: `/v1/store` (Slow Path)

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────────────────────────┐
│   Annie     │     │  agentic-memories │     │         LangGraph Pipeline          │
│  (Gemini)   │     │    /v1/store      │     │                                     │
└──────┬──────┘     └────────┬─────────┘     └──────────────────┬──────────────────┘
       │                     │                                   │
       │  POST /v1/store     │                                   │
       │  {history: [...]}   │                                   │
       │────────────────────>│                                   │
       │                     │                                   │
       │                     │  1. node_extract_memories         │
       │                     │     (LLM call ~15-30s)            │
       │                     │──────────────────────────────────>│
       │                     │                                   │
       │                     │  2. node_classify_memories        │
       │                     │     (LLM call ~10-20s)            │
       │                     │──────────────────────────────────>│
       │                     │                                   │
       │                     │  3. node_generate_embeddings      │
       │                     │     (embedding call ~2-5s)        │
       │                     │──────────────────────────────────>│
       │                     │                                   │
       │                     │  4. node_store_chromadb           │
       │                     │     (~1s)                         │
       │                     │──────────────────────────────────>│
       │                     │                                   │
       │                     │  5. node_store_episodic           │
       │                     │     (~1s)                         │
       │                     │──────────────────────────────────>│
       │                     │                                   │
       │                     │  6. node_store_profile            │
       │                     │     (LLM call ~10-20s)            │
       │                     │──────────────────────────────────>│
       │                     │                                   │
       │  Response           │                                   │
       │  (after 60-100s)    │                                   │
       │<────────────────────│                                   │
       │                     │                                   │
```

**Total Time**: 60-100+ seconds

### 2.2 Background Memory Extraction (Already Running)

Annie already has automatic background memory extraction:

1. **Memory Orchestrator**: Runs on every message via `/v1/orchestrator/message`
2. **Streaming Injection**: Memories are extracted and injected during conversation
3. **Automatic Extraction**: No explicit `store_memory` call needed for routine info

This means the LLM only needs to call `store_memory` for **critical explicit memories** that the user specifically asks to be remembered.

---

## 3. Proposed Architecture

### 3.1 New Flow: `/v1/memories/direct` (Fast Path)

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────────────────────┐
│   Annie     │     │  agentic-memories │     │            Storage              │
│  (Gemini)   │     │ /v1/memories/    │     │  ChromaDB + Typed Tables (TS)   │
└──────┬──────┘     └────────┬─────────┘     └────────────────┬────────────────┘
       │                     │                                │
       │  POST /v1/memories/ │                                │
       │  direct             │                                │
       │  {content, tags,    │                                │
       │   event_timestamp?, │                                │
       │   emotional_state?, │                                │
       │   skill_name?}      │                                │
       │────────────────────>│                                │
       │                     │                                │
       │                     │  1. Generate embedding         │
       │                     │     (OpenAI ~500ms)            │
       │                     │───────────────────────────────>│
       │                     │                                │
       │                     │  2. Store in ChromaDB (always) │
       │                     │     + stored_in_* flags        │
       │                     │     (~100ms)                   │
       │                     │───────────────────────────────>│
       │                     │                                │
       │                     │  3. Conditional typed tables:  │
       │                     │     - episodic_memories        │
       │                     │     - emotional_memories       │
       │                     │     - procedural_memories      │
       │                     │     (~100ms)                   │
       │                     │───────────────────────────────>│
       │                     │                                │
       │  Response           │                                │
       │  (after 1-2s)       │                                │
       │<────────────────────│                                │
       │                     │                                │
```

**Storage Routing Logic**:
- **Always**: ChromaDB (with stored_in_* metadata flags)
- **If event_timestamp provided**: → episodic_memories
- **If emotional_state provided**: → emotional_memories
- **If skill_name provided**: → procedural_memories

**Total Time**: 1-2 seconds

### 3.2 Delete Flow: `DELETE /v1/memories/{id}`

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────────────────────┐
│   Annie     │     │  agentic-memories │     │            Storage              │
│  (Gemini)   │     │ /v1/memories/{id}│     │  ChromaDB + Typed Tables (TS)   │
└──────┬──────┘     └────────┬─────────┘     └────────────────┬────────────────┘
       │                     │                                │
       │  DELETE /v1/        │                                │
       │  memories/{id}      │                                │
       │────────────────────>│                                │
       │                     │                                │
       │                     │  1. Get metadata from ChromaDB │
       │                     │     (check stored_in_* flags)  │
       │                     │     (~50ms)                    │
       │                     │───────────────────────────────>│
       │                     │                                │
       │                     │  2. Delete from ChromaDB       │
       │                     │     (~50ms)                    │
       │                     │───────────────────────────────>│
       │                     │                                │
       │                     │  3. Delete from typed tables   │
       │                     │     (only tables with flags)   │
       │                     │     (~50ms)                    │
       │                     │───────────────────────────────>│
       │                     │                                │
       │  Response           │                                │
       │  (after <500ms)     │                                │
       │<────────────────────│                                │
       │                     │                                │
```

**Delete Logic**:
1. Get metadata from ChromaDB to check stored_in_* flags
2. Delete from ChromaDB (always)
3. Delete from typed tables based on flags (no need to query all tables)

**Total Time**: <500ms

---

## 4. API Contract (Annie ↔ agentic-memories)

### 4.0 Contract Overview

| Aspect | Specification |
|--------|---------------|
| **Base URL** | `http://host.docker.internal:8080` (Docker) or `AGENTIC_MEMORIES_URL` env var |
| **API Version** | `/v1/` prefix on all endpoints |
| **Content-Type** | `application/json` (request and response) |
| **Authentication** | None (internal service communication) |
| **Timeout (Annie client)** | 10 seconds |
| **Timeout (agentic-memories)** | No explicit timeout (embedding call ~500ms, storage ~200ms) |
| **Idempotency** | Not guaranteed — duplicate calls create duplicate memories |

### 4.1 POST `/v1/memories/direct`

Store a pre-formatted memory directly without LLM extraction.

#### Request

**Headers:**
```
Content-Type: application/json
```

**Body Schema:**
```typescript
{
  // REQUIRED
  user_id: string;           // User identifier (e.g., "YOUR_USER_ID")
  content: string;           // Memory content, max 5000 chars

  // GENERAL FIELDS (always stored in ChromaDB)
  layer?: "short-term" | "semantic" | "long-term";  // Default: "semantic"
  type?: "explicit" | "implicit";                    // Default: "explicit"
  importance?: number;       // 0.0-1.0, Default: 0.8
  confidence?: number;       // 0.0-1.0, Default: 0.9
  persona_tags?: string[];   // Max 10 tags, e.g., ["health", "preference"]
  metadata?: {
    source?: string;         // Default: "llm_explicit"
    conversation_id?: string;
    trigger?: string;        // What triggered this storage
  }

  // OPTIONAL EPISODIC FIELDS → triggers episodic_memories write
  event_timestamp?: datetime;  // When the event occurred
  location?: string;           // Where it happened
  participants?: string[];     // Who was involved

  // OPTIONAL EMOTIONAL FIELDS → triggers emotional_memories write
  emotional_state?: string;    // e.g., "happy", "anxious", "excited"
  valence?: number;            // -1.0 (negative) to 1.0 (positive)
  arousal?: number;            // 0.0 (calm) to 1.0 (intense)

  // OPTIONAL PROCEDURAL FIELDS → triggers procedural_memories write
  skill_name?: string;         // Name of the skill/procedure
  proficiency_level?: string;  // e.g., "beginner", "intermediate", "expert"
}
```

**Example Request (basic - ChromaDB only):**
```json
{
  "user_id": "YOUR_USER_ID",
  "content": "User is allergic to shellfish - confirmed severe reaction, carries EpiPen",
  "layer": "semantic",
  "type": "explicit",
  "importance": 0.95,
  "confidence": 0.98,
  "persona_tags": ["health", "allergy", "critical", "medical"],
  "metadata": {
    "source": "llm_explicit",
    "conversation_id": "conv_abc123",
    "trigger": "User explicitly stated allergy during health discussion"
  }
}
```

**Example Request (with episodic fields - also writes to episodic_memories):**
```json
{
  "user_id": "YOUR_USER_ID",
  "content": "User bought a house in Seattle",
  "importance": 0.9,
  "persona_tags": ["life_event", "housing"],
  "event_timestamp": "2025-12-15T10:30:00Z",
  "location": "Seattle, WA",
  "participants": ["spouse"]
}
```

**Example Request (with emotional fields - also writes to emotional_memories):**
```json
{
  "user_id": "YOUR_USER_ID",
  "content": "User mentioned feeling anxious about upcoming job interview",
  "importance": 0.7,
  "emotional_state": "anxious",
  "valence": -0.3,
  "arousal": 0.7
}
```

#### Response

**HTTP Status Codes:**

| Status | Meaning |
|--------|---------|
| 200 | Success — memory stored |
| 400 | Validation error — invalid request body |
| 500 | Server error — storage or embedding failure |

**Success Response Schema (200):**
```typescript
{
  status: "success";
  memory_id: string;         // UUID
  message: "Memory stored successfully";
  storage: {
    chromadb: boolean;       // Always true on success
    episodic: boolean;       // true if stored in episodic_memories (when event_timestamp provided)
    emotional: boolean;      // true if stored in emotional_memories (when emotional_state provided)
    procedural: boolean;     // true if stored in procedural_memories (when skill_name provided)
  }
}
```

**Example Success Response (basic):**
```json
{
  "status": "success",
  "memory_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "message": "Memory stored successfully",
  "storage": {
    "chromadb": true,
    "episodic": false,
    "emotional": false,
    "procedural": false
  }
}
```

**Example Success Response (with episodic storage):**
```json
{
  "status": "success",
  "memory_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "message": "Memory stored successfully",
  "storage": {
    "chromadb": true,
    "episodic": true,
    "emotional": false,
    "procedural": false
  }
}
```

**Error Response Schema (400/500):**
```typescript
{
  status: "error";
  message: string;           // Human-readable error description
  error_code: "VALIDATION_ERROR" | "EMBEDDING_ERROR" | "STORAGE_ERROR" | "INTERNAL_ERROR";
}
```

**Example Error Response:**
```json
{
  "status": "error",
  "message": "Missing required field: content",
  "error_code": "VALIDATION_ERROR"
}
```

**Error Codes:**

| Code | HTTP Status | Meaning | Annie Action |
|------|-------------|---------|--------------|
| `VALIDATION_ERROR` | 400 | Missing/invalid fields | Fix request, retry |
| `EMBEDDING_ERROR` | 500 | OpenAI embedding failed | Retry with backoff |
| `STORAGE_ERROR` | 500 | ChromaDB/TimescaleDB failed | Retry with backoff |
| `INTERNAL_ERROR` | 500 | Unexpected server error | Log, don't retry |

---

### 4.2 DELETE `/v1/memories/{memory_id}`

Delete a specific memory by ID.

#### Request

**URL Parameters:**
```
memory_id: string (UUID) — Required, path parameter
```

**Query Parameters:**
```
user_id: string — Required, for authorization
```

**Example:**
```
DELETE /v1/memories/a1b2c3d4-e5f6-7890-abcd-ef1234567890?user_id=YOUR_USER_ID
```

#### Response

**HTTP Status Codes:**

| Status | Meaning |
|--------|---------|
| 200 | Success — memory deleted (or not found) |
| 400 | Missing user_id query parameter |
| 403 | Unauthorized — memory belongs to different user |
| 500 | Server error — deletion failed |

**Success Response Schema (200):**
```typescript
{
  status: "success";
  deleted: boolean;          // true if memory was found and deleted
  memory_id: string;         // Echo back the requested ID
  storage: {
    chromadb: boolean;       // true if deleted from ChromaDB
    episodic: boolean;       // true if deleted from episodic_memories
    emotional: boolean;      // true if deleted from emotional_memories
    procedural: boolean;     // true if deleted from procedural_memories
  }
}
```

**Example Success Response:**
```json
{
  "status": "success",
  "deleted": true,
  "memory_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "storage": {
    "chromadb": true,
    "episodic": true,
    "emotional": false,
    "procedural": false
  }
}
```

**Not Found Response Schema (200 with deleted=false):**
```typescript
{
  status: "error";
  deleted: false;
  memory_id: string;
  message: "Memory not found";
}
```

**Example Not Found Response:**
```json
{
  "status": "error",
  "deleted": false,
  "memory_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "message": "Memory not found"
}
```

**Unauthorized Response Schema (403):**
```typescript
{
  status: "error";
  deleted: false;
  memory_id: string;
  message: "Unauthorized: memory belongs to different user";
}
```

**Example Unauthorized Response:**
```json
{
  "status": "error",
  "deleted": false,
  "memory_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "message": "Unauthorized: memory belongs to different user"
}
```

**Error Response Schema (500):**
```typescript
{
  status: "error";
  deleted: false;
  memory_id: string;
  message: string;           // Error description
}
```

**Example Error Response:**
```json
{
  "status": "error",
  "deleted": false,
  "memory_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "message": "Failed to delete from TimescaleDB: connection timeout"
}
```

---

### 4.3 Contract Guarantees

| Guarantee | Store (`POST`) | Delete (`DELETE`) |
|-----------|----------------|-------------------|
| **Atomicity** | Best-effort (partial success OK) | All-or-nothing (both storages required) |
| **Consistency** | Memory retrievable immediately after 200 | Memory not retrievable after 200 |
| **Durability** | Persisted to disk (ChromaDB + TimescaleDB) | Removed from both storages |
| **Latency p95** | < 3 seconds | < 1 second |

### 4.4 Annie MCP Tool → API Mapping

| Annie Tool | HTTP Method | Endpoint | Timeout |
|------------|-------------|----------|---------|
| `store_memory` | POST | `/v1/memories/direct` | 10s |
| `delete_memory` | DELETE | `/v1/memories/{id}?user_id={uid}` | 10s |
| `retrieve_memories` | GET/POST | `/v1/retrieve` (existing) | 10s |

---

## 5. Detailed Implementation

### 5.1 POST `/v1/memories/direct` Implementation

**Location**: `agentic-memories/src/app.py`

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime

class DirectMemoryRequest(BaseModel):
    # Required
    user_id: str
    content: str

    # General fields (always stored in ChromaDB)
    layer: Literal["short-term", "semantic", "long-term"] = "semantic"
    type: Literal["explicit", "implicit"] = "explicit"
    importance: float = Field(default=0.8, ge=0.0, le=1.0)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    persona_tags: List[str] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None

    # Optional episodic fields → triggers episodic_memories write
    event_timestamp: Optional[datetime] = None
    location: Optional[str] = None
    participants: Optional[List[str]] = None

    # Optional emotional fields → triggers emotional_memories write
    emotional_state: Optional[str] = None
    valence: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    arousal: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    # Optional procedural fields → triggers procedural_memories write
    skill_name: Optional[str] = None
    proficiency_level: Optional[str] = None

class DirectMemoryResponse(BaseModel):
    status: str
    memory_id: Optional[str] = None
    message: str
    storage: Optional[Dict[str, bool]] = None

@app.post("/v1/memories/direct", response_model=DirectMemoryResponse)
def store_memory_direct(body: DirectMemoryRequest) -> DirectMemoryResponse:
    """
    Store a pre-formatted memory directly without LLM extraction.

    This endpoint is designed for LLM-initiated storage of critical explicit
    memories that bypass the full ingestion pipeline.

    Storage Routing Logic:
    1. Always store in ChromaDB (vector search)
    2. Conditionally store in typed tables based on optional fields:
       - event_timestamp → episodic_memories
       - emotional_state → emotional_memories
       - skill_name → procedural_memories
    """
    import uuid
    from datetime import datetime, timezone

    start_time = time.time()
    memory_id = str(uuid.uuid4())

    # Track which typed tables will be written to
    stored_in_episodic = bool(body.event_timestamp)
    stored_in_emotional = bool(body.emotional_state)
    stored_in_procedural = bool(body.skill_name)

    try:
        # 1. Generate embedding
        from src.dependencies.embeddings import get_embeddings
        embeddings = get_embeddings([body.content])
        if not embeddings or not embeddings[0]:
            return DirectMemoryResponse(
                status="error",
                message="Failed to generate embedding",
                storage=None
            )

        # 2. Store in ChromaDB (always)
        from src.dependencies.chroma import get_chroma_client
        chroma = get_chroma_client()
        collection = chroma.get_or_create_collection("memories")

        # Include stored_in_* flags for efficient deletion
        chroma_metadata = {
            "user_id": body.user_id,
            "layer": body.layer,
            "type": body.type,
            "importance": body.importance,
            "confidence": body.confidence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": (body.metadata or {}).get("source", "llm_explicit"),
            # Tracking flags for deletion
            "stored_in_episodic": stored_in_episodic,
            "stored_in_emotional": stored_in_emotional,
            "stored_in_procedural": stored_in_procedural,
            **{f"tag_{i}": tag for i, tag in enumerate(body.persona_tags[:10])}
        }

        collection.add(
            ids=[memory_id],
            embeddings=[embeddings[0]],
            documents=[body.content],
            metadatas=[chroma_metadata]
        )

        # 3. Conditional typed table storage
        from src.dependencies.timescale import get_timescale_conn, release_timescale_conn
        import json

        conn = get_timescale_conn()
        episodic_stored = False
        emotional_stored = False
        procedural_stored = False

        if conn:
            try:
                with conn.cursor() as cur:
                    # Store in episodic_memories if event_timestamp provided
                    if body.event_timestamp:
                        cur.execute("""
                            INSERT INTO episodic_memories (
                                id, user_id, event_timestamp, event_type, content,
                                location, participants, importance_score, tags, metadata
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            memory_id,
                            body.user_id,
                            body.event_timestamp,
                            "explicit_memory",
                            body.content,
                            body.location,
                            body.participants,
                            body.importance,
                            body.persona_tags if body.persona_tags else None,
                            json.dumps(body.metadata) if body.metadata else None
                        ))
                        episodic_stored = True

                    # Store in emotional_memories if emotional_state provided
                    if body.emotional_state:
                        cur.execute("""
                            INSERT INTO emotional_memories (
                                id, user_id, emotional_state, valence, arousal,
                                content, importance_score, created_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            memory_id,
                            body.user_id,
                            body.emotional_state,
                            body.valence,
                            body.arousal,
                            body.content,
                            body.importance,
                            datetime.now(timezone.utc)
                        ))
                        emotional_stored = True

                    # Store in procedural_memories if skill_name provided
                    if body.skill_name:
                        cur.execute("""
                            INSERT INTO procedural_memories (
                                id, user_id, skill_name, proficiency_level,
                                content, importance_score, created_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (
                            memory_id,
                            body.user_id,
                            body.skill_name,
                            body.proficiency_level,
                            body.content,
                            body.importance,
                            datetime.now(timezone.utc)
                        ))
                        procedural_stored = True

                conn.commit()
            finally:
                release_timescale_conn(conn)

        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "[memories.direct] stored user_id=%s memory_id=%s duration_ms=%s",
            body.user_id, memory_id, duration_ms
        )

        return DirectMemoryResponse(
            status="success",
            memory_id=memory_id,
            message="Memory stored successfully",
            storage={
                "chromadb": True,
                "episodic": episodic_stored,
                "emotional": emotional_stored,
                "procedural": procedural_stored
            }
        )

    except Exception as e:
        logger.error("[memories.direct] error user_id=%s error=%s", body.user_id, e)
        return DirectMemoryResponse(
            status="error",
            message=f"Storage failed: {str(e)}",
            storage=None
        )
```

---

### 5.2 DELETE `/v1/memories/{memory_id}` Implementation

Delete a specific memory by ID.

#### Request

```
DELETE /v1/memories/{memory_id}?user_id={user_id}
```

Query Parameters:
- `memory_id` (path, required): UUID of the memory to delete
- `user_id` (query, required): User ID for authorization

#### Response

**Success (200)**:
```json
{
  "status": "success",
  "deleted": true,
  "memory_id": "uuid-string",
  "storage": {
    "chromadb": true,
    "timescale": true
  }
}
```

**Not Found (404)**:
```json
{
  "status": "error",
  "deleted": false,
  "memory_id": "uuid-string",
  "message": "Memory not found"
}
```

#### Implementation Details

**Location**: `agentic-memories/src/app.py`

```python
class DeleteMemoryResponse(BaseModel):
    status: str
    deleted: bool
    memory_id: str
    message: Optional[str] = None
    storage: Optional[Dict[str, bool]] = None

@app.delete("/v1/memories/{memory_id}", response_model=DeleteMemoryResponse)
def delete_memory(
    memory_id: str,
    user_id: str = Query(..., description="User ID for authorization")
) -> DeleteMemoryResponse:
    """
    Delete a specific memory by ID.

    Uses metadata flags stored in ChromaDB to efficiently delete from
    only the relevant typed tables (no need to query all tables).

    Logic:
    1. Get metadata from ChromaDB to determine where memory exists
    2. Verify ownership
    3. Delete from ChromaDB (always)
    4. Delete from typed tables based on stored_in_* flags
    """
    start_time = time.time()

    chromadb_deleted = False
    episodic_deleted = False
    emotional_deleted = False
    procedural_deleted = False

    try:
        # 1. Get metadata from ChromaDB to determine where memory exists
        from src.dependencies.chroma import get_chroma_client
        chroma = get_chroma_client()
        collection = chroma.get_or_create_collection("memories")

        result = collection.get(ids=[memory_id], include=["metadatas"])

        if not result or not result["metadatas"] or not result["metadatas"][0]:
            return DeleteMemoryResponse(
                status="error",
                deleted=False,
                memory_id=memory_id,
                message="Memory not found"
            )

        metadata = result["metadatas"][0]

        # 2. Verify ownership before deletion
        stored_user_id = metadata.get("user_id")
        if stored_user_id != user_id:
            return DeleteMemoryResponse(
                status="error",
                deleted=False,
                memory_id=memory_id,
                message="Unauthorized: memory belongs to different user"
            )

        # Extract storage flags
        stored_in_episodic = metadata.get("stored_in_episodic", False)
        stored_in_emotional = metadata.get("stored_in_emotional", False)
        stored_in_procedural = metadata.get("stored_in_procedural", False)

        # 3. Delete from ChromaDB (always)
        collection.delete(ids=[memory_id])
        chromadb_deleted = True

        # 4. Delete from typed tables based on stored flags
        from src.dependencies.timescale import get_timescale_conn, release_timescale_conn

        conn = get_timescale_conn()
        if conn:
            try:
                with conn.cursor() as cur:
                    if stored_in_episodic:
                        cur.execute(
                            "DELETE FROM episodic_memories WHERE id = %s AND user_id = %s",
                            (memory_id, user_id)
                        )
                        episodic_deleted = cur.rowcount > 0

                    if stored_in_emotional:
                        cur.execute(
                            "DELETE FROM emotional_memories WHERE id = %s AND user_id = %s",
                            (memory_id, user_id)
                        )
                        emotional_deleted = cur.rowcount > 0

                    if stored_in_procedural:
                        cur.execute(
                            "DELETE FROM procedural_memories WHERE id = %s AND user_id = %s",
                            (memory_id, user_id)
                        )
                        procedural_deleted = cur.rowcount > 0

                conn.commit()
            finally:
                release_timescale_conn(conn)

        duration_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "[memories.delete] user_id=%s memory_id=%s chromadb=%s episodic=%s emotional=%s procedural=%s duration_ms=%s",
            user_id, memory_id, chromadb_deleted, episodic_deleted, emotional_deleted, procedural_deleted, duration_ms
        )

        return DeleteMemoryResponse(
            status="success",
            deleted=True,
            memory_id=memory_id,
            storage={
                "chromadb": chromadb_deleted,
                "episodic": episodic_deleted,
                "emotional": emotional_deleted,
                "procedural": procedural_deleted
            }
        )

    except Exception as e:
        logger.error("[memories.delete] error memory_id=%s error=%s", memory_id, e)
        return DeleteMemoryResponse(
            status="error",
            deleted=False,
            memory_id=memory_id,
            message=f"Delete failed: {str(e)}"
        )
```

---

## 6. Annie MCP Tool Changes

### 6.1 Updated `store_memory` Tool

**Location**: `annie/mcp_server/tools.py`

#### Tool Schema Changes

```python
store_memory_tool = {
    "name": "store_memory",
    "description": """Store a critical explicit memory that the user specifically asked you to remember.

⚠️ IMPORTANT: All conversations are automatically processed for memory extraction in the background.
You do NOT need to call this tool for routine information.

✅ ONLY use this tool for:
- User explicitly says "Remember that..." or "Don't forget..."
- Critical health/safety information (allergies, medications, emergency contacts)
- Strong explicit preferences the user emphasizes
- Important constraints or requirements

❌ DO NOT use this tool for:
- General conversation topics (auto-extracted)
- Information shared casually (auto-extracted)
- Things you want to reference later (use retrieve_memories instead)
- Routine updates or status information

Examples of when to use:
- "Remember I'm allergic to shellfish" → YES, use store_memory
- "My risk tolerance is very conservative, please remember that" → YES
- "I bought some NVDA stock today" → NO, auto-extracted
- "I had a meeting with John" → NO, auto-extracted
""",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "content": {
                "type": "string",
                "description": "The memory to store - clear, concise statement. Example: 'User is allergic to shellfish' or 'User prefers conservative investment strategies'"
            },
            "importance": {
                "type": "number",
                "description": "How important is this memory? 0.0 (low) to 1.0 (critical). Default: 0.8",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.8
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Categories for this memory. Options: health, preference, finance, personal, goal, constraint, relationship"
            }
        },
        "required": ["user_id", "content"]
    },
    "handler": store_memory_tool_handler
}
```

#### Handler Changes

```python
async def store_memory_tool_handler(
    user_id: str,
    content: str,
    importance: float = 0.8,
    tags: List[str] = None
) -> Dict[str, Any]:
    """
    Store an explicit critical memory via direct storage API.

    This bypasses the full LangGraph pipeline for fast storage (~1-2s).
    """
    start_time = time.time()

    # Get agentic-memories URL
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Build request payload
    payload = {
        "user_id": user_id,
        "content": content,
        "layer": "semantic",
        "type": "explicit",
        "importance": importance,
        "confidence": 0.95,  # High confidence for explicit memories
        "persona_tags": tags or [],
        "metadata": {
            "source": "llm_explicit",
            "tool": "store_memory"
        }
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:  # 10s timeout (was 180s)
            logger.info(
                "Storing explicit memory via direct API",
                extra={
                    "user_id": user_id,
                    "content_length": len(content),
                    "importance": importance,
                    "tags": tags
                }
            )

            response = await client.post(
                f"{memories_url}/v1/memories/direct",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    "Memory stored successfully via direct API",
                    extra={
                        "user_id": user_id,
                        "memory_id": result.get("memory_id"),
                        "duration_ms": duration_ms
                    }
                )
                return {
                    "status": "success",
                    "memory_id": result.get("memory_id"),
                    "message": "Memory stored successfully"
                }
            else:
                error_msg = response.text
                logger.error(
                    "Direct memory storage failed",
                    extra={
                        "user_id": user_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )
                return {
                    "status": "error",
                    "message": f"Storage failed: {error_msg}"
                }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Direct memory storage timeout",
            extra={"user_id": user_id, "duration_ms": duration_ms}
        )
        return {
            "status": "error",
            "message": "Storage timeout - please try again"
        }

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Unexpected error in direct memory storage",
            extra={"user_id": user_id, "error": str(e), "duration_ms": duration_ms}
        )
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}"
        }
```

---

### 6.2 New `delete_memory` Tool

**Location**: `annie/mcp_server/tools.py`

```python
async def delete_memory_tool_handler(
    user_id: str,
    memory_id: str,
    reason: str = None
) -> Dict[str, Any]:
    """
    Delete a specific memory by ID.

    Use when user indicates a memory is incorrect or wants it removed.
    """
    start_time = time.time()

    # Get agentic-memories URL
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            logger.info(
                "Deleting memory",
                extra={
                    "user_id": user_id,
                    "memory_id": memory_id,
                    "reason": reason
                }
            )

            response = await client.delete(
                f"{memories_url}/v1/memories/{memory_id}",
                params={"user_id": user_id}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    "Memory deleted successfully",
                    extra={
                        "user_id": user_id,
                        "memory_id": memory_id,
                        "duration_ms": duration_ms
                    }
                )
                return {
                    "status": "success",
                    "deleted": True,
                    "memory_id": memory_id,
                    "message": "Memory deleted successfully"
                }
            elif response.status_code == 404:
                return {
                    "status": "error",
                    "deleted": False,
                    "memory_id": memory_id,
                    "message": "Memory not found"
                }
            else:
                error_msg = response.text
                logger.error(
                    "Memory deletion failed",
                    extra={
                        "user_id": user_id,
                        "memory_id": memory_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )
                return {
                    "status": "error",
                    "deleted": False,
                    "memory_id": memory_id,
                    "message": f"Delete failed: {error_msg}"
                }

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Unexpected error deleting memory",
            extra={
                "user_id": user_id,
                "memory_id": memory_id,
                "error": str(e),
                "duration_ms": duration_ms
            }
        )
        return {
            "status": "error",
            "deleted": False,
            "memory_id": memory_id,
            "message": f"Unexpected error: {str(e)}"
        }


delete_memory_tool = {
    "name": "delete_memory",
    "description": """Delete a memory that is incorrect or that the user wants removed.

Use this tool when:
- User says a memory is wrong: "That's not right, I don't have a cat"
- User explicitly asks to forget: "Forget that I mentioned X"
- Correcting outdated information: "I no longer work at Company Y"
- User requests removal: "Delete that memory about..."

⚠️ IMPORTANT:
- Always confirm with the user before deleting
- Get the memory_id from retrieve_memories results first
- Explain what memory will be deleted before proceeding

Example flow:
1. User: "That's wrong, I'm not allergic to peanuts"
2. You: Call retrieve_memories to find the incorrect memory
3. You: "I found a memory saying you're allergic to peanuts (ID: abc123). Should I delete it?"
4. User: "Yes, delete it"
5. You: Call delete_memory with the memory_id
""",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "memory_id": {
                "type": "string",
                "description": "The memory ID to delete (from retrieve_memories results)"
            },
            "reason": {
                "type": "string",
                "description": "Why this memory is being deleted (for audit trail)"
            }
        },
        "required": ["user_id", "memory_id"]
    },
    "handler": delete_memory_tool_handler
}
```

---

## 7. System Prompt Changes

### 7.1 New Memory Instructions Section

**Location**: `annie/backend/api/prompts.py`

Add after `TOOL_USAGE_INSTRUCTIONS`:

```python
MEMORY_SYSTEM_INSTRUCTIONS = """
## MEMORY SYSTEM

### Automatic Background Extraction
All conversations are automatically processed for memory extraction in the background.
You do NOT need to manually store routine information - it's handled automatically.

The background system extracts:
- Topics discussed
- Preferences mentioned
- Decisions made
- Important facts shared
- Emotional context

### When to Use store_memory
ONLY use store_memory for **critical explicit memories** that require immediate,
guaranteed storage:

✅ USE store_memory for:
- "Remember that I'm allergic to shellfish" → Critical health info
- "Don't forget my risk tolerance is very conservative" → Emphasized preference
- "Always remind me about my medications" → Safety-critical
- Explicit user requests to remember something specific

❌ DO NOT use store_memory for:
- General conversation topics → Auto-extracted
- Casual mentions of preferences → Auto-extracted
- Status updates ("I bought NVDA today") → Auto-extracted
- Things you want to reference later → Use retrieve_memories

### When to Use delete_memory
Use delete_memory when the user indicates a memory is incorrect:

- "That's wrong, I'm not allergic to peanuts"
- "Forget that I mentioned working at X"
- "Delete that old information about..."

**Always confirm before deleting:**
1. Use retrieve_memories to find the specific memory
2. Show the user what will be deleted
3. Get explicit confirmation
4. Then call delete_memory

### When to Use retrieve_memories
Use retrieve_memories to get context for the current conversation:

- Before answering questions about user preferences
- When user asks "what do you know about me"
- To personalize recommendations
- To reference past decisions

Retrieval is fast (<2s) and should be used liberally.
"""
```

### 7.2 Update `build_system_prompt()`

```python
def build_system_prompt(
    user_id: Optional[str] = None,
    platform: str = "api",
    include_tool_instructions: bool = True,
    profile: Optional[Dict[str, Any]] = None,
    portfolio: Optional[Dict[str, Any]] = None,
    triggers: Optional[list] = None,
    proactive_context: Optional[Dict[str, Any]] = None
) -> str:
    prompt_parts = [BASE_SYSTEM_PROMPT]

    # Add memory system instructions (NEW)
    prompt_parts.append("\n\n" + MEMORY_SYSTEM_INSTRUCTIONS)

    # Add proactive capabilities section
    prompt_parts.append("\n\n" + PROACTIVE_CAPABILITIES_SECTION)

    # ... rest of function unchanged
```

---

## 8. Testing Plan

### 8.1 Unit Tests

#### agentic-memories

```python
# tests/test_direct_memory.py

def test_store_memory_direct_success():
    """Test successful direct memory storage."""
    response = client.post("/v1/memories/direct", json={
        "user_id": "test-user",
        "content": "User is allergic to shellfish",
        "importance": 0.9,
        "persona_tags": ["health", "allergy"]
    })
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["memory_id"] is not None

def test_store_memory_direct_validation():
    """Test validation of required fields."""
    response = client.post("/v1/memories/direct", json={
        "user_id": "test-user"
        # missing content
    })
    assert response.status_code == 422

def test_delete_memory_success():
    """Test successful memory deletion."""
    # First create a memory
    create_resp = client.post("/v1/memories/direct", json={
        "user_id": "test-user",
        "content": "Test memory"
    })
    memory_id = create_resp.json()["memory_id"]

    # Then delete it
    delete_resp = client.delete(
        f"/v1/memories/{memory_id}",
        params={"user_id": "test-user"}
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True

def test_delete_memory_not_found():
    """Test deletion of non-existent memory."""
    response = client.delete(
        "/v1/memories/non-existent-id",
        params={"user_id": "test-user"}
    )
    assert response.status_code == 200
    assert response.json()["deleted"] is False

def test_delete_memory_wrong_user():
    """Test that users can only delete their own memories."""
    # Create memory for user1
    create_resp = client.post("/v1/memories/direct", json={
        "user_id": "user1",
        "content": "User1's memory"
    })
    memory_id = create_resp.json()["memory_id"]

    # Try to delete as user2
    delete_resp = client.delete(
        f"/v1/memories/{memory_id}",
        params={"user_id": "user2"}
    )
    assert delete_resp.json()["status"] == "error"
    assert "Unauthorized" in delete_resp.json()["message"]
```

#### annie MCP Server

```python
# tests/test_memory_tools.py

@pytest.mark.asyncio
async def test_store_memory_tool_success():
    """Test store_memory tool with direct API."""
    with patch('httpx.AsyncClient.post') as mock_post:
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {"status": "success", "memory_id": "test-123"}
        )

        result = await store_memory_tool_handler(
            user_id="test-user",
            content="User is allergic to shellfish",
            importance=0.9,
            tags=["health"]
        )

        assert result["status"] == "success"
        assert result["memory_id"] == "test-123"

@pytest.mark.asyncio
async def test_store_memory_tool_timeout():
    """Test store_memory tool handles timeout gracefully."""
    with patch('httpx.AsyncClient.post') as mock_post:
        mock_post.side_effect = httpx.TimeoutException("timeout")

        result = await store_memory_tool_handler(
            user_id="test-user",
            content="Test content"
        )

        assert result["status"] == "error"
        assert "timeout" in result["message"].lower()

@pytest.mark.asyncio
async def test_delete_memory_tool_success():
    """Test delete_memory tool."""
    with patch('httpx.AsyncClient.delete') as mock_delete:
        mock_delete.return_value = Mock(
            status_code=200,
            json=lambda: {"status": "success", "deleted": True, "memory_id": "test-123"}
        )

        result = await delete_memory_tool_handler(
            user_id="test-user",
            memory_id="test-123",
            reason="User said this was incorrect"
        )

        assert result["status"] == "success"
        assert result["deleted"] is True
```

### 8.2 Integration Tests

```python
# tests/e2e/test_memory_flow.py

@pytest.mark.asyncio
async def test_store_retrieve_delete_flow():
    """Test full memory lifecycle."""
    user_id = "e2e-test-user"

    # 1. Store a memory
    store_result = await store_memory_tool_handler(
        user_id=user_id,
        content="E2E test: User prefers morning meetings",
        importance=0.8,
        tags=["preference", "schedule"]
    )
    assert store_result["status"] == "success"
    memory_id = store_result["memory_id"]

    # 2. Retrieve and verify
    retrieve_result = await retrieve_memories_tool_handler(
        user_id=user_id,
        query="meeting preferences"
    )
    assert any(memory_id in str(m) for m in retrieve_result.get("memories", []))

    # 3. Delete the memory
    delete_result = await delete_memory_tool_handler(
        user_id=user_id,
        memory_id=memory_id,
        reason="E2E test cleanup"
    )
    assert delete_result["deleted"] is True

    # 4. Verify deletion
    retrieve_after = await retrieve_memories_tool_handler(
        user_id=user_id,
        query="meeting preferences"
    )
    assert not any(memory_id in str(m) for m in retrieve_after.get("memories", []))
```

### 8.3 Performance Tests

```python
# tests/performance/test_memory_latency.py

@pytest.mark.asyncio
async def test_direct_storage_latency():
    """Verify direct storage completes in <3s."""
    import time

    start = time.time()
    result = await store_memory_tool_handler(
        user_id="perf-test-user",
        content="Performance test memory",
        importance=0.5
    )
    duration = time.time() - start

    assert result["status"] == "success"
    assert duration < 3.0, f"Direct storage took {duration}s, expected <3s"

@pytest.mark.asyncio
async def test_delete_latency():
    """Verify delete completes in <1s."""
    # First create
    store_result = await store_memory_tool_handler(
        user_id="perf-test-user",
        content="Memory to delete"
    )
    memory_id = store_result["memory_id"]

    # Measure delete
    import time
    start = time.time()
    delete_result = await delete_memory_tool_handler(
        user_id="perf-test-user",
        memory_id=memory_id
    )
    duration = time.time() - start

    assert delete_result["deleted"] is True
    assert duration < 1.0, f"Delete took {duration}s, expected <1s"
```

---

## 9. Rollout Plan

### Phase 1: agentic-memories (Day 1)

1. Add `POST /v1/memories/direct` endpoint
2. Add `DELETE /v1/memories/{id}` endpoint
3. Deploy to staging
4. Run integration tests

### Phase 2: Annie Backend (Day 1-2)

1. Update `store_memory` tool to use direct API
2. Add `delete_memory` tool
3. Update system prompt with memory instructions
4. Deploy to staging

### Phase 3: Testing (Day 2)

1. E2E test: store → retrieve → delete flow
2. Performance test: verify <3s latency
3. LLM behavior test: verify reduced store_memory calls

### Phase 4: Production (Day 3)

1. Deploy agentic-memories changes
2. Deploy Annie changes
3. Monitor:
   - `store_memory` call frequency (should decrease)
   - `store_memory` latency (should be ~1-2s)
   - Error rates
   - User feedback

---

## 10. Monitoring & Alerts

### Metrics to Track

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| `store_memory` p95 latency | <3s | >5s |
| `delete_memory` p95 latency | <1s | >2s |
| `store_memory` error rate | <1% | >5% |
| `store_memory` calls per user per day | <5 | >20 (indicates LLM not following instructions) |

### Log Queries

```
# Direct storage performance
event="memories.direct" | stats avg(duration_ms), p95(duration_ms) by status

# Delete performance
event="memories.delete" | stats avg(duration_ms), p95(duration_ms) by status

# Tool usage patterns
tool_name="store_memory" | stats count by user_id, hour
```

---

## 11. Rollback Plan

If issues are detected:

### Quick Rollback (Annie only)

1. Revert `store_memory` handler to call `/v1/store` instead of `/v1/memories/direct`
2. Increase timeout back to 180s
3. Deploy Annie

### Full Rollback

1. Revert Annie changes
2. Revert agentic-memories changes (endpoints remain but unused)
3. Monitor for stability

---

## 12. Design Decisions (Updated 2025-12-29)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Transaction Atomicity | Best-effort | Partial success acceptable; monitoring catches discrepancies |
| Collection Name | "memories" | Confirmed matches main pipeline in `storage.py` |
| Embedding Timeout | None | Trust OpenAI (~500ms typical) |
| Tag Limit | 10 tags max | Sufficient flexibility for complex memories |
| Storage Routing | ChromaDB + conditional typed tables | Skip semantic_memories; use episodic/emotional/procedural based on fields |
| Metadata Flags | stored_in_* flags in ChromaDB | Enables efficient deletion without querying all tables |
| Delete Logic | Metadata-driven | Check ChromaDB metadata flags to know which typed tables to delete from |
| Performance Threshold | 3s | Safe buffer for cold starts/network variance |
| Rate Limiting | Defer to post-launch | Monitor first, implement if needed |
| LLM Compliance | Trust system prompt | No server-side enforcement |
| Content Filtering | Defer | Trust LLM, add if issues arise |
| Delete UX | ID-based | LLM handles fuzzy matching via retrieve_memories |

## 13. Remaining Open Questions

1. **Embedding Model**: Should direct storage use the same embedding model as the main pipeline?
   - Recommendation: Yes, for consistency in retrieval

2. **Audit Trail**: Should we log all delete operations?
   - Recommendation: Yes, with reason field for compliance

---

## 14. Appendix

### A. Memory Model Reference

```python
class Memory(BaseModel):
    id: Optional[str] = None
    user_id: str
    content: str
    layer: Literal["short-term", "semantic", "long-term"]
    type: Literal["explicit", "implicit"]
    embedding: Optional[List[float]] = None
    timestamp: datetime
    confidence: float = 0.5
    ttl: Optional[int] = None
    usage_count: int = 0
    relevance_score: float = 0.0
    importance: float = 0.5
    persona_tags: List[str] = []
    emotional_signature: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = {}
```

### B. Episodic Memory Table Schema

```sql
CREATE TABLE episodic_memories (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL,
    event_type TEXT,
    content TEXT NOT NULL,
    location JSONB,
    participants TEXT[],
    emotional_valence FLOAT,
    emotional_arousal FLOAT,
    importance_score FLOAT,
    tags TEXT[],
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_episodic_user_id ON episodic_memories(user_id);
CREATE INDEX idx_episodic_timestamp ON episodic_memories(event_timestamp DESC);
```

### C. ChromaDB Collection Schema

```python
collection.add(
    ids=["memory-uuid"],
    embeddings=[[0.1, 0.2, ...]],  # 1536 dims for OpenAI
    documents=["Memory content"],
    metadatas=[{
        "user_id": "user-123",
        "layer": "semantic",
        "type": "explicit",
        "importance": 0.8,
        "confidence": 0.9,
        "timestamp": "2025-12-27T10:00:00Z",
        "source": "llm_explicit",
        "tag_0": "health",
        "tag_1": "allergy"
    }]
)
```
