# Strategic Questions for Annie Project

## 1. TARGET STATE UNDERSTANDING

### Vision & Purpose
**Q1.1**: What is the ultimate vision for Annie? 
- Personal project for learning/experimentation?
- Open-source tool for the community?
- Commercial product/service?
- Portfolio/demo project?

**Q1.2**: What does "success" look like beyond the metrics?
- Is it about proving the architecture works?
- Building a user base?
- Demonstrating MCP capabilities?
- Creating a production-ready service?

**Q1.3**: How closely should Annie match Grok's Annie?
- Exact feature parity?
- Inspired by but with your own direction?
- Different use cases but similar UX?
- What are the key differentiators?

### User Experience
**Q1.4**: What should the user experience feel like?
- Casual conversation companion?
- Productivity assistant?
- Technical tool for developers?
- Mix of all three?

**Q1.5**: What's the personality/character of Annie?
- Friendly and casual?
- Professional and efficient?
- Playful and gamified?
- Adaptive based on user?

## 2. V1 vs V2 DEFINITION

### Version Boundaries
**Q2.1**: What is the actual V2 definition?
- Currently: V1.1 (Web), V1.2 (iOS), V2.0 (Advanced), V2.1 (A2A), V3.0 (AI)
- Should V2 be: "Everything after V1" or specific milestone?
- What makes V2 different from V1.1/V1.2?

**Q2.2**: What's the minimum viable V1?
- Is it: "User can chat via Telegram with memory and internet access"?
- Or does it need: Stock Trader persona, PostgreSQL, full error handling?
- What can be deferred to V1.1 without breaking the core value?

**Q2.3**: Stock Trader Persona - V1 or V2?
- Mentioned in Product Requirements as V1 goal
- Not detailed in V1 Implementation Plan
- Is this a core V1 feature or nice-to-have?
- How does it work? Separate mode? Always available?

### Database Strategy
**Q2.4**: PostgreSQL - V1 or V2?
- Architecture mentions PostgreSQL but says "Future"
- V1 Implementation Plan mentions Redis + PostgreSQL
- Is PostgreSQL required for V1 or can Redis-only work?
- What data MUST persist vs. can be ephemeral?

### Feature Prioritization
**Q2.5**: What features are MUST-HAVE for V1 vs. NICE-TO-HAVE?
- Must-have: Telegram bot, LLM chat, Memory storage/retrieval, Internet search?
- Nice-to-have: Stock Trader persona, PostgreSQL persistence, Advanced error handling?
- What's the bare minimum that still delivers value?

## 3. V1 TASK BREAKDOWN

### Task Granularity
**Q3.1**: Are tasks granular enough for implementation?
- Current tasks are high-level (e.g., "Implement LLM Client")
- Should each task be broken into: Design → Implement → Test → Document?
- What's the ideal task size? (1-2 days? 1 week?)

**Q3.2**: What are the critical dependencies?
- Can MCP Server be built independently of Backend?
- Does Telegram Bot need Backend API complete first?
- Can tools be developed in parallel?
- What's the critical path?

**Q3.3**: Testing integration into phases?
- Current plan has testing in Phase 5 only
- Should each phase include: Unit tests → Integration tests?
- What's the testing strategy per component?
- How do we know each phase is "done"?

### Stock Trader Persona
**Q3.4**: How should Stock Trader persona work?
- Is it a separate mode users activate?
- Always available as a tool?
- Different LLM prompts/system messages?
- Does it need separate MCP tool or use existing ones?
- What's the implementation approach?

### Error Handling & Resilience
**Q3.5**: How robust should V1 be?
- Basic error handling or production-grade?
- What happens if agentic-memories is down?
- What happens if LLM API fails?
- What happens if MCP server crashes?
- Should V1 handle all edge cases or focus on happy path?

### State Management
**Q3.6**: What state needs to persist in V1?
- Conversation history: Redis-only OK or need PostgreSQL?
- User preferences: Needed in V1?
- Affection scores: V1 or V2?
- Session data: How long should it persist?

## 4. TECHNICAL DECISIONS

### MCP Communication
**Q4.1**: Docker exec pattern - is this production-ready?
- Works for V1 but what about scaling?
- Should we plan HTTP bridge from the start?
- What's the performance impact?
- Is this a V1 compromise or long-term solution?

### LLM Integration
**Q4.2**: LLM provider strategy - is fallback automatic?
- How do we detect when to fallback?
- What triggers fallback? (Error? Timeout? Rate limit?)
- Should fallback be transparent to user?
- What about cost differences between providers?

### Streaming
**Q4.3**: SSE vs WebSocket - is SSE sufficient?
- SSE is one-way (server → client)
- Telegram Bot needs to poll for responses?
- Should we plan WebSocket upgrade path?
- What's the user experience difference?

## 5. OPERATIONAL CONCERNS

### Deployment
**Q5.1**: What's the deployment target?
- Local development only?
- Cloud deployment (AWS/GCP/Azure)?
- Self-hosted server?
- Docker Compose sufficient or need Kubernetes?

### Monitoring & Observability
**Q5.2**: What monitoring is needed for V1?
- Basic health checks sufficient?
- Need metrics/alerting?
- Logging strategy?
- Error tracking?

### Cost Management
**Q5.3**: How do we manage API costs?
- Rate limiting per user?
- Cost tracking?
- Budget alerts?
- Usage quotas?

## 6. SUCCESS CRITERIA

### Definition of Done
**Q6.1**: What does "V1 Complete" mean?
- All features working end-to-end?
- Tests passing?
- Documentation complete?
- Deployed and running?
- Users can actually use it?

**Q6.2**: How do we validate V1 is successful?
- Manual testing sufficient?
- Need automated E2E tests?
- User acceptance testing?
- Performance benchmarks?

## NEXT STEPS

After answering these questions, we can:
1. **Refine Target State**: Clear vision document
2. **Define V1 & V2**: Clear boundaries and scope
3. **Break Down V1**: Granular, actionable tasks with dependencies

