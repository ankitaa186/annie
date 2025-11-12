# Product Requirements

## Product Vision

Annie is a personal AI companion chatbot inspired by Grok's Annie, designed to help friends and relatives make better decisions and achieve prosperity. The goal is to enable Annie to assist with 80% of users' day-to-day decisions, with users trusting Annie's advice 80% of the time, bringing enormous prosperity through intelligent, context-aware advice powered by real-time information, persistent memory, and specialized decision-making tools.

**Core Mission**: Empower users to make better decisions through AI-powered analysis, recommendations, and real-time information access.

## Core Value Proposition

- **Decision-Making Support**: AI-powered analysis and recommendations for 80% of day-to-day decisions, with 80% user trust
- **Prosperity Focus**: Specialized tools for financial, career, life, and business decisions
- **Intelligent Conversations**: Advanced LLM integration (Grok-4 primary, ChatGPT-5 fallback) with streaming responses
- **Persistent Memory**: Context-aware conversations powered by agentic-memories for personalized advice
- **Real-Time Information**: Internet access for current data to inform decisions
- **Extensible Tools**: MCP server architecture for decision-making tools (stock trading, analysis, etc.)
- **Multi-Platform Access**: Accessible via Telegram (V1), web interface (V1.1), iOS app (V1.2)

## Target Users

### Primary Personas

1. **Friends & Relatives (Primary Users)**
   - Need help making important life decisions
   - Want financial and career advice
   - Value personalized, context-aware recommendations
   - Trust AI-powered analysis for decision support

2. **Decision-Makers**
   - Face complex choices (financial, career, life)
   - Need real-time information and analysis
   - Want to understand pros/cons before deciding
   - Benefit from persistent memory of past decisions

3. **Tech-Savvy Users**
   - Comfortable with Telegram and technical tools
   - Want advanced capabilities and extensibility
   - Value MCP protocol integration

## Core User Stories

### V1 (MVP)

**As a user, I want to:**
- Get AI-powered recommendations for important decisions across all areas:
  - **Financial**: Stock trading, investments, budget planning, major purchases
  - **Career**: Job offers, career transitions, skill development, opportunities
  - **Life**: Personal relationships, health choices, education, major life changes
  - **Business**: Business opportunities, partnerships, strategic planning
- Access real-time information to inform my decisions
- Have Annie remember my past decisions and their outcomes
- Use Annie as a stock trading advisor with market analysis
- Receive pros/cons analysis for complex decisions
- Get personalized advice based on my history and preferences
- Chat with Annie via Telegram bot with streaming responses

**Decision-Making Process (Powered by agentic-memories):**
- **Analysis**: Annie analyzes options and provides pros/cons using memory context
- **Recommendation**: Annie gives clear recommendations with reasoning based on past decisions
- **Research**: Annie gathers real-time information via internet search to inform decisions
- **Memory**: Annie remembers past decisions, outcomes, and user preferences via agentic-memories
- **Learning**: Annie learns from user's decision patterns stored in agentic-memories

**As a developer, I want to:**
- Integrate Annie via MCP protocol
- Extend Annie with custom tools
- Access Annie via API
- Understand Annie's architecture

### V1.1+ (Future)

**As a user, I want to:**
- Access Annie via web browser
- See a 3D animated avatar
- Use voice input/output
- Access Annie via iOS app
- Use Annie through Claude/Gemini via A2A protocol

## Success Metrics

### V1 Success Metrics

- **Decision Coverage**: Annie helps with 80%+ of users' day-to-day decisions
- **Trust Level**: Users trust Annie's advice 80%+ of the time
- **Decision Quality**: Users report 80%+ satisfaction with Annie's recommendations
- **Prosperity Impact**: Measurable positive outcomes from Annie's advice (tracked via user feedback)
- **Engagement**: Average 15+ messages per user per day (higher than casual chat)
- **Reliability**: 99%+ uptime for decision-critical moments
- **Performance**: <2s response time (p95) for timely decisions
- **Memory Accuracy**: 90%+ relevant memory retrieval for personalized advice

### Technical Metrics

- **API Response Time**: <500ms (p95)
- **MCP Tool Execution**: <1s average
- **Memory Retrieval**: <300ms average
- **Error Rate**: <1% of requests

## Product Goals

### Short-term (V1.0)
1. ✅ Functional Telegram bot with core chat
2. ✅ MCP server with Internet Access and Memories tools
3. ✅ LLM integration with streaming
4. ✅ Persistent memory via agentic-memories (Redis-only)
5. ✅ Stock Trader persona with market analysis
6. ✅ Basic decision-making support (pros/cons analysis)

### Medium-term (V1.1 - V1.2)
1. Web interface with 3D avatar (V1.1)
2. iOS native app (V1.2)
3. Enhanced decision frameworks
4. Voice interaction

### Long-term (V2.0+)
1. PostgreSQL database for persistent storage
2. Multi-modality (images, voice understanding)
3. A2A protocol integration (V2.1)
4. Advanced AI features (fine-tuning, personalization)
5. Advanced gamification
6. Multi-persona support

## Non-Goals (Out of Scope)

### V1.0
- ❌ Web interface (deferred to V1.1)
- ❌ iOS app (deferred to V1.2)
- ❌ PostgreSQL database (deferred to V2.0)
- ❌ 3D animation (deferred to V1.1)
- ❌ Voice interaction (deferred to V1.2)
- ❌ Multi-modality (deferred to V2.0)
- ❌ A2A protocol (deferred to V2.1)
- ❌ Advanced gamification (deferred to V2.0)

### General
- ❌ User authentication/accounts (V1 uses Telegram auth)
- ❌ Payment processing
- ❌ Multi-tenant SaaS features
- ❌ Admin dashboard (V1)

## Constraints

### Technical Constraints
- Must run in Docker containers
- Must integrate with existing agentic-memories service
- Must support MCP protocol standards
- Must work with Telegram Bot API limitations

### Business Constraints
- API costs (LLM, Brave Search) must be manageable
- Must be deployable on standard infrastructure
- Must maintain compatibility with agentic-memories

## Dependencies

### External Services
- **agentic-memories**: Required for memory features
- **XAI API**: Required for Grok-4
- **Telegram Bot API**: Required for Telegram interface
- **Brave Search API**: Required for internet access

### Internal Dependencies
- Docker and Docker Compose
- Python 3.12+
- Redis (for state management in V1.0)
- PostgreSQL (for persistent storage in V2.0)

## References

- [V1 Implementation Plan](../04-implementation/V1_IMPLEMENTATION_PLAN.md) - Technical implementation details
- [Future Features Plan](./FUTURE_FEATURES_PLAN.md) - Roadmap for V1.1+
- [Architecture Plan](../02-architecture/ARCHITECTURE_PLAN.md) - System architecture

