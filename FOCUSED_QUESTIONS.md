# Focused Questions for Decision-Making Annie

Based on your vision: **Personal project for friends/relatives to make 80% of decisions and achieve prosperity**

## Decision-Making Focus

### Q1: What Types of Decisions?
**What categories of decisions should Annie help with?**

- [ ] **Financial Decisions**
  - Stock trading/investment advice
  - Budget planning
  - Major purchases (house, car)
  - Financial planning

- [ ] **Career Decisions**
  - Job offers/negotiations
  - Career transitions
  - Skill development
  - Professional opportunities

- [ ] **Life Decisions**
  - Personal relationships
  - Health choices
  - Education paths
  - Major life changes

- [ ] **Business Decisions**
  - Business opportunities
  - Partnerships
  - Strategic planning

**Which are priority for V1?**

### Q2: How Does "80% of Decisions" Work?
**What does this mean exactly?**

- [ ] **80% Accuracy**: Annie's recommendations are correct 80% of the time?
- [ ] **80% Coverage**: Annie helps with 80% of user's decision types?
- [ ] **80% Trust**: Users follow Annie's advice 80% of the time?
- [ ] **80% Satisfaction**: Users are satisfied with 80% of recommendations?

**How do we measure this?**

### Q3: Decision-Making Process
**How should Annie help users make decisions?**

- [ ] **Analysis**: Analyze options and provide pros/cons
- [ ] **Recommendation**: Give clear recommendation with reasoning
- [ ] **Research**: Gather real-time information to inform decision
- [ ] **Memory**: Remember past decisions and outcomes
- [ ] **Learning**: Learn from user's decision patterns

**What's the ideal decision-making flow?**

Example:
```
User: "Should I invest in Tesla stock?"
Annie: 
1. Searches current Tesla market data
2. Analyzes user's risk profile (from memory)
3. Reviews user's past investment decisions
4. Provides pros/cons analysis
5. Makes recommendation with reasoning
```

### Q4: Stock Trader Persona - V1 or V2?
**Is Stock Trader persona core to V1?**

- [ ] **V1 Core**: Essential for financial decision-making
- [ ] **V1 Nice-to-Have**: Can add later
- [ ] **V2**: Defer to future version

**What should Stock Trader persona do?**
- [ ] Real-time stock analysis
- [ ] Portfolio recommendations
- [ ] Market trend analysis
- [ ] Risk assessment
- [ ] Investment strategy advice

## V1 vs V2 Boundaries

### Q5: Minimum Viable V1
**What's the absolute minimum for V1 to deliver value?**

**Must Have:**
- [ ] Telegram bot working
- [ ] LLM chat with streaming
- [ ] Memory storage/retrieval
- [ ] Internet search for real-time data
- [ ] Basic decision analysis (pros/cons)

**Nice to Have:**
- [ ] Stock Trader persona
- [ ] Advanced decision frameworks
- [ ] PostgreSQL persistence
- [ ] Decision outcome tracking
- [ ] Multiple decision types

**What can wait for V1.1?**

### Q6: V2 Definition
**What makes V2 different from V1.1/V1.2?**

**Current Plan:**
- V1: Telegram bot + MCP tools + Memory
- V1.1: Web interface + 3D avatar
- V1.2: iOS app
- V2.0: Advanced features (voice, gamification)
- V2.1: A2A protocol

**Should V2 be:**
- [ ] **Everything after V1** (V1.1, V1.2, V2.0 all = V2)
- [ ] **Major milestone** (e.g., "Decision-making platform complete")
- [ ] **Specific features** (e.g., "Advanced decision frameworks")

**What's your V2 vision?**

## Technical Decisions

### Q7: Database Strategy
**What data MUST persist in V1?**

- [ ] **Conversation History**: Needed for decision context?
- [ ] **Decision Records**: Track decisions and outcomes?
- [ ] **User Preferences**: Risk profile, decision patterns?
- [ ] **Outcomes**: Did decisions work out? (for learning)

**Can Redis-only work for V1, or need PostgreSQL?**

### Q8: Decision Tracking
**Should V1 track decision outcomes?**

- [ ] **Yes**: Learn from what worked/didn't work
- [ ] **No**: V1 just provides advice, tracking comes later
- [ ] **Basic**: Simple feedback (good/bad), detailed tracking later

**How do users provide feedback on decisions?**

### Q9: Error Handling Robustness
**How robust should V1 be?**

- [ ] **Basic**: Handle happy path, graceful errors
- [ ] **Production-Grade**: Handle all edge cases, fallbacks
- [ ] **Personal Project**: Focus on features, polish later

**What happens if:**
- agentic-memories is down?
- LLM API fails?
- Internet search fails?
- User makes bad decision despite advice?

## Task Breakdown

### Q10: Stock Trader Implementation
**How should Stock Trader persona work in V1?**

**Option A: Separate MCP Tool**
- New tool: `stock_analysis`
- Called when user asks about stocks
- Provides analysis and recommendations

**Option B: LLM Prompt Engineering**
- System prompt includes stock trading expertise
- Uses existing internet_search tool
- No separate tool needed

**Option C: Hybrid**
- Basic analysis via LLM + internet search
- Advanced features via dedicated tool (V2)

**Which approach for V1?**

### Q11: Decision Framework
**Should V1 include structured decision frameworks?**

- [ ] **Yes**: Pros/cons templates, decision matrices
- [ ] **No**: Let LLM handle naturally
- [ ] **Basic**: Simple pros/cons, advanced frameworks later

**Examples:**
- Pros/Cons analysis
- Decision matrix (weighted criteria)
- Risk/Reward assessment
- Scenario planning

### Q12: Task Granularity
**How detailed should V1 tasks be?**

**Current**: High-level (e.g., "Implement LLM Client")

**Should we break down to:**
- [ ] **1-2 day tasks**: Very granular, clear deliverables
- [ ] **1 week tasks**: Medium granularity, multiple sub-tasks
- [ ] **2 week phases**: Current approach, add sub-tasks

**Example breakdown:**
```
Phase 2: Core Backend (Week 3-4)
├── Task 2.1: Backend API Setup (2 days)
│   ├── Create FastAPI app structure
│   ├── Add health check endpoint
│   ├── Set up routing
│   └── Add error handling
├── Task 2.2: LLM Client (3 days)
│   ├── Unified client interface
│   ├── Grok-4 integration
│   ├── ChatGPT-5 fallback
│   └── Streaming support
└── ...
```

## Next Steps

**Please answer these questions, especially:**
1. **Q1**: What decision types are priority?
2. **Q2**: What does "80% of decisions" mean?
3. **Q5**: What's minimum V1?
4. **Q10**: How should Stock Trader work?

Then we can:
1. ✅ **Refine Vision**: Update product requirements
2. ✅ **Define V1 & V2**: Clear boundaries and scope
3. ✅ **Break Down V1**: Granular, actionable tasks

