# annie - Sprint Plan

**Author:** Ankit  
**Date:** 2025-11-10  
**Project:** annie V1.0 MVP  
**Sprint Duration:** 1-2 weeks per sprint  
**Total Duration:** ~10 weeks (5 sprints)

---

## Overview

This sprint plan organizes the 24 stories from the [Epic and Story Breakdown](./epics-and-stories.md) into manageable sprints, considering dependencies, parallelization opportunities, and team capacity.

**Planning Assumptions:**
- **Sprint Duration:** 1-2 weeks per sprint
- **Team Capacity:** 1-2 developers (can scale)
- **Story Points:** Using Fibonacci scale (1, 2, 3, 5, 8)
- **Sprint Capacity:** ~8-13 points per sprint (1 developer) or ~16-26 points (2 developers)
- **Parallelization:** Stories can run in parallel when dependencies allow

**Total Effort:**
- **Total Stories:** 24 stories
- **Total Story Points:** ~60 points
- **Estimated Duration:** ~10 weeks (5 sprints)

---

## Sprint Breakdown

### Sprint 1: Foundation & Infrastructure Setup
**Duration:** 2 weeks  
**Sprint Goal:** Establish development environment and foundational infrastructure  
**Capacity:** 13 points (1 developer) or 26 points (2 developers)

#### Stories

| Story ID | Story Title | Points | Priority | Dependencies |
|----------|-------------|--------|----------|--------------|
| 1.1 | Project Structure & Repository Setup | 2 | P0 | None |
| 1.2 | Docker Compose & Service Configuration | 3 | P0 | 1.1 |
| 1.3 | Environment Configuration & Secrets Management | 2 | P0 | 1.1 |
| 1.4 | Logging Infrastructure | 2 | P1 | 1.2 |
| 1.5 | Operational Scripts & Makefile | 2 | P1 | 1.2, 1.3 |
| 1.6 | MCP Server Foundation | 3 | P0 | 1.2, 1.4 |

**Total Points:** 14 points

**Parallelization Opportunities:**
- Stories 1.3 and 1.4 can run in parallel (after 1.1, 1.2)
- Story 1.5 can start once 1.2 and 1.3 are complete

**Sprint Deliverables:**
- ✅ Complete project structure
- ✅ Docker Compose with all services running
- ✅ Environment configuration system
- ✅ Structured logging across services
- ✅ Operational scripts (Makefile, run_docker.sh)
- ✅ Working MCP server with health check tool

**Definition of Done:**
- All Docker services start successfully
- Health checks pass for all services
- Environment variables properly configured
- Logging works across all services
- MCP server responds to tool calls

**Risks & Mitigations:**
- **Risk:** Docker setup complexity
  - **Mitigation:** Start early, test frequently, document issues
- **Risk:** Environment configuration errors
  - **Mitigation:** Create comprehensive env.example, validate early

---

### Sprint 2: Core Backend & LLM Integration
**Duration:** 2 weeks  
**Sprint Goal:** Implement backend API with LLM integration and streaming support  
**Capacity:** 13 points (1 developer) or 26 points (2 developers)

#### Stories

| Story ID | Story Title | Points | Priority | Dependencies |
|----------|-------------|--------|----------|--------------|
| 2.1 | Backend API Foundation | 2 | P0 | 1.2, 1.4 |
| 2.2 | LLM Client Setup & Provider Management | 3 | P0 | 2.1 |
| 2.3 | SSE Streaming Support | 3 | P0 | 2.2 |
| 2.4 | Function Calling for MCP Tools | 3 | P0 | 2.2, 1.6 |
| 2.5 | Conversation State Management | 3 | P1 | 2.1 |
| 2.6 | Error Handling Patterns | 2 | P1 | 2.1, 2.2 |

**Total Points:** 16 points

**Parallelization Opportunities:**
- Story 2.5 can run in parallel with 2.2-2.4 (only needs 2.1)
- Story 2.6 can run in parallel with 2.3-2.5 (needs 2.1, 2.2)

**Sprint Deliverables:**
- ✅ FastAPI backend with health checks
- ✅ LLM client with Grok-4 and ChatGPT-5 support
- ✅ SSE streaming for real-time responses
- ✅ Function calling for MCP tools
- ✅ Redis-based conversation state management
- ✅ Comprehensive error handling patterns

