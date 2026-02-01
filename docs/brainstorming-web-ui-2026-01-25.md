# Brainstorming Session Results

**Session Date:** 2026-01-25
**Facilitator:** BMad Master
**Participant:** Ankit

## Executive Summary

**Topic:** Annie Web UI - Responsive Web Application

**Session Goals:** Design a responsive web app UI for Annie that overcomes Telegram limitations, provides richer experience, and enables web/mobile accessibility.

**Techniques Used:** Role Playing, First Principles Thinking, SCAMPER Method

**Total Ideas Generated:** 17

### Key Themes Identified:

1. **Simplicity over innovation** - Start with proven patterns (Gemini), differentiate through personality not complexity
2. **Annie as presence** - Avatar, voice, "knows me" feel - she's a companion, not a tool
3. **Transparency builds trust** - Health status, LLM indicator, visible thinking states
4. **Multimodal is core** - Text, voice, files in; voice AND text out
5. **Power later, foundation first** - Memory browser, tool calling, proactive triggers are V2/V3

## Technique Sessions

### Role Playing (4 Perspectives)

**User Perspective:**
- Health status indicators with green dots at top
- Current LLM being used visible
- Conversation history sidebar (left)
- Standard agentic chat interface as foundation (Gemini-style)

**Annie Perspective:**
- Animated anime avatar with state-based animations
- States: idle, thinking, speaking, empathetic
- Voice output capability
- "She knows me" feel through memory integration

**Developer Perspective:**
- Deferred to Mary (Business Analyst) for technical analysis

**New User Perspective:**
- No onboarding - drop them directly into the experience
- Let Annie introduce herself naturally

### First Principles Thinking

**Non-Negotiables Identified:**
1. **Input:** Text, voice, files
2. **Output:** Voice AND text (always both)
3. **Context:** Conversation history accessible
4. **State:** Thinking/working indicator visible

**Nice-to-have:** Animated avatar (personality layer)

### SCAMPER Method

| Lens | Ideas Generated |
|------|-----------------|
| **Substitute** | Voice+text toggle input, animated avatar, contextual thinking indicators ("Annie is searching...") |
| **Combine** | Voice+text output together, thinking indicator embedded in avatar |
| **Adapt** | Gemini's layout as baseline |
| **Modify** | Add avatar, health status, file sharing; remove Google-specific features |
| **Put to Use** | Memory browser, tool calling UI |
| **Eliminate** | Model selector (Annie chooses her own LLM) |
| **Reverse** | Proactive triggers (Annie initiates contact) |

## Idea Categorization

### Immediate Opportunities (V1)

| # | Feature | Rationale |
|---|---------|-----------|
| 1 | Gemini-style layout | Proven baseline |
| 2 | Health status + LLM indicator | Simple, builds trust |
| 3 | Conversation sidebar | Essential navigation |
| 4 | Standard agentic chat | Core functionality |
| 5 | Text input | Non-negotiable |
| 6 | File upload | Already built (Epic 18) |
| 7 | Thinking/working indicator | Non-negotiable, simple to implement |
| 8 | No model selector | Less UI, not more |
| 9 | No onboarding | Drop them in |

### Future Innovations (V2)

| # | Feature | Rationale |
|---|---------|-----------|
| 1 | Voice input | Requires speech-to-text integration |
| 2 | Voice + text output | Web audio playback, leverage Home Assistant work |
| 3 | Animated anime avatar | Design/animation effort |
| 4 | Avatar states | Depends on avatar |
| 5 | "Knows me" UI touches | Memory integration polish |
| 6 | Memory browser | New UI surface, needs design |

### Moonshots (V3)

| # | Feature | Rationale |
|---|---------|-----------|
| 1 | Tool calling UI | Complex UX, user-initiated tools |
| 2 | Proactive triggers | Needs notification infrastructure, careful UX |

### Insights and Learnings

- Annie's web UI should feel like *opening a conversation with a friend who happens to have superpowers* - not like opening a productivity tool
- Gemini is a better baseline than Claude due to existing voice integration alignment
- Transparency (health status, LLM indicator, thinking states) is a differentiator for trust
- The avatar is key to transforming cold text into a companion with presence

## Action Planning

### Top 3 Priority Ideas

#### #1 Priority: Core Chat Interface

- **Rationale:** Foundation everything else builds on. Can't test voice or avatar without basic chat working.
- **Next steps:** Choose frontend framework, evaluate assistant-ui library vs custom, wire up to existing backend
- **Resources needed:** Frontend framework decision, Mary's technical analysis
- **Timeline:** V1

#### #2 Priority: Thinking/State Indicators

- **Rationale:** Non-negotiable for transparency, relatively simple to implement, high trust impact
- **Next steps:** Design contextual messages for each tool, implement streaming state updates
- **Resources needed:** Backend SSE event types for tool calls
- **Timeline:** V1

#### #3 Priority: Animated Avatar

- **Rationale:** Key personality differentiator, transforms Annie from text to presence
- **Next steps:** Commission or source anime avatar, define animation states, implement with Lottie
- **Resources needed:** Avatar design/assets, animation expertise
- **Timeline:** V2

## Reflection and Follow-up

### What Worked Well

- Role Playing quickly surfaced key perspectives
- SCAMPER systematically generated features from existing patterns
- First Principles distilled non-negotiables cleanly

### Areas for Further Exploration

- Avatar design and animation approach
- Voice I/O technical implementation
- Memory browser UX design

### Recommended Follow-up Techniques

- User journey mapping for specific flows
- Technical spike for voice input/output
- Competitive analysis of avatar implementations

### Questions That Emerged

- Should voice output be web TTS or route through Home Assistant?
- How to handle offline/degraded mode?
- What's the auth strategy for linking web users to Telegram users?

### Next Session Planning

- **Suggested topics:** Memory browser UX, Avatar design specs
- **Recommended timeframe:** After V1 core is built
- **Preparation needed:** Technical framework decision, initial V1 implementation

---

_Session facilitated using the BMAD brainstorming framework_

## Outcome

**Epic 20: Annie Web UI** created at `docs/epics/epic-20-web-ui.md` with 15 stories covering:
- V1: Core infrastructure, layout, chat, streaming, indicators (10-14 days)
- V2: Voice I/O, avatar, mobile PWA
- V3: Memory browser, tool calling UI, proactive triggers dashboard
