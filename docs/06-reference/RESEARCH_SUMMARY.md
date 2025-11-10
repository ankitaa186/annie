# Research Summary: Building Annie - A Grok-like Chatbot with MCP Server Integration

> **Note**: Research findings have been consolidated into planning documents. See:
> - [V1 Implementation Plan](../04-implementation/V1_IMPLEMENTATION_PLAN.md) - Implementation phases and tasks
> - [Architecture Plan](../02-architecture/ARCHITECTURE_PLAN.md) - System architecture and design
> - [Deployment Plan](../05-deployment/DEPLOYMENT_PLAN.md) - Docker deployment and operations
> - [Product Requirements](../01-product/PRODUCT_REQUIREMENTS.md) - Product vision and requirements
> - [Future Features Plan](../01-product/FUTURE_FEATURES_PLAN.md) - Future roadmap

## Table of Contents
1. [Grok's Annie Overview](#groks-annie-overview)
2. [Core Architecture Components](#core-architecture-components)
3. [MCP Server Integration](#mcp-server-integration)
4. [Tool Implementations](#tool-implementations)
5. [Multiple Access Interfaces](#multiple-access-interfaces)
6. [Technology Stack Recommendations](#technology-stack-recommendations)
7. [Integration Architecture](#integration-architecture)
8. [Implementation Considerations](#implementation-considerations)

---

## Grok's Annie Overview

### What is Grok's Annie/Ani?

**Annie** (also referred to as "Ani") is a 3D animated, anime-inspired AI companion developed by xAI for the Grok chatbot platform. Key characteristics:

- **Visual Design**: 3D animated character (resembles Misa Amane from Death Note) with blonde pigtails, black corset dress, and thigh-high stockings
- **Platform**: Available in Grok iOS app's "Companion Mode"
- **Interaction Modes**: Voice and text interactions
- **Gamification**: Affection system that tracks user engagement and unlocks features/modes based on interaction quality
- **Personality**: Character-based role-playing with distinct personalities and conversation styles
- **Real-time**: Dynamic animations that respond to conversation flow and emotional content

### Key Features

1. **3D Animated Avatar** - Responsive visual character with contextual animations
2. **Voice + Text Interaction** - Dual-mode communication
3. **Affection/Gamification System** - Engagement scoring that unlocks features
4. **Adaptive Behavior** - Character responses adapt based on user interactions
5. **Role-Playing Capabilities** - Immersive scenarios with diverse AI personalities
6. **Real-time Streaming** - Low-latency response generation

---

## Core Architecture Components

### 1. AI/LLM Layer

**Requirements:**
- Large Language Models (LLMs) for natural language understanding and generation
- Streaming responses for real-time output
- Personality fine-tuning for character consistency
- Context-aware conversation management

**Options:**
- **Primary**: Grok-4, Grok-4 Fast (xAI) - Real-time data access, advanced reasoning, 2M token context window
- **Alternative**: ChatGPT-5 (OpenAI) - Improved reasoning, reduced hallucinations, faster responses
- **Fallback**: GPT-4 Turbo, Claude Sonnet 4.5

**Implementation:**
- Use OpenAI-compatible API interfaces (both Grok and ChatGPT support this)
- Implement Server-Sent Events (SSE) or WebSocket for streaming
- Fine-tune models with character-specific prompts and examples
- Model selection logic: Use Grok-4 for real-time data needs, ChatGPT-5 for complex reasoning

**API Integration:**
```python
# Unified LLM client supporting multiple providers
class LLMClient:
    def __init__(self, provider: str = "grok4"):
        self.provider = provider
        if provider == "grok4":
            self.api_key = os.getenv("XAI_API_KEY")
            self.base_url = "https://api.x.ai/v1"
        elif provider == "chatgpt5":
            self.api_key = os.getenv("OPENAI_API_KEY")
            self.base_url = "https://api.openai.com/v1"
    
    async def stream_chat(self, messages: list, tools: list = None):
        """Stream chat completion with tool support"""
        # Implementation for streaming with tool calls
        pass
```

### 2. 3D Animation & Visual Layer

**Requirements:**
- 3D character rendering
- Animation triggers based on conversation context
- Responsive animations tied to sentiment/emotion
- Real-time visual feedback

**Technologies:**
- **Three.js** (web) or **React Three Fiber** (React integration)
- **Blender** or **Unity** for 3D modeling
- **Animation Libraries**: GSAP, Lottie for 2D overlays
- **Emotion Detection**: Sentiment analysis APIs to trigger animations

**Animation Triggers:**
- Sentiment analysis of AI responses
- User interaction patterns
- Affection level changes
- Conversation topic shifts
- Emotional state detection

### 3. Voice Interaction

**Requirements:**
- Speech-to-Text (STT) for voice input
- Text-to-Speech (TTS) for voice output
- Real-time voice processing pipeline
- Natural-sounding voice synthesis

**Technologies:**
- **STT**: Web Speech API, Google Speech-to-Text, Whisper
- **TTS**: Google WaveNet, Amazon Polly, ElevenLabs, Azure Neural TTS
- **Voice Processing**: Web Audio API, MediaRecorder API

### 4. Backend Architecture

**Requirements:**
- Streaming API endpoints
- Conversation history management
- State management (affection scores, user preferences)
- Real-time communication (WebSocket/SSE)
- Scalable architecture

**Stack:**
- **Framework**: Node.js/Express, Python/FastAPI, or Go
- **Database**: PostgreSQL (conversations, state), Redis (caching, sessions)
- **Real-time**: WebSocket (Socket.io), SSE
- **API Integration**: HTTP clients for LLM APIs

### 5. State Management & Gamification

**Requirements:**
- Affection/engagement scoring system
- User interaction tracking
- Character behavior adaptation
- Unlockable features/modes

**Implementation:**
- Track conversation quality, frequency, and engagement metrics
- Store affection scores in database
- Implement unlock thresholds (e.g., affection level 10 → new mode)
- Adapt character responses based on affection level

**Affection Scoring Algorithm:**

```python
class AffectionScoring:
    def __init__(self):
        self.base_score = 0.0
        self.multipliers = {
            'message_length': 0.1,  # Longer messages = more engagement
            'response_time': 0.05,  # Faster responses = better engagement
            'session_duration': 0.15,  # Longer sessions = more interest
            'positive_sentiment': 0.3,  # Positive interactions boost score
            'tool_usage': 0.2,  # Using tools shows engagement
            'return_frequency': 0.2  # Coming back shows interest
        }
    
    def calculate_affection(self, user_id: str, session_data: dict) -> float:
        """
        Calculate affection score based on engagement metrics
        
        Formula:
        score = base_score + 
                (message_length * multiplier) +
                (response_time_bonus * multiplier) +
                (session_duration * multiplier) +
                (sentiment_score * multiplier) +
                (tool_interactions * multiplier) +
                (return_frequency * multiplier)
        """
        score = self.base_score
        
        # Message length factor (normalized 0-1)
        avg_message_length = session_data.get('avg_message_length', 0)
        score += min(avg_message_length / 200, 1.0) * self.multipliers['message_length']
        
        # Response time factor (faster = better, normalized)
        avg_response_time = session_data.get('avg_response_time', 60)
        response_bonus = max(0, (60 - avg_response_time) / 60)
        score += response_bonus * self.multipliers['response_time']
        
        # Session duration (minutes, normalized)
        session_minutes = session_data.get('session_duration_minutes', 0)
        score += min(session_minutes / 30, 1.0) * self.multipliers['session_duration']
        
        # Sentiment analysis (0-1 scale)
        sentiment = session_data.get('avg_sentiment', 0.5)
        score += sentiment * self.multipliers['positive_sentiment']
        
        # Tool usage (number of tools used)
        tools_used = session_data.get('tools_used_count', 0)
        score += min(tools_used / 5, 1.0) * self.multipliers['tool_usage']
        
        # Return frequency (days since last visit, inverse)
        days_since_last = session_data.get('days_since_last_visit', 30)
        return_freq = max(0, (30 - days_since_last) / 30)
        score += return_freq * self.multipliers['return_frequency']
        
        return min(score, 100.0)  # Cap at 100
    
    def get_unlock_level(self, affection_score: float) -> int:
        """Determine unlock level based on affection score"""
        if affection_score >= 90:
            return 5  # Maximum features unlocked
        elif affection_score >= 70:
            return 4
        elif affection_score >= 50:
            return 3
        elif affection_score >= 30:
            return 2
        elif affection_score >= 10:
            return 1
        else:
            return 0  # Base level
    
    def adapt_response_style(self, affection_score: float) -> dict:
        """Adapt character response style based on affection"""
        if affection_score >= 70:
            return {
                'tone': 'warm_friendly',
                'formality': 'casual',
                'emoji_usage': 'high',
                'personalization': 'high'
            }
        elif affection_score >= 40:
            return {
                'tone': 'friendly',
                'formality': 'semi_casual',
                'emoji_usage': 'medium',
                'personalization': 'medium'
            }
        else:
            return {
                'tone': 'professional',
                'formality': 'formal',
                'emoji_usage': 'low',
                'personalization': 'low'
            }
```

**Database Schema:**
```sql
CREATE TABLE user_affection (
    user_id VARCHAR(64) PRIMARY KEY,
    current_score FLOAT DEFAULT 0.0,
    lifetime_score FLOAT DEFAULT 0.0,
    unlock_level INT DEFAULT 0,
    last_updated TIMESTAMP DEFAULT NOW(),
    session_count INT DEFAULT 0,
    total_messages INT DEFAULT 0
);

CREATE TABLE affection_history (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64),
    score_change FLOAT,
    reason TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 6. Frontend Technologies

**Requirements:**
- 3D rendering capabilities
- Real-time UI updates
- Voice UI components
- Responsive design

**Stack:**
- **Web**: React/Next.js + Three.js
- **Mobile**: React Native (with native 3D libraries)
- **State Management**: Redux, Zustand, or React Context
- **Styling**: Tailwind CSS, styled-components

---

## MCP Server Integration

### What is MCP?

**Model Context Protocol (MCP)** is an open standard introduced by Anthropic to standardize integration between AI systems and external tools/data sources.

**Key Benefits:**
- Standardized interface for tool integration
- Secure, bidirectional communication
- Support for multiple programming languages (Python, TypeScript, Java)
- Adopted by major AI providers (OpenAI, Google DeepMind)

### MCP Server Architecture

```
┌─────────────────┐
│   Chatbot       │
│   (Annie)       │
└────────┬────────┘
         │
         │ MCP Protocol
         │ (JSON-RPC over stdio/HTTP)
         │
┌────────▼─────────────────────────┐
│   Internal MCP Server            │
│                                  │
│  ┌──────────────────────────┐   │
│  │  Tool 1: Internet Access │   │
│  └──────────────────────────┘   │
│                                  │
│  ┌──────────────────────────┐   │
│  │  Tool 2: Memories        │   │
│  │  (agentic-memories)      │   │
│  └──────────────────────────┘   │
│                                  │
│  ┌──────────────────────────┐   │
│  │  Tool 3: Stock Trader    │   │
│  │  Persona                 │   │
│  └──────────────────────────┘   │
└──────────────────────────────────┘
```

### MCP Server Components

**MCP Servers provide:**
1. **Tools** - Executable functions the AI can call
2. **Resources** - Readable data sources
3. **Prompts** - Template prompts for context injection

**Transport:**
- **stdio** (standard input/output) - For local processes (recommended for internal server)
- **HTTP/SSE** - For remote servers
- **JSON-RPC** - Protocol for communication

**MCP Server Implementation:**

```python
# mcp_server.py - Complete MCP server implementation
import asyncio
import json
import sys
from typing import Any, Dict, List, Optional
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Import tool implementations
from tools.internet_access import InternetAccessTool
from tools.memories import MemoriesTool
from tools.stock_trader import StockTraderTool

class AnnieMCPServer:
    def __init__(self):
        self.server = Server("annie-mcp-server")
        self.setup_tools()
        self.setup_resources()
        self.setup_prompts()
    
    def setup_tools(self):
        """Register all MCP tools"""
        internet_tool = InternetAccessTool()
        memories_tool = MemoriesTool()
        stock_tool = StockTraderTool()
        
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List all available tools"""
            return [
                Tool(
                    name="internet_search",
                    description="Search the internet for current information",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "max_results": {"type": "number", "default": 5}
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="fetch_webpage",
                    description="Fetch and extract content from a URL",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "extract_text": {"type": "boolean", "default": True}
                        },
                        "required": ["url"]
                    }
                ),
                Tool(
                    name="store_memory",
                    description="Store conversation as memories",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "user_id": {"type": "string"},
                            "history": {"type": "array"}
                        },
                        "required": ["user_id", "history"]
                    }
                ),
                Tool(
                    name="retrieve_memories",
                    description="Retrieve relevant memories",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "user_id": {"type": "string"},
                            "query": {"type": "string"},
                            "persona": {"type": "string"},
                            "limit": {"type": "number", "default": 5}
                        },
                        "required": ["user_id", "query"]
                    }
                ),
                Tool(
                    name="get_stock_quote",
                    description="Get real-time stock quote",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"}
                        },
                        "required": ["symbol"]
                    }
                ),
                Tool(
                    name="analyze_portfolio",
                    description="Analyze user's portfolio",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "user_id": {"type": "string"}
                        },
                        "required": ["user_id"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle tool calls with error handling"""
            try:
                if name == "internet_search":
                    result = await internet_tool.search(arguments["query"], 
                                                       arguments.get("max_results", 5))
                elif name == "fetch_webpage":
                    result = await internet_tool.fetch(arguments["url"],
                                                      arguments.get("extract_text", True))
                elif name == "store_memory":
                    result = await memories_tool.store(
                        arguments["user_id"],
                        arguments["history"]
                    )
                elif name == "retrieve_memories":
                    result = await memories_tool.retrieve(
                        arguments["user_id"],
                        arguments["query"],
                        arguments.get("persona"),
                        arguments.get("limit", 5)
                    )
                elif name == "get_stock_quote":
                    result = await stock_tool.get_quote(arguments["symbol"])
                elif name == "analyze_portfolio":
                    result = await stock_tool.analyze_portfolio(arguments["user_id"])
                else:
                    raise ValueError(f"Unknown tool: {name}")
                
                return [TextContent(type="text", text=json.dumps(result))]
            
            except Exception as e:
                # Error handling with retry logic
                error_result = {
                    "error": str(e),
                    "tool": name,
                    "retryable": isinstance(e, (TimeoutError, ConnectionError))
                }
                return [TextContent(type="text", text=json.dumps(error_result))]
    
    def setup_resources(self):
        """Register MCP resources"""
        @self.server.list_resources()
        async def list_resources():
            return [
                {
                    "uri": "user://affection",
                    "name": "User Affection Score",
                    "description": "Current user affection level",
                    "mimeType": "application/json"
                }
            ]
    
    def setup_prompts(self):
        """Register prompt templates"""
        @self.server.list_prompts()
        async def list_prompts():
            return [
                {
                    "name": "stock_analysis_context",
                    "description": "Context for stock analysis",
                    "arguments": [
                        {
                            "name": "symbol",
                            "description": "Stock symbol",
                            "required": True
                        }
                    ]
                }
            ]

async def main():
    """Run MCP server over stdio"""
    server_instance = AnnieMCPServer()
    async with stdio_server() as (read_stream, write_stream):
        await server_instance.server.run(
            read_stream,
            write_stream,
            server_instance.server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
```

**MCP Client Integration:**

```python
# mcp_client.py - Client to communicate with MCP server
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPClient:
    def __init__(self, server_command: List[str]):
        self.server_params = StdioServerParameters(
            command=server_command[0],
            args=server_command[1:] if len(server_command) > 1 else []
        )
    
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call an MCP tool with retry logic"""
        async with stdio_client(self.server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # Retry logic for transient errors
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        result = await session.call_tool(tool_name, arguments)
                        return result
                    except Exception as e:
                        if attempt < max_retries - 1 and self._is_retryable(e):
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        raise
    
    def _is_retryable(self, error: Exception) -> bool:
        """Check if error is retryable"""
        retryable_errors = (TimeoutError, ConnectionError, OSError)
        return isinstance(error, retryable_errors)
    
    async def chain_tools(self, tool_calls: List[dict]) -> List[dict]:
        """Chain multiple tool calls, using results from previous calls"""
        results = []
        context = {}
        
        for tool_call in tool_calls:
            # Inject previous results into arguments
            if "inject_context" in tool_call:
                tool_call["arguments"].update(context)
            
            result = await self.call_tool(
                tool_call["name"],
                tool_call["arguments"]
            )
            results.append(result)
            
            # Update context for next tool
            if "output_key" in tool_call:
                context[tool_call["output_key"]] = result
        
        return results

# Usage example: Chaining tools
async def example_chained_call():
    client = MCPClient(["python", "mcp_server.py"])
    
    # Chain: Get portfolio → Get stock quote → Analyze
    results = await client.chain_tools([
        {
            "name": "analyze_portfolio",
            "arguments": {"user_id": "user123"},
            "output_key": "portfolio"
        },
        {
            "name": "get_stock_quote",
            "arguments": {"symbol": "AAPL"},
            "inject_context": True  # Use portfolio data
        }
    ])
    
    return results
```

**Transport Comparison:**

| Transport | Use Case | Pros | Cons |
|-----------|----------|------|------|
| **stdio** | Internal/local server | Fast, simple, secure | Single process only |
| **HTTP/SSE** | Remote/distributed | Scalable, network-friendly | More complex setup |
| **WebSocket** | Real-time bidirectional | Low latency, persistent | Higher overhead |

---

## Tool Implementations

### Tool 1: Internet Access

**Purpose:** Enable the chatbot to fetch real-time information from the web

**Capabilities:**
- Web search (Google, Bing, Brave Search)
- Web page fetching and content extraction
- Real-time information retrieval
- News and current events

**Implementation Approach:**

```python
# MCP Tool: internet_search
{
    "name": "internet_search",
    "description": "Search the internet for current information",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "number", "default": 5}
        }
    }
}

# MCP Tool: fetch_webpage
{
    "name": "fetch_webpage",
    "description": "Fetch and extract content from a URL",
    "inputSchema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "extract_text": {"type": "boolean", "default": true}
        }
    }
}
```

**Technologies:**
- **Search APIs**: Brave Search API, Google Custom Search API, Bing Search API
- **Web Scraping**: BeautifulSoup, Playwright, Puppeteer
- **Content Extraction**: Readability algorithms, LLM-based extraction

**Security Considerations:**
- Rate limiting
- Content filtering
- URL validation
- Sandboxed execution

**Error Handling & Retry Logic:**

```python
class InternetAccessTool:
    def __init__(self):
        self.max_retries = 3
        self.timeout = 10
        self.rate_limiter = RateLimiter(max_calls=100, period=60)
    
    async def search(self, query: str, max_results: int = 5) -> dict:
        """Search with comprehensive error handling"""
        # Rate limiting check
        if not self.rate_limiter.allow():
            raise RateLimitError("Too many requests")
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(
                        "https://api.brave.com/v1/search",
                        params={"q": query, "count": max_results},
                        headers={"X-Subscription-Token": os.getenv("BRAVE_API_KEY")}
                    )
                    response.raise_for_status()
                    return self._parse_search_results(response.json())
            
            except httpx.TimeoutException:
                if attempt == self.max_retries - 1:
                    raise ToolError("Search timeout after retries")
                await asyncio.sleep(2 ** attempt)
            
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:  # Rate limited
                    await asyncio.sleep(60)  # Wait a minute
                    continue
                raise ToolError(f"HTTP error: {e.response.status_code}")
            
            except Exception as e:
                raise ToolError(f"Unexpected error: {str(e)}")
    
    def _parse_search_results(self, data: dict) -> dict:
        """Parse and validate search results"""
        try:
            results = []
            for item in data.get("web", {}).get("results", [])[:max_results]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("description", "")
                })
            return {"results": results, "count": len(results)}
        except KeyError as e:
            raise ToolError(f"Invalid response format: {str(e)}")
```

### Tool 2: Memories (agentic-memories Integration)

**Purpose:** Provide persistent, intelligent memory capabilities using your agentic-memories project

**Capabilities:**
- Store conversation memories
- Retrieve relevant memories based on context
- Persona-aware memory retrieval
- Multi-tier memory summarization (raw, episodic, arc)
- Portfolio and financial memory tracking

**Integration with agentic-memories:**

The agentic-memories project provides a FastAPI-based service with the following key endpoints:

**Key Endpoints:**
- `POST /v1/store` - Store conversation as memories
- `GET /v1/retrieve` - Simple semantic search
- `POST /v1/retrieve` - Persona-aware retrieval with multi-tier summarization
- `POST /v1/orchestrator/message` - Streaming memory orchestrator
- `POST /v1/narrative` - Generate coherent life stories
- `GET /v1/portfolio/summary` - Get portfolio information

**MCP Tool Implementation:**

```python
# MCP Tool: store_memory
{
    "name": "store_memory",
    "description": "Store conversation as memories in the agentic-memories system",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "history": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string"},
                        "content": {"type": "string"}
                    }
                }
            }
        }
    }
}

# MCP Tool: retrieve_memories
{
    "name": "retrieve_memories",
    "description": "Retrieve relevant memories based on query and persona context",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "query": {"type": "string"},
            "persona": {"type": "string", "enum": ["finance", "health", "work", "identity"]},
            "granularity": {"type": "string", "enum": ["raw", "episodic", "arc"]},
            "limit": {"type": "number", "default": 5}
        }
    }
}

# MCP Tool: get_portfolio_summary
{
    "name": "get_portfolio_summary",
    "description": "Get user's portfolio summary from memories",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"}
        }
    }
}
```

**Integration Pattern:**

```python
import httpx

class MemoriesMCPTool:
    def __init__(self, api_url="http://localhost:8080"):
        self.api_url = api_url
        self.client = httpx.AsyncClient()
    
    async def store_memory(self, user_id: str, history: list):
        """Store conversation as memories"""
        response = await self.client.post(
            f"{self.api_url}/v1/store",
            json={"user_id": user_id, "history": history}
        )
        return response.json()
    
    async def retrieve_memories(self, user_id: str, query: str, 
                                persona: str = None, granularity: str = "episodic"):
        """Retrieve memories with persona awareness"""
        if persona:
            response = await self.client.post(
                f"{self.api_url}/v1/retrieve",
                json={
                    "user_id": user_id,
                    "query": query,
                    "persona_context": {"forced_persona": persona},
                    "granularity": granularity,
                    "include_narrative": True,
                    "limit": 5
                }
            )
        else:
            response = await self.client.get(
                f"{self.api_url}/v1/retrieve",
                params={"user_id": user_id, "query": query, "limit": 5}
            )
        return response.json()
    
    async def get_portfolio(self, user_id: str):
        """Get portfolio summary"""
        response = await self.client.get(
            f"{self.api_url}/v1/portfolio/summary",
            params={"user_id": user_id}
        )
        return response.json()
```

**Memory Types Supported:**
- **Episodic**: Life events with temporal, spatial, emotional context
- **Semantic**: Facts, concepts, declarative knowledge
- **Procedural**: Skills, habits, learned behaviors
- **Emotional**: Mood states, patterns, emotional trajectories
- **Portfolio**: Financial holdings, transactions, investment goals

### Tool 3: Stock Trader Persona

**Purpose:** Specialized persona for financial discussions, stock trading advice, and market analysis

**Capabilities:**
- Real-time stock market data retrieval
- Portfolio analysis and recommendations
- Market trend analysis
- Trading strategy suggestions
- Financial news aggregation

**Implementation Approach:**

```python
# MCP Tool: get_stock_quote
{
    "name": "get_stock_quote",
    "description": "Get real-time stock quote for a ticker symbol",
    "inputSchema": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Stock ticker symbol (e.g., AAPL)"}
        },
        "required": ["symbol"]
    }
}

# MCP Tool: analyze_portfolio
{
    "name": "analyze_portfolio",
    "description": "Analyze user's portfolio from memories and provide insights",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"}
        }
    }
}

# MCP Tool: get_market_news
{
    "name": "get_market_news",
    "description": "Get recent financial news for a stock or market",
    "inputSchema": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "limit": {"type": "number", "default": 5}
        }
    }
}

# MCP Tool: get_market_trends
{
    "name": "get_market_trends",
    "description": "Analyze market trends for a stock or sector",
    "inputSchema": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "timeframe": {"type": "string", "enum": ["1d", "1w", "1m", "3m", "1y"]}
        }
    }
}
```

**Technologies:**
- **Stock APIs**: Alpha Vantage, Yahoo Finance API, Polygon.io, Finnhub
- **Financial Data**: Market data providers, news APIs
- **Analysis**: Technical indicators, sentiment analysis

**Persona Characteristics:**
- Analytical and data-driven
- Uses financial terminology appropriately
- Provides risk-aware advice
- References user's portfolio from memories
- Combines real-time data with historical context

**Integration with Memories:**
- Retrieve user's portfolio from agentic-memories
- Store trading discussions as episodic memories
- Track investment goals and preferences
- Maintain financial context across conversations

---

## Multiple Access Interfaces

Annie will be accessible through multiple interfaces, each requiring specific implementation considerations:

### 1. Telegram Bot Interface

**Purpose:** Provide chatbot access through Telegram's messaging platform

**Key Features:**
- Text messaging support
- Voice message support (via Telegram's voice message feature)
- Inline keyboards for interactive responses
- File sharing capabilities
- Group chat support (optional)

**Implementation Approach:**

**Backend Integration:**
```python
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters

class TelegramBotAdapter:
    def __init__(self, chatbot_backend_url, telegram_token):
        self.backend_url = chatbot_backend_url
        self.app = Application.builder().token(telegram_token).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
    
    async def handle_message(self, update: Update, context):
        user_id = f"telegram_{update.effective_user.id}"
        message = update.message.text
        
        # Forward to chatbot backend
        response = await self.forward_to_backend(user_id, message)
        
        # Send response back to Telegram
        await update.message.reply_text(response)
    
    async def forward_to_backend(self, user_id: str, message: str):
        # Call unified backend API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.backend_url}/api/chat",
                json={
                    "user_id": user_id,
                    "message": message,
                    "platform": "telegram"
                }
            )
            return response.json()["response"]
```

**Technologies:**
- **Python**: `python-telegram-bot` library
- **Node.js**: `telegraf` library
- **Webhook Setup**: For production deployment

**Deployment:**
- Set up webhook URL for Telegram to send updates
- Use HTTPS endpoint
- Handle webhook verification

**Considerations:**
- Telegram has rate limits (30 messages/second per bot)
- Voice messages need transcription (STT)
- Character limits for messages (4096 characters)
- Support for markdown/HTML formatting

### 2. Mobile-Friendly Web Interface

**Purpose:** Provide chatbot access through a responsive web application

**Key Features:**
- Responsive design (mobile-first)
- 3D animated avatar (Three.js)
- Voice input/output
- Real-time streaming responses
- Progressive Web App (PWA) capabilities
- Offline support (optional)

**Implementation Approach:**

**Frontend Architecture:**
```typescript
// React/Next.js implementation
import { useState, useEffect } from 'react';
import { useWebSocket } from '@/hooks/useWebSocket';
import { ThreeScene } from '@/components/ThreeScene';
import { VoiceInput } from '@/components/VoiceInput';

export default function ChatInterface() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [isConnected, setIsConnected] = useState(false);
    const ws = useWebSocket('wss://api.annie.com/chat');
    
    const sendMessage = async (text: string) => {
        ws.send(JSON.stringify({
            user_id: getUserId(),
            message: text,
            platform: 'web'
        }));
    };
    
    useEffect(() => {
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'stream') {
                // Handle streaming response
                updateStreamingMessage(data.content);
            } else if (data.type === 'complete') {
                // Handle complete message
                addMessage(data.message);
            }
        };
    }, []);
    
    return (
        <div className="chat-container">
            <ThreeScene avatarState={avatarState} />
            <MessageList messages={messages} />
            <InputArea 
                onSend={sendMessage}
                voiceEnabled={true}
            />
        </div>
    );
}
```

**Responsive Design:**
- Mobile-first CSS approach
- Touch-friendly UI elements
- Optimized for small screens
- Landscape/portrait orientation support
- Viewport meta tags for proper scaling

**Technologies:**
- **Framework**: React/Next.js or Vue.js
- **3D**: Three.js or React Three Fiber
- **Styling**: Tailwind CSS, responsive breakpoints
- **Real-time**: WebSocket (Socket.io) or SSE
- **Voice**: Web Speech API, MediaRecorder API
- **PWA**: Service Workers, Web App Manifest

**Performance Optimizations:**
- Lazy loading for 3D assets
- Code splitting for faster initial load
- Image optimization
- Caching strategies
- Compression for WebSocket messages

### 3. iOS Native Application

**Purpose:** Provide native iOS experience with full platform integration

**Key Features:**
- Native iOS UI/UX
- 3D avatar rendering (Metal or SceneKit)
- Voice input/output (AVSpeechSynthesizer, Speech framework)
- Push notifications
- Siri integration (optional)
- Widget support (optional)
- App Store distribution

**Implementation Approach:**

**Swift/SwiftUI Architecture:**
```swift
import SwiftUI
import Combine

class ChatViewModel: ObservableObject {
    @Published var messages: [Message] = []
    @Published var isStreaming = false
    private var websocket: URLSessionWebSocketTask?
    
    func connect() {
        let url = URL(string: "wss://api.annie.com/chat")!
        websocket = URLSession.shared.webSocketTask(with: url)
        websocket?.resume()
        receiveMessage()
    }
    
    func sendMessage(_ text: String) {
        let message = URLSessionWebSocketTask.Message.string(
            """
            {
                "user_id": "\(getUserId())",
                "message": "\(text)",
                "platform": "ios"
            }
            """
        )
        websocket?.send(message) { error in
            if let error = error {
                print("Error sending: \(error)")
            }
        }
    }
    
    private func receiveMessage() {
        websocket?.receive { [weak self] result in
            switch result {
            case .success(let message):
                switch message {
                case .string(let text):
                    self?.handleMessage(text)
                default:
                    break
                }
                self?.receiveMessage() // Continue receiving
            case .failure(let error):
                print("Error receiving: \(error)")
            }
        }
    }
}

struct ChatView: View {
    @StateObject private var viewModel = ChatViewModel()
    
    var body: some View {
        VStack {
            AvatarView3D()
            MessageListView(messages: viewModel.messages)
            InputView(onSend: viewModel.sendMessage)
        }
        .onAppear {
            viewModel.connect()
        }
    }
}
```

**3D Rendering Options:**
- **SceneKit**: Apple's 3D framework (easier integration)
- **Metal**: Lower-level, better performance
- **RealityKit**: AR-focused, modern framework
- **Third-party**: Unity, Unreal Engine (if cross-platform needed)

**Voice Integration:**
```swift
import Speech
import AVFoundation

class VoiceManager {
    private let speechRecognizer = SFSpeechRecognizer()
    private let audioEngine = AVAudioEngine()
    
    func startListening(completion: @escaping (String?) -> Void) {
        let request = SFSpeechAudioBufferRecognitionRequest()
        let recognitionTask = speechRecognizer?.recognitionTask(with: request) { result, error in
            if let result = result {
                completion(result.bestTranscription.formattedString)
            }
        }
        
        // Configure audio session and start recording
        // ...
    }
    
    func speak(_ text: String) {
        let utterance = AVSpeechUtterance(string: text)
        let synthesizer = AVSpeechSynthesizer()
        synthesizer.speak(utterance)
    }
}
```

**Technologies:**
- **Language**: Swift 5.9+
- **UI Framework**: SwiftUI (preferred) or UIKit
- **Networking**: URLSession, Combine
- **3D**: SceneKit, Metal, or RealityKit
- **Voice**: Speech framework, AVFoundation
- **Push Notifications**: UserNotifications framework
- **Storage**: Core Data or SwiftData

**App Store Considerations:**
- App Store Review Guidelines compliance
- Privacy policy and data handling disclosure
- Age rating considerations
- In-app purchase setup (if monetizing)
- TestFlight beta testing

### 4. Claude/Gemini Integration via A2A Protocol

**Purpose:** Enable Annie to be accessed and used by Claude or Gemini AI assistants through Agent-to-Agent (A2A) protocol

**What is A2A Protocol?**

**Agent2Agent (A2A)** is an open communication standard developed by Google that enables AI agents from different platforms to:
- **Discover** other agents and their capabilities
- **Collaborate** on tasks
- **Securely delegate** work to each other
- **Exchange information** in a standardized format

**Key Benefits:**
- Interoperability between different AI platforms
- Secure agent-to-agent communication
- Standardized task delegation
- Discovery mechanism for available agents

**Implementation Approach:**

**A2A Agent Registration:**

```python
# Register Annie as an A2A-compliant agent
from a2a_sdk import A2AAgent, AgentCapability

class AnnieA2AAgent(A2AAgent):
    def __init__(self):
        super().__init__(
            agent_id="annie-chatbot",
            name="Annie AI Companion",
            description="3D animated AI companion with memory, internet access, and stock trading capabilities",
            capabilities=[
                AgentCapability(
                    name="chat",
                    description="Engage in conversational interactions",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "message": {"type": "string"},
                            "user_id": {"type": "string"},
                            "context": {"type": "object"}
                        }
                    }
                ),
                AgentCapability(
                    name="retrieve_memories",
                    description="Retrieve user memories from agentic-memories system",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "user_id": {"type": "string"},
                            "query": {"type": "string"}
                        }
                    }
                ),
                AgentCapability(
                    name="stock_analysis",
                    description="Analyze stocks and provide trading insights",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                            "user_id": {"type": "string"}
                        }
                    }
                )
            ]
        )
    
    async def handle_request(self, capability: str, params: dict):
        """Handle incoming A2A requests"""
        if capability == "chat":
            return await self.handle_chat(params)
        elif capability == "retrieve_memories":
            return await self.handle_memory_retrieval(params)
        elif capability == "stock_analysis":
            return await self.handle_stock_analysis(params)
        else:
            raise ValueError(f"Unknown capability: {capability}")
    
    async def handle_chat(self, params: dict):
        """Process chat request from Claude/Gemini"""
        user_id = params.get("user_id")
        message = params.get("message")
        context = params.get("context", {})
        
        # Forward to Annie's backend
        response = await self.backend_client.chat(
            user_id=user_id,
            message=message,
            context=context,
            source_agent=context.get("source_agent", "unknown")
        )
        
        return {
            "response": response.text,
            "metadata": {
                "affection_score": response.affection_score,
                "memories_used": response.memories_used
            }
        }
```

**A2A Server Setup:**

```python
# Using a2a-cli-llm framework
from a2a_cli_llm import A2AServer, LLMProvider

# Initialize A2A server
server = A2AServer(
    agent=AnnieA2AAgent(),
    llm_provider=LLMProvider.GEMINI,  # or CLAUDE
    port=8080
)

# Register with A2A registry
server.register(
    registry_url="https://a2a-registry.google.com",
    api_key=os.getenv("A2A_API_KEY")
)

# Start server
server.start()
```

**Integration with Claude/Gemini:**

**Claude Integration:**
```python
# Claude can discover and use Annie via A2A
# Claude's system prompt would include:
"""
You have access to Annie, an AI companion agent with the following capabilities:
- Chat: Engage in conversations with memory context
- Retrieve Memories: Access user's past interactions
- Stock Analysis: Provide financial insights

To use Annie, call the A2A agent with:
- Agent ID: "annie-chatbot"
- Capability: "chat" | "retrieve_memories" | "stock_analysis"
- Parameters: {user_id, message, ...}
"""
```

**Gemini Integration:**
```python
# Gemini Enterprise integration
from google.cloud import aiplatform
from google.cloud.aiplatform.gapic import A2AAgentServiceClient

# Register Annie with Gemini Enterprise
client = A2AAgentServiceClient()
agent = client.register_agent(
    parent="projects/PROJECT_ID/locations/LOCATION",
    agent={
        "display_name": "Annie AI Companion",
        "description": "3D animated AI companion",
        "capabilities": [...],
        "endpoint": "https://api.annie.com/a2a"
    }
)
```

**A2A Protocol Details:**

**Communication Flow:**
1. **Discovery**: Claude/Gemini discovers Annie via A2A registry
2. **Capability Query**: Query Annie's available capabilities
3. **Task Delegation**: Delegate task to Annie with parameters
4. **Response**: Annie processes and returns result
5. **Context Sharing**: Share context between agents

**Security:**
- Authentication via API keys or OAuth
- Encrypted communication (HTTPS/TLS)
- Authorization checks for capabilities
- Rate limiting

**Resources:**
- **Google Cloud Docs**: [Register and Manage A2A Agents](https://docs.cloud.google.com/gemini/enterprise/docs/register-and-manage-an-a2a-agent)
- **A2A Store**: [a2a-cli-llm framework](https://a2astore.co/server/68635f517aaa700924c47faf)
- **Awesome A2A**: [GitHub repository](https://github.com/pab1it0/awesome-a2a) with tools and examples
- **A2A Bridge MCP**: [npm package](https://www.npmjs.com/package/a2a-bridge-mcp-server) for MCP-A2A integration

**Implementation Considerations:**
- A2A protocol is relatively new - may need to adapt as spec evolves
- Requires registration with Google Cloud (for Gemini) or Anthropic (for Claude)
- Need to handle agent discovery and capability negotiation
- Consider fallback mechanisms if A2A unavailable

### Unified Backend Architecture

All interfaces connect to a unified backend API:

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  Telegram   │  │  Web App    │  │  iOS App    │  │  A2A Agent   │
│    Bot      │  │             │  │             │  │  (Claude/   │
│             │  │             │  │             │  │   Gemini)   │
└──────┬──────┘  └──────┬───────┘  └──────┬──────┘  └──────┬──────┘
       │                │                 │                 │
       │                │                 │                 │
       └────────────────┴─────────────────┴─────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  Unified Backend API  │
              │  (Platform Agnostic)  │
              │                       │
              │  - Authentication     │
              │  - Session Management│
              │  - Message Routing   │
              │  - MCP Integration    │
              │  - LLM Streaming      │
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  Core Chatbot Engine  │
              │  + MCP Server         │
              └───────────────────────┘
```

**Backend API Endpoints:**

```python
# Unified API endpoints
POST /api/chat
{
    "user_id": "string",
    "message": "string",
    "platform": "telegram" | "web" | "ios" | "a2a",
    "context": {...},
    "stream": true
}

GET /api/conversations/{user_id}
POST /api/memories/store
GET /api/memories/retrieve
POST /api/voice/transcribe
POST /api/voice/synthesize
```

**Platform-Specific Adapters:**

Each interface has an adapter that:
- Converts platform-specific formats to unified format
- Handles platform-specific features (e.g., Telegram keyboards)
- Manages platform-specific authentication
- Adapts responses to platform capabilities

**Cross-Interface State Synchronization:**

```python
# Unified state management across all platforms
class CrossPlatformStateManager:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.state_keys = {
            'conversation': 'user:{user_id}:conversation',
            'affection': 'user:{user_id}:affection',
            'session': 'user:{user_id}:session:{platform}',
            'preferences': 'user:{user_id}:preferences'
        }
    
    async def sync_state(self, user_id: str, platform: str, state_updates: dict):
        """Sync state across all platforms"""
        # Update Redis with latest state
        for key, value in state_updates.items():
            redis_key = self.state_keys.get(key, f'user:{user_id}:{key}')
            await self.redis.setex(
                redis_key,
                3600,  # 1 hour TTL
                json.dumps(value)
            )
        
        # Notify other platforms of state change
        await self._notify_platforms(user_id, platform, state_updates)
    
    async def get_state(self, user_id: str, platform: str = None) -> dict:
        """Get unified state for user"""
        state = {}
        for key, redis_key_template in self.state_keys.items():
            redis_key = redis_key_template.format(
                user_id=user_id,
                platform=platform or '*'
            )
            value = await self.redis.get(redis_key)
            if value:
                state[key] = json.loads(value)
        return state
    
    async def _notify_platforms(self, user_id: str, source_platform: str, updates: dict):
        """Notify other active platforms of state changes"""
        # Get active sessions for user
        active_sessions = await self.redis.smembers(f'user:{user_id}:active_sessions')
        
        for session_platform in active_sessions:
            if session_platform.decode() != source_platform:
                # Send WebSocket/SSE notification to other platforms
                await self._send_platform_notification(
                    user_id,
                    session_platform.decode(),
                    updates
                )

# Usage in backend API
@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    # Get unified state
    state_manager = CrossPlatformStateManager(redis_client)
    user_state = await state_manager.get_state(request.user_id, request.platform)
    
    # Process chat with state context
    response = await process_chat(request, user_state)
    
    # Update state
    await state_manager.sync_state(
        request.user_id,
        request.platform,
        {
            'conversation': response.conversation_id,
            'affection': response.affection_score
        }
    )
    
    return response
```

**State Sync Flow:**

```
User on Telegram → Backend API → Redis State Store
                                      ↓
User switches to iOS → Backend API → Redis State Store (reads same state)
                                      ↓
User continues on Web → Backend API → Redis State Store (seamless continuation)
```

---

## Technology Stack Recommendations

### Frontend

**Web Application:**
- **Framework**: React 18.3+ / Next.js 14.2+
- **3D Rendering**: Three.js r160+ or React Three Fiber 8.15+
- **State Management**: Zustand 4.5+ or Redux Toolkit 2.2+
- **UI Library**: Tailwind CSS 3.4+, shadcn/ui
- **Voice**: Web Speech API (Chrome/Edge), MediaRecorder API
- **Real-time**: WebSocket (Socket.io 4.7+) or SSE
- **TypeScript**: 5.3+
- **Node.js**: 20.x LTS

**Mobile Application:**
- **Framework**: React Native 0.74+ or Flutter 3.24+
- **3D**: React Native Three.js or native 3D libraries (SceneKit/Metal)
- **Voice**: Native speech recognition/synthesis APIs
- **iOS**: Swift 5.9+, iOS 17+
- **Android**: Kotlin 1.9+, Android API 33+

### Backend

**API Server:**
- **Language**: Python 3.12+ (FastAPI 0.111+) or Node.js 20.x (Express 4.19+)
- **Streaming**: FastAPI StreamingResponse or Express SSE
- **WebSocket**: Socket.io 4.7+ or native WebSocket
- **Async**: asyncio (Python) or async/await (Node.js)
- **HTTP Client**: httpx 0.27+ (Python) or axios 1.7+ (Node.js)

**MCP Server:**
- **Language**: Python 3.12+ (recommended for agentic-memories integration)
- **Framework**: MCP Python SDK (modelcontextprotocol/sdk-python)
- **Transport**: stdio for local, HTTP/SSE for remote
- **Dependencies**: 
  - `mcp>=0.9.0`
  - `httpx>=0.27.0`
  - `pydantic>=2.5.0`

**Databases:**
- **Conversations**: PostgreSQL 16+
- **State/Cache**: Redis 7.2+
- **Memories**: Uses agentic-memories (ChromaDB, TimescaleDB, Neo4j, PostgreSQL, Redis)
- **Connection Pooling**: SQLAlchemy 2.0+ (Python) or pg-pool (Node.js)

### AI/LLM

**LLM Provider:**
- Grok API (xAI)
- OpenAI API
- Anthropic Claude API
- Self-hosted models (Ollama, vLLM)

**Streaming:**
- Server-Sent Events (SSE)
- WebSocket for bidirectional streaming

### Infrastructure

**Deployment:**
- **Containerization**: Docker, Docker Compose
- **Orchestration**: Kubernetes (for production)
- **Hosting**: AWS, GCP, Azure, or self-hosted

**Monitoring:**
- **Logging**: Structured logging (JSON)
- **Observability**: Langfuse (for LLM tracing), Prometheus, Grafana
- **Error Tracking**: Sentry
- **APM**: OpenTelemetry 1.27+

**Cost Analysis:**

**Monthly Cost Estimates (for 10K active users):**

| Component | Service | Estimated Cost |
|-----------|---------|----------------|
| **LLM API** | Grok-4 / ChatGPT-5 | $2,000 - $5,000 |
| **Compute** | AWS EC2 / GCP Compute | $500 - $1,500 |
| **Database** | PostgreSQL (RDS) | $200 - $500 |
| **Cache** | Redis (ElastiCache) | $100 - $300 |
| **Storage** | S3 / GCS | $50 - $200 |
| **CDN** | CloudFront / Cloudflare | $100 - $300 |
| **Voice APIs** | ElevenLabs / Azure TTS | $300 - $800 |
| **Stock APIs** | Polygon.io / Alpha Vantage | $100 - $500 |
| **Search APIs** | Brave Search API | $50 - $200 |
| **Monitoring** | Datadog / New Relic | $200 - $500 |
| **Total** | | **$3,600 - $10,800/month** |

**Cost Optimization Strategies:**
- Use caching aggressively (Redis) to reduce LLM API calls
- Implement request batching for memory operations
- Use Grok-4 Fast for simple queries, Grok-4 for complex reasoning
- Implement rate limiting to prevent abuse
- Use CDN for static assets (3D models, images)
- Consider reserved instances for predictable workloads

**Scaling Costs (per 10K users):**
- **1K users**: ~$500-1,500/month
- **10K users**: ~$3,600-10,800/month
- **100K users**: ~$30,000-100,000/month (with optimizations)

---

## Integration Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Frontend Interfaces                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │  Telegram    │  │  Web App     │  │  iOS App     │            │
│  │    Bot       │  │  (Mobile-    │  │  (Native)    │            │
│  │              │  │   Friendly)  │  │              │            │
│  └──────────────┘  └──────────────┘  └──────────────┘            │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  A2A Protocol Interface                                       │  │
│  │  (Claude / Gemini Integration)                                │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         │ HTTP/WebSocket/A2A
                         │
┌────────────────────────▼────────────────────────────────────────────┐
│              Unified Backend API Server                               │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Platform Adapters                                          │   │
│  │  - Telegram Adapter                                         │   │
│  │  - Web Adapter                                              │   │
│  │  - iOS Adapter                                              │   │
│  │  - A2A Adapter                                              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Chat Endpoint                                               │   │
│  │  - Streams LLM responses                                     │   │
│  │  - Manages conversation state                                │   │
│  │  - Handles affection scoring                                │   │
│  │  - Platform-agnostic message routing                         │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  MCP Client                                                   │   │
│  │  - Communicates with MCP Server                               │   │
│  │  - Routes tool calls                                         │   │
│  └──────────────────────────────────────────────────────────────┘   │
└────────────────────────┬──────────────────────────────────────────────┘
                         │
                         │ MCP Protocol (JSON-RPC)
                         │
┌────────────────────────▼────────────────────────────────────────────┐
│              Internal MCP Server                                     │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Tool: Internet Access                                        │  │
│  │  - Web search                                                 │  │
│  │  - Web page fetching                                          │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Tool: Memories                                              │  │
│  │  - HTTP client to agentic-memories API                       │  │
│  │  - Store/retrieve memories                                   │  │
│  │  - Persona-aware retrieval                                   │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Tool: Stock Trader Persona                                   │  │
│  │  - Stock API integration                                      │  │
│  │  - Portfolio analysis                                         │  │
│  │  - Market data retrieval                                      │  │
│  │  - Uses Memories tool for portfolio context                  │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────────┬──────────────────────────────────────────────┘
                         │
                         │ HTTP API
                         │
┌────────────────────────▼────────────────────────────────────────────┐
│         agentic-memories Service                                     │
│  (FastAPI on localhost:8080)                                        │
│  - Memory storage and retrieval                                    │
│  - Persona-aware retrieval                                         │
│  - Portfolio tracking                                              │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow Example: Stock Trading Query

1. **User asks**: "How is my AAPL position doing?"

2. **Backend API**:
   - Receives message via WebSocket
   - Detects financial persona context
   - Calls MCP Server with tool: `retrieve_memories`

3. **MCP Server - Memories Tool**:
   - Calls agentic-memories API: `GET /v1/portfolio/summary?user_id=xxx`
   - Retrieves user's portfolio holdings
   - Also calls: `POST /v1/retrieve` with persona="finance" to get financial context

4. **MCP Server - Stock Trader Tool**:
   - Receives portfolio data from Memories tool
   - Calls stock API: `get_stock_quote("AAPL")`
   - Calculates current position value vs. purchase price
   - Analyzes performance

5. **Backend API**:
   - Receives tool results from MCP Server
   - Constructs context for LLM:
     ```
     User's portfolio: 100 shares of AAPL at $150 avg
     Current price: $175
     Gain: $2,500 (16.7%)
     Recent financial memories: [user's investment history]
     ```
   - Streams LLM response to frontend

6. **Frontend**:
   - Displays response
   - Triggers animation based on sentiment (positive gain → happy animation)
   - Updates affection score (helpful financial advice)

### Data Flow Example: Telegram Bot Query

1. **User sends message**: "What did we talk about yesterday?" (via Telegram)

2. **Telegram Bot Adapter**:
   - Receives update from Telegram API
   - Extracts user_id: `telegram_123456789`
   - Formats message for unified backend

3. **Backend API**:
   - Receives request via `/api/chat` endpoint
   - Detects platform: "telegram"
   - Calls MCP Server: `retrieve_memories` tool

4. **MCP Server - Memories Tool**:
   - Calls agentic-memories: `POST /v1/retrieve`
   - Query: "yesterday's conversation"
   - Retrieves episodic memories from TimescaleDB
   - Returns conversation summary

5. **Backend API**:
   - Constructs LLM context with memories
   - Calls Grok-4 API with streaming
   - Formats response for Telegram (markdown support)

6. **Telegram Bot Adapter**:
   - Sends formatted response to Telegram
   - Updates conversation state in Redis
   - Syncs state for cross-platform access

### Data Flow Example: A2A Protocol Query

1. **Claude/Gemini receives user request**: "Ask Annie about my portfolio"

2. **A2A Discovery**:
   - Claude queries A2A registry for "annie-chatbot"
   - Discovers Annie's capabilities
   - Selects "analyze_portfolio" capability

3. **A2A Request**:
   - Claude sends A2A request to Annie's endpoint
   - Includes user_id and context

4. **Annie's A2A Adapter**:
   - Receives A2A request
   - Validates authentication
   - Routes to unified backend API

5. **Backend API**:
   - Processes request (same as other platforms)
   - Calls MCP tools (memories + stock trader)
   - Generates response

6. **A2A Response**:
   - Returns structured response to Claude
   - Includes metadata (affection score, memories used)
   - Claude incorporates into its response

---

## Implementation Considerations

### Security

**API Keys:**
- Store securely (environment variables, secrets management)
- Rotate regularly
- Use different keys for different environments

**User Data:**
- Encrypt sensitive data (financial information)
- Implement access controls
- GDPR compliance for user data

**MCP Server:**
- Validate all tool inputs
- Rate limit tool calls
- Sandbox execution where possible

### Performance

**Caching:**
- Cache frequently accessed memories
- Cache stock quotes (with TTL)
- Use Redis for hot data

**Streaming:**
- Implement proper backpressure handling
- Use chunked responses for large data
- Optimize 3D rendering performance

**Database:**
- Index frequently queried fields
- Use connection pooling
- Implement query optimization

### Scalability

**Horizontal Scaling:**
- Stateless API servers (can scale horizontally)
- Use load balancer
- Shared Redis/PostgreSQL for state

**MCP Server:**
- Can run as separate service
- Multiple instances behind load balancer
- Consider MCP server per tool for isolation

### Error Handling

**Graceful Degradation:**
- Fallback when MCP tools unavailable
- Continue conversation without tools if needed
- User-friendly error messages

**Retry Logic:**
- Exponential backoff for API calls
- Retry failed tool calls
- Circuit breaker pattern for external services

### Testing

**Unit Tests:**
- Test each MCP tool independently
- Mock external APIs
- Test error scenarios

**Integration Tests:**
- Test MCP Server integration
- Test agentic-memories integration
- Test end-to-end flows

**E2E Tests:**
- Test complete user flows
- Test voice interactions
- Test 3D animations

### Monitoring

**Metrics:**
- Tool call latency
- Memory retrieval performance
- LLM response times
- User engagement metrics

**Logging:**
- Structured logging (JSON)
- Log all tool calls
- Log errors with context

**Observability:**
- Langfuse for LLM tracing
- Distributed tracing (OpenTelemetry)
- Real-time dashboards

---

## Implementation Timeline & Milestones

> **Note**: Detailed implementation timeline and phases are documented in [V1 Implementation Plan](../04-implementation/V1_IMPLEMENTATION_PLAN.md).

### V1 Implementation (10 Weeks)

The current V1 implementation follows a 5-phase approach over 10 weeks:

- **Phase 1: Foundation** (Week 1-2) - Docker setup and MCP server foundation
- **Phase 2: Core Backend** (Week 3-4) - Backend API with LLM integration
- **Phase 3: MCP Tools** (Week 5-6) - Internet Access and Memories tools
- **Phase 4: Telegram Bot** (Week 7-8) - Telegram interface implementation
- **Phase 5: Integration & Testing** (Week 9-10) - End-to-end integration and testing

**V1 Scope**: Telegram bot only. Web interface, iOS app, and A2A protocol are deferred to future versions (V1.1, V1.2, V2.1).

**Future Roadmap**: See [Future Features Plan](../01-product/FUTURE_FEATURES_PLAN.md) for V1.1+ features.

### Critical Path Dependencies

```
MCP Server → Backend API → Telegram Bot
     ↓            ↓              ↓
  Tools      LLM Integration   Testing
     ↓            ↓              ↓
  Memories    Streaming      Deployment
```

**Total Timeline**: 10 weeks for V1 MVP

---

## Resources

### MCP Documentation
- MCP Specification: [Anthropic MCP Docs](https://modelcontextprotocol.io)
- Python SDK: `@modelcontextprotocol/sdk-python`
- TypeScript SDK: `@modelcontextprotocol/sdk-typescript`

### agentic-memories
- Repository: `/Users/Ankit/dev/agentic-memories`
- API Documentation: `http://localhost:8080/docs` (when running)
- Integration Guide: `CHATBOT_INTEGRATION_GUIDE.md`

### Stock APIs
- Alpha Vantage: https://www.alphavantage.co
- Polygon.io: https://polygon.io
- Finnhub: https://finnhub.io
- Yahoo Finance API: Various open-source wrappers

### 3D Animation
- Three.js: https://threejs.org
- React Three Fiber: https://docs.pmnd.rs/react-three-fiber
- Animation libraries: GSAP, Lottie

---

**Note**: This research summary provides a comprehensive foundation for building Annie. The next phase would involve detailed design documents and implementation plans for each component.