**Definition of Done:**
- Backend API responds to requests
- LLM streaming works end-to-end
- Function calling enables tool invocation
- Conversation state persists in Redis
- Error handling provides graceful degradation

**Risks & Mitigations:**
- **Risk:** LLM API integration complexity
  - **Mitigation:** Start with simple API calls, add streaming incrementally
- **Risk:** Streaming performance issues
  - **Mitigation:** Test early, optimize connection management
- **Risk:** MCP client Docker exec complexity
  - **Mitigation:** Build on MCP server foundation from Sprint 1

---

### Sprint 3: Memory & Decision Support Tools
**Duration:** 2 weeks  
**Sprint Goal:** Integrate persistent memory and implement decision support tools  
**Capacity:** 13 points (1 developer) or 26 points (2 developers)

#### Stories

| Story ID | Story Title | Points | Priority | Dependencies |
|----------|-------------|--------|----------|--------------|
| 3.1 | Memory Storage Integration | 3 | P0 | 2.4, 1.6 |
| 3.2 | Memory Retrieval for Decision Support | 2 | P0 | 3.1 |
| 4.1 | Internet Access Tool | 2 | P0 | 2.4, 1.6 |
| 4.2 | Stock Trader Tool - Market Analysis | 4 | P0 | 2.4, 1.6 |
| 4.3 | Stock Trader Tool - Personalized Recommendations | 2 | P1 | 4.2, 3.2 |

**Total Points:** 13 points

**Parallelization Opportunities:**
- Stories 3.1, 4.1, and 4.2 can run in parallel (all need 2.4, 1.6)
- Story 3.2 depends on 3.1
- Story 4.3 depends on 4.2 and 3.2

**Sprint Deliverables:**
- ✅ agentic-memories integration for storage and retrieval
- ✅ Internet Access tool (Brave Search)
- ✅ Stock Trader tool with market analysis
- ✅ Personalized stock recommendations using memory

**Definition of Done:**
- Memories are stored after conversations
- Relevant memories are retrieved for decision support
- Internet search provides real-time information
- Stock analysis provides actionable insights
- Tools integrate seamlessly with LLM function calling

**Risks & Mitigations:**
- **Risk:** agentic-memories service availability
  - **Mitigation:** Implement graceful degradation, test with mock service
- **Risk:** External API rate limits (Brave Search, Stock API)
  - **Mitigation:** Implement rate limiting, add retry logic, handle errors gracefully
- **Risk:** Stock API selection and integration
  - **Mitigation:** Research APIs early, choose reliable provider, have fallback

---

### Sprint 4: Telegram Bot Interface
**Duration:** 2 weeks  
**Sprint Goal:** Implement Telegram bot with streaming responses and error handling  
**Capacity:** 7 points (1 developer) or 14 points (2 developers)

#### Stories

| Story ID | Story Title | Points | Priority | Dependencies |
|----------|-------------|--------|----------|--------------|
| 5.1 | Telegram Bot Setup & Message Reception | 2 | P0 | 2.1, 1.2 |
| 5.2 | Streaming Response Delivery | 3 | P0 | 5.1, 2.3 |
| 5.3 | Message Formatting & Error Handling | 2 | P1 | 5.2 |

**Total Points:** 7 points

**Parallelization Opportunities:**
- Stories run sequentially due to dependencies

**Sprint Deliverables:**
- ✅ Telegram bot that receives messages
- ✅ Streaming responses to users
- ✅ Proper message formatting
- ✅ User-friendly error handling

**Definition of Done:**
- Users can send messages via Telegram
- Bot responds with streaming text
- Messages are properly formatted
- Error handling is user-friendly
- Bot handles 100+ concurrent users

**Risks & Mitigations:**
- **Risk:** Telegram API rate limits
  - **Mitigation:** Implement rate limiting, handle errors gracefully
- **Risk:** Streaming performance with Telegram
  - **Mitigation:** Optimize message batching, test with long responses
- **Risk:** Message formatting complexity
  - **Mitigation:** Test markdown rendering early, handle edge cases

---

