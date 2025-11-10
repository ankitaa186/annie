# V1.0 vs V2.0 Definition

## Version Strategy

Using semantic versioning with `.x` format:
- **V1.0**: Initial release (MVP)
- **V1.1**: Web interface
- **V1.2**: iOS app
- **V2.0**: Major milestone (database, multi-modality)
- **V2.1**: A2A protocol
- **V3.0**: Advanced AI features

## V1.0 Scope (Current Focus)

### ✅ Included

**Core Infrastructure:**
- MCP Server with tool hosting
- Backend API (FastAPI)
- Telegram Bot interface
- Docker containerization
- Redis state management

**MCP Tools:**
- Internet Access Tool (Brave Search)
- Memories Tool (agentic-memories integration)
- **Stock Trader Tool** (market analysis, recommendations)

**Decision Support:**
- Pros/cons analysis
- Real-time information gathering
- Personalized recommendations via memory
- LLM-powered decision assistance

**LLM Integration:**
- Grok-4 primary
- ChatGPT-5 fallback
- Streaming responses (SSE)
- Function calling for tools

### ❌ Deferred to V1.1+
- Web interface (V1.1)
- iOS app (V1.2)
- 3D animation (V1.1)
- Voice interaction (V1.2)

### ❌ Deferred to V2.0+
- **PostgreSQL database** (V2.0)
- **Multi-modality** (images, voice understanding) (V2.0)
- Advanced gamification (V2.0)
- A2A protocol (V2.1)

## V2.0 Definition

**V2.0 = Major Milestone: "Production-Ready Decision Platform"**

### Key Additions

1. **PostgreSQL Database**
   - Persistent conversation history
   - User preferences and profiles
   - Decision outcome tracking
   - Analytics and insights

2. **Multi-Modality**
   - Image understanding
   - Voice input/output
   - Multi-modal decision analysis
   - Document analysis

3. **Advanced Features**
   - Enhanced decision frameworks
   - Decision outcome learning
   - Advanced personalization
   - WebSocket support

4. **Production Readiness**
   - Scalability improvements
   - Advanced monitoring
   - Performance optimization
   - Enhanced error handling

## V1.0 Success Criteria

### Functional
- [ ] User can chat via Telegram
- [ ] Bot provides streaming responses
- [ ] Internet search works
- [ ] Memories stored and retrieved
- [ ] **Stock Trader provides market analysis**
- [ ] LLM uses tools appropriately
- [ ] Basic pros/cons analysis works

### Technical
- [ ] Redis state management working
- [ ] MCP tools callable
- [ ] Docker services running
- [ ] Error handling graceful
- [ ] Performance targets met

### Decision-Making
- [ ] Users can ask for decision help
- [ ] Annie provides pros/cons
- [ ] Real-time data informs decisions
- [ ] Memory provides context
- [ ] Stock analysis available

## V2.0 Success Criteria

### Functional
- [ ] PostgreSQL persistence working
- [ ] Multi-modal inputs supported
- [ ] Decision outcomes tracked
- [ ] Advanced frameworks available
- [ ] WebSocket bidirectional communication

### Technical
- [ ] Database migrations working
- [ ] Multi-modal processing pipeline
- [ ] Enhanced monitoring
- [ ] Production deployment ready

## Migration Path: V1.0 → V2.0

### Data Migration
- Redis data → PostgreSQL
- Conversation history preservation
- User preference migration
- Decision outcome tracking setup

### Feature Migration
- Add PostgreSQL alongside Redis
- Gradual migration of data
- Multi-modal features added incrementally
- Backward compatibility maintained

## Key Differences Summary

| Feature | V1.0 | V2.0 |
|---------|------|------|
| **Database** | Redis only | Redis + PostgreSQL |
| **Persistence** | Temporary (TTL) | Permanent |
| **Multi-Modality** | ❌ | ✅ |
| **Stock Trader** | ✅ | ✅ Enhanced |
| **Decision Tracking** | Basic | Advanced with outcomes |
| **Platforms** | Telegram only | Telegram + Web + iOS |
| **Voice** | ❌ | ✅ |

## References

- [V1 Implementation Plan](./V1_IMPLEMENTATION_PLAN.md) - Detailed V1.0 tasks
- [Future Features Plan](../01-product/FUTURE_FEATURES_PLAN.md) - V1.1+ roadmap
- [Product Requirements](../01-product/PRODUCT_REQUIREMENTS.md) - Overall vision