### Sprint 5: Integration, Testing & Documentation
**Duration:** 2 weeks  
**Sprint Goal:** Ensure all components work together, meet quality standards, and are ready for deployment  
**Capacity:** 13 points (1 developer) or 26 points (2 developers)

#### Stories

| Story ID | Story Title | Points | Priority | Dependencies |
|----------|-------------|--------|----------|--------------|
| 6.1 | End-to-End Integration | 3 | P0 | Epics 1-5 complete |
| 6.2 | Unit & Integration Testing | 4 | P0 | 6.1 |
| 6.3 | Error Scenario & Performance Testing | 3 | P0 | 6.2 |
| 6.4 | Documentation & Deployment Readiness | 3 | P0 | 6.3 |

**Total Points:** 13 points

**Parallelization Opportunities:**
- Stories run sequentially due to dependencies

**Sprint Deliverables:**
- ✅ Complete end-to-end integration
- ✅ Comprehensive test coverage (80%+)
- ✅ Performance requirements met
- ✅ Complete documentation
- ✅ Production-ready deployment

**Definition of Done:**
- All components integrated successfully
- Test coverage meets targets (80%+)
- Performance requirements met (<500ms first token, <5s tool calls)
- Documentation complete and up-to-date
- System ready for production deployment

**Risks & Mitigations:**
- **Risk:** Integration issues discovered late
  - **Mitigation:** Start integration testing early, fix issues incrementally
- **Risk:** Performance bottlenecks
  - **Mitigation:** Performance test early, identify and fix bottlenecks
- **Risk:** Documentation completeness
  - **Mitigation:** Document as you go, review documentation early

---

## Sprint Timeline Summary

| Sprint | Duration | Stories | Points | Focus Area |
|--------|----------|---------|--------|------------|
| Sprint 1 | 2 weeks | 6 stories | 14 pts | Foundation & Infrastructure |
| Sprint 2 | 2 weeks | 6 stories | 16 pts | Core Backend & LLM |
| Sprint 3 | 2 weeks | 5 stories | 13 pts | Memory & Tools |
| Sprint 4 | 2 weeks | 3 stories | 7 pts | Telegram Bot |
| Sprint 5 | 2 weeks | 4 stories | 13 pts | Integration & Quality |
| **Total** | **10 weeks** | **24 stories** | **63 pts** | **V1.0 MVP** |

---

## Parallelization Strategy

### Sprint 1 Parallelization
```
Week 1:
  Day 1-2: Story 1.1 (Project Structure)
  Day 3-5: Story 1.2 (Docker Compose) [blocks others]
  
Week 2:
  Day 1-2: Story 1.3 (Environment Config) || Story 1.4 (Logging) [parallel]
  Day 3-4: Story 1.5 (Operational Scripts) [after 1.3]
  Day 5-7: Story 1.6 (MCP Server) [after 1.4]
```

### Sprint 2 Parallelization
```
Week 1:
  Day 1-2: Story 2.1 (Backend API Foundation)
  Day 3-5: Story 2.2 (LLM Client Setup)
  
Week 2:
  Day 1-3: Story 2.3 (Streaming) || Story 2.4 (Function Calling) [parallel after 2.2]
  Day 1-3: Story 2.5 (Conversation State) [parallel, only needs 2.1]
  Day 4-5: Story 2.6 (Error Handling) [after 2.2]
```

### Sprint 3 Parallelization
```
Week 1:
  Day 1-3: Story 3.1 (Memory Storage) || Story 4.1 (Internet Tool) || Story 4.2 (Stock Analysis) [parallel]
  
Week 2:
  Day 1-2: Story 3.2 (Memory Retrieval) [after 3.1]
  Day 3-4: Story 4.3 (Personalized Recommendations) [after 4.2, 3.2]
```

---

## Capacity Planning

### Single Developer Scenario
- **Sprint Capacity:** ~8-13 points per sprint
- **Total Duration:** ~10 weeks
- **Buffer:** 20% buffer for unexpected issues
- **Risk:** Higher risk of delays, limited parallelization

### Two Developer Scenario
- **Sprint Capacity:** ~16-26 points per sprint
- **Total Duration:** ~6-8 weeks (with parallelization)
- **Buffer:** 15% buffer for coordination overhead
- **Benefit:** Better parallelization, faster delivery

### Recommended Approach
- **Start:** Single developer for Sprints 1-2 (foundation)
- **Scale:** Add second developer for Sprints 3-5 (features + testing)
- **Rationale:** Foundation requires sequential work, features benefit from parallelization

---

## Risk Management

### High-Risk Stories

1. **Story 1.2: Docker Compose & Service Configuration**
   - **Risk:** Complex Docker setup, networking issues
   - **Mitigation:** Start early, test frequently, document issues
   - **Contingency:** Simplify Docker setup, use local development mode

2. **Story 2.4: Function Calling for MCP Tools**
   - **Risk:** Docker exec pattern complexity, MCP protocol issues
   - **Mitigation:** Build on MCP server foundation, test incrementally
   - **Contingency:** Use alternative MCP transport (HTTP instead of stdio)

3. **Story 4.2: Stock Trader Tool - Market Analysis**
   - **Risk:** External API reliability, rate limits, data quality
   - **Mitigation:** Research APIs early, implement fallbacks, handle errors gracefully
   - **Contingency:** Use multiple API providers, implement caching

4. **Story 6.3: Error Scenario & Performance Testing**
   - **Risk:** Performance bottlenecks discovered late
   - **Mitigation:** Performance test early, optimize incrementally
   - **Contingency:** Extend sprint if needed, prioritize critical performance issues

### Dependencies on External Services

- **agentic-memories:** Required for memory features
  - **Risk:** Service unavailable or slow
  - **Mitigation:** Implement graceful degradation, retry logic, local caching

- **Grok-4 API / ChatGPT-5:** Required for LLM functionality
  - **Risk:** API failures, rate limits, cost overruns
  - **Mitigation:** Implement fallback, rate limiting, cost monitoring

- **Brave Search API:** Required for internet access
  - **Risk:** Rate limits, API changes
  - **Mitigation:** Implement rate limiting, error handling, fallback to alternative search

- **Stock API:** Required for stock analysis
  - **Risk:** API reliability, data quality, cost
  - **Mitigation:** Choose reliable provider, implement fallbacks, monitor costs

---

## Success Metrics

### Sprint-Level Metrics
- **Velocity:** Story points completed per sprint
- **Burndown:** Story points remaining over time
- **Quality:** Test coverage, bug count, code review feedback

### Release-Level Metrics
- **On-Time Delivery:** V1.0 MVP delivered within 10 weeks
- **Quality:** 80%+ test coverage, <1% error rate
- **Performance:** <500ms first token latency, <5s tool calls
- **User Satisfaction:** Functional Telegram bot with streaming responses

---

## Definition of Ready (DoR)

A story is ready for sprint planning when:
- ✅ Story has clear acceptance criteria
- ✅ Story has estimated effort (story points)
- ✅ Dependencies are identified
- ✅ Technical approach is understood
- ✅ Story is small enough to complete in sprint (<5 points)

---

## Definition of Done (DoD)

A story is done when:
- ✅ All acceptance criteria are met
- ✅ Code is written and reviewed
- ✅ Unit tests are written and passing
- ✅ Integration tests pass (if applicable)
- ✅ Documentation is updated
- ✅ Code is merged to main branch
- ✅ No critical bugs remain

---

## Sprint Ceremonies

### Sprint Planning (Start of Sprint)
- Review sprint goal and stories
- Identify dependencies and risks
- Assign stories to developers
- Plan parallelization opportunities

### Daily Standup (Daily)
- What did I complete yesterday?
- What will I work on today?
- Are there any blockers?

### Sprint Review (End of Sprint)
- Demo completed stories
- Gather feedback
- Update sprint metrics

### Sprint Retrospective (End of Sprint)
- What went well?
- What could be improved?
- Action items for next sprint

---

## Next Steps

1. **Review Sprint Plan** - Validate timeline, capacity, and dependencies
2. **Generate Sprint Status File** - Use `sprint-planning` workflow to create tracking file
3. **Begin Sprint 1** - Start with Story 1.1 (Project Structure & Repository Setup)
4. **Track Progress** - Update sprint status as stories progress

---

_This sprint plan organizes the epic/story breakdown into manageable sprints with clear goals, timelines, and success criteria._

_For tracking: Use the `sprint-planning` workflow to generate `sprint-status.yaml` for development tracking._
