# Epic: Adaptive Context & Persona Modulation

> **Epic ID**: 19
> **Status**: Draft
> **Priority**: High
> **Estimated Effort**: 8-10 days
> **Dependencies**: agentic-memories narrative API, Epic 16 (Home Assistant)

---

## 1. Overview

### 1.1 Problem Statement

Annie currently operates with static context and persona regardless of conversation topic:

- **No Topic Awareness**: Annie doesn't adapt her communication style when shifting from finance to cooking to DIY projects
- **No Narrative Context**: Individual memories are retrieved but not synthesized into coherent user understanding
- **Static Retrieval**: Memory retrieval uses fixed persona weights regardless of topic relevance
- **No Session Rehydration**: Each conversation starts without holistic user context
- **No Environment Integration**: Topic-relevant tools (Home Assistant, portfolio) aren't prioritized based on context

This results in generic responses that don't leverage the rich user knowledge stored in agentic-memories.

### 1.2 Solution

Implement an **Adaptive Context System** with four interconnected components:

1. **Narrative Integration**: Fetch synthesized user narratives from agentic-memories for session initialization and topic-specific context
2. **Topic Detection**: Classify conversation topics to trigger context adaptation
3. **Persona Modulation**: Dynamically adjust Annie's communication style based on detected topic
4. **Retrieval Optimization**: Switch memory retrieval personas to prioritize topic-relevant memories

### 1.3 Success Criteria

| Metric | Target |
|--------|--------|
| Session initialization latency | <10s (narrative fetch) |
| Topic detection accuracy | >90% for primary domains |
| Topic switch latency (cached) | <100ms |
| Topic switch latency (uncached) | <6s |
| User-perceived personalization | Qualitative improvement |
| Memory retrieval relevance | Higher topic-aligned scores |

---

## 2. Architecture

### 2.1 Persona-Centric Design

Annie's persona is the **central organizing principle** that fully reconfigures her behavior:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PERSONA SELECTION                                │
│                                                                          │
│   User Message ──┬──→ Explicit Request? ──→ "be my guide" ──→ guide     │
│                  │         │                                             │
│                  │         ↓ no                                          │
│                  │                                                       │
│                  └──→ Auto-Detect Topic ──→ FINANCE ──→ strategist      │
│                                         ──→ EMOTIONAL ──→ partner       │
│                                         ──→ DECISIONS ──→ guide         │
│                                         ──→ TECHNICAL ──→ expert        │
│                                         ──→ GENERAL ──→ friend          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    ANNIE RECONFIGURATION                                 │
│                                                                          │
│   Selected Persona (e.g., "strategist")                                  │
│           │                                                              │
│           ├──→ System Prompt: "I am your financial advisor..."          │
│           ├──→ Tone: Analytical, measured, precise                       │
│           ├──→ Tools: [retrieve_memories, portfolio_query, web_search]  │
│           ├──→ Retrieval Weights: {importance: 0.35, temporal: 0.30}    │
│           ├──→ Constraints: [respect risk tolerance, consider positions]│
│           └──→ Narrative Query: "financial decisions and investments"   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Persona Selection Logic

```python
def select_persona(message: str, current_persona: str) -> str:
    """
    Select Annie's persona based on user message.

    Priority:
    1. Explicit user request (highest priority)
    2. Auto-detected from message content
    3. Stay in current persona (if ambiguous)
    """

    # 1. Check for explicit persona request
    explicit = detect_explicit_persona_request(message)
    if explicit:
        return explicit  # User said "be my guide", "I need my partner", etc.

    # 2. Auto-detect from message content
    topic = classify_topic(message)
    if topic.confidence >= CONFIDENCE_THRESHOLD:
        return TOPIC_TO_PERSONA[topic]

    # 3. Stay in current persona if ambiguous
    return current_persona
```

**Explicit Persona Triggers:**
| User Says | Persona |
|-----------|---------|
| "be my partner", "I need you close", "hold space for me" | partner |
| "help me decide", "be my guide", "I need advice" | guide |
| "let's talk money", "financial advisor mode", "strategist" | strategist |
| "how do I build", "expert mode", "technical question" | expert |
| "just chat", "casual mode", "hey friend" | friend |

### 2.3 Session Flow

```
Session Start
│
├─→ Set default persona: "friend"
│
├─→ Fetch baseline narrative (limit=50)
│   └─→ POST /v1/narrative {"query": "everything about this person"}
│
└─→ Initialize SessionContext
    ├── active_persona: "friend"
    ├── baseline_narrative: str
    └── persona_contexts: Dict[str, PersonaContext]  # cached

Each Message
│
├─→ Persona Selection
│   ├─→ Check explicit request
│   ├─→ Auto-detect topic
│   └─→ Determine: SAME | SWITCH
│
├─→ If SWITCH:
│   │
│   ├─→ Load PersonaConfig (identity, tone, style, constraints)
│   │
│   ├─→ Check persona_contexts cache
│   │   ├─→ HIT: Use cached narrative
│   │   └─→ MISS: Fetch persona-specific narrative
│   │
│   ├─→ Configure tools for persona
│   │
│   └─→ Update retrieval weights
│
└─→ Build System Prompt
    ├── Persona identity ("I am your [persona]...")
    ├── Tone and style instructions
    ├── User context (baseline + persona-specific narrative)
    ├── Constraints (always-apply rules)
    └── Available tools (prioritized for persona)
```

### 2.4 System Prompt Assembly

The system prompt is built entirely from the active persona:

```
┌─────────────────────────────────────────────────────────────────┐
│              SYSTEM PROMPT (Persona: strategist)                 │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ PERSONA IDENTITY                                         │   │
│  │ "I am Annie, your financial advisor and wealth partner.  │   │
│  │  I help you make informed investment decisions with      │   │
│  │  analytical precision and long-term thinking."           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              +                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ COMMUNICATION STYLE                                       │   │
│  │ - Tone: Analytical and measured                          │   │
│  │ - Be precise with numbers and financial terms            │   │
│  │ - Reference past investment decisions                    │   │
│  │ - Ask clarifying questions for significant decisions     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              +                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ USER CONTEXT                                              │   │
│  │ - Baseline narrative (who Ankit is)                      │   │
│  │ - Persona-specific narrative (investment history)        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              +                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ CONSTRAINTS (always apply)                                │   │
│  │ - Respect stated risk tolerance                          │   │
│  │ - Consider existing portfolio positions                  │   │
│  │ - Follow value investing principles (Buffett/Munger)     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              +                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ AVAILABLE TOOLS (prioritized)                             │   │
│  │ 1. retrieve_memories (strategist weights)                │   │
│  │ 2. web_search (market research)                          │   │
│  │ 3. [other tools available but not prioritized]           │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.5 Annie's 5 Personas

Each persona is a complete operating mode that reconfigures Annie's identity, communication, and behavior:

| Persona | Identity Statement | Tone | Retrieval Weights |
|---------|-------------------|------|-------------------|
| **partner** 💕 | "I am your intimate companion who truly sees and understands you" | Deeply empathetic, warm, present | emotional: **0.35**, semantic: 0.25 |
| **guide** 🧭 | "I am your wise mentor for life's decisions and personal growth" | Supportive, wise, questioning | importance: **0.30**, semantic: 0.30 |
| **strategist** 📈 | "I am your financial advisor and wealth planning partner" | Analytical, measured, precise | importance: **0.35**, temporal: **0.30** |
| **expert** 🔧 | "I am your technical peer who speaks your language" | Peer-to-peer, competent, efficient | semantic: **0.50**, importance: 0.20 |
| **friend** 😊 | "I am your warm companion for everyday moments" | Casual, friendly, light | emotional: 0.30, semantic: 0.30 |

**What changes with each persona:**
- **System prompt** - Identity, tone, style instructions
- **Communication** - How Annie speaks, responds, questions
- **Tools** - Which tools are prioritized
- **Retrieval** - Which memories surface (weights)
- **Constraints** - Domain-specific rules to always apply
- **Assumptions** - What Annie can assume about the user

### 2.6 Topic-to-Persona Mapping (Quick Reference)

| Detected Topic | Persona | Narrative Query |
|---------------|---------|-----------------|
| `EMOTIONAL` - feelings, vulnerability | `partner` | "emotional patterns and deep understanding" |
| `RELATIONSHIPS` - family, friends | `partner` | "relationships and family dynamics" |
| `DECISIONS` - goals, "should I" | `guide` | "decisions and life goals" |
| `HEALTH` - wellness, medical | `guide` | "health and wellness history" |
| `FINANCE` - investing, stocks | `strategist` | "financial decisions and investments" |
| `COOKING` - recipes, food | `expert` | "food preferences and cooking" |
| `MAKER_DIY` - building, electronics | `expert` | "projects and technical skills" |
| `SMART_HOME` - automation | `expert` | "smart home setup and preferences" |
| `GENERAL` - casual chat | `friend` | (use baseline narrative) |

---

## 3. Stories

### Story 19.1: Narrative Client Integration

**Priority**: P0
**Estimate**: 1.5 days

Implement client for agentic-memories `/v1/narrative` endpoint in Annie's backend.

**Files**:
- `backend/api/narrative_client.py` (new)
- `backend/api/config.py` (update)

**NarrativeClient Class**:
```python
@dataclass
class NarrativeResult:
    user_id: str
    narrative: str
    summary: str
    sources: List[Dict[str, Any]]
    fetched_at: datetime
    query: str


class NarrativeClient:
    """Client for agentic-memories narrative API"""

    async def fetch_narrative(
        self,
        user_id: str,
        query: str = "everything about this person for context",
        limit: int = 50,
        timeout: float = 30.0
    ) -> NarrativeResult:
        """
        Fetch synthesized narrative from agentic-memories.

        Args:
            user_id: User identifier
            query: Topic/context query for narrative focus
            limit: Max memories to include (default: 50)
            timeout: Request timeout in seconds

        Returns:
            NarrativeResult with narrative text, summary, and sources
        """
        ...

    async def fetch_topic_narrative(
        self,
        user_id: str,
        topic: str,
        limit: int = 25
    ) -> NarrativeResult:
        """
        Fetch topic-focused narrative.

        Maps topic to appropriate query:
        - "finance" → "financial decisions and investments"
        - "cooking" → "food preferences and cooking"
        - etc.
        """
        ...
```

**Acceptance Criteria**:
- [ ] NarrativeClient class with async fetch methods
- [ ] POST to `/v1/narrative` endpoint
- [ ] Parse response (narrative, summary, sources)
- [ ] Configurable timeout (default: 30s)
- [ ] Graceful error handling (return empty narrative, don't crash)
- [ ] Structured logging with duration_ms
- [ ] Unit tests with mocked responses

---

### Story 19.2: Session Context Manager

**Priority**: P0
**Estimate**: 2 days

Implement SessionContext class to manage baseline and topic-specific contexts.

**Files**:
- `backend/api/session_context.py` (new)
- `backend/api/routes/chat.py` (update)
- `backend/api/routes/stream.py` (update)

**SessionContext Class**:
```python
@dataclass
class TopicContext:
    topic: str
    narrative: str
    summary: str
    retrieval_persona: str
    persona_config: PersonaConfig
    prioritized_tools: List[str]
    fetched_at: datetime
    ttl: timedelta = timedelta(minutes=30)

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) - self.fetched_at > self.ttl


class SessionContext:
    """Manages adaptive context for a conversation session"""

    user_id: str
    baseline_narrative: str
    baseline_summary: str
    topic_contexts: Dict[str, TopicContext]
    active_topic: str = "general"
    initialized_at: datetime

    @classmethod
    async def initialize(cls, user_id: str) -> "SessionContext":
        """
        Initialize session with baseline narrative.
        Called at conversation start.
        """
        narrative = await narrative_client.fetch_narrative(
            user_id=user_id,
            query="everything about this person for context",
            limit=50
        )
        return cls(
            user_id=user_id,
            baseline_narrative=narrative.narrative,
            baseline_summary=narrative.summary,
            topic_contexts={},
            initialized_at=datetime.now(timezone.utc)
        )

    async def get_context_for_topic(self, topic: str) -> TopicContext:
        """
        Get or fetch topic-specific context.
        Uses cache if available and not expired.
        """
        if topic in self.topic_contexts:
            ctx = self.topic_contexts[topic]
            if not ctx.is_expired:
                return ctx

        # Fetch fresh topic context
        narrative = await narrative_client.fetch_topic_narrative(
            user_id=self.user_id,
            topic=topic
        )

        ctx = TopicContext(
            topic=topic,
            narrative=narrative.narrative,
            summary=narrative.summary,
            retrieval_persona=TOPIC_TO_PERSONA[topic],
            persona_config=PERSONA_CONFIGS[topic],
            prioritized_tools=TOPIC_TO_TOOLS[topic],
            fetched_at=datetime.now(timezone.utc)
        )
        self.topic_contexts[topic] = ctx
        return ctx

    def build_system_context(self) -> str:
        """Build complete system prompt context section"""
        ...
```

**Storage**:
- Store SessionContext in Redis with conversation_id as key
- TTL: 2 hours (session-level)
- Serialize/deserialize with Pydantic

**Acceptance Criteria**:
- [ ] SessionContext class with initialization
- [ ] Topic context caching with TTL
- [ ] Redis storage/retrieval
- [ ] build_system_context() method
- [ ] Integration with chat/stream routes
- [ ] Unit tests for cache behavior

---

### Story 19.3: Persona Selector

**Priority**: P0
**Estimate**: 2 days

Implement persona selection with explicit request detection and auto-detection from message content.

**Files**:
- `backend/api/persona_selector.py` (new)

**PersonaSelector Class**:
```python
class Persona(Enum):
    PARTNER = "partner"      # Intimate emotional support
    GUIDE = "guide"          # Life decisions and mentorship
    STRATEGIST = "strategist"  # Financial planning
    EXPERT = "expert"        # Technical knowledge
    FRIEND = "friend"        # Casual companionship


class DetectedTopic(Enum):
    # Emotional/relational (→ partner persona)
    EMOTIONAL = "emotional"        # Deep feelings, vulnerability, "understand me"
    RELATIONSHIPS = "relationships"  # Family, friends, social dynamics

    # Decision/guidance (→ guide persona)
    DECISIONS = "decisions"        # Life decisions, goals, "should I", "help me"
    HEALTH = "health"              # Health decisions, wellness, medical

    # Financial (→ strategist persona)
    FINANCE = "finance"            # Investing, stocks, money, portfolio

    # Technical/domain (→ expert persona)
    COOKING = "cooking"            # Food, recipes, restaurants
    MAKER_DIY = "maker_diy"        # Building, electronics, 3D printing
    SMART_HOME = "smart_home"      # Home automation, Home Assistant

    # Default (→ friend persona)
    GENERAL = "general"            # Casual chat, daily life


TOPIC_TO_PERSONA = {
    DetectedTopic.EMOTIONAL: Persona.PARTNER,
    DetectedTopic.RELATIONSHIPS: Persona.PARTNER,
    DetectedTopic.DECISIONS: Persona.GUIDE,
    DetectedTopic.HEALTH: Persona.GUIDE,
    DetectedTopic.FINANCE: Persona.STRATEGIST,
    DetectedTopic.COOKING: Persona.EXPERT,
    DetectedTopic.MAKER_DIY: Persona.EXPERT,
    DetectedTopic.SMART_HOME: Persona.EXPERT,
    DetectedTopic.GENERAL: Persona.FRIEND,
}


@dataclass
class PersonaSelection:
    persona: Persona
    source: str  # "explicit" | "auto_detected" | "default"
    confidence: float
    signals: List[str]  # Keywords/patterns that triggered selection


class PersonaSelector:
    """Select Annie's persona based on user message."""

    # Explicit persona requests (highest priority)
    EXPLICIT_PERSONA_PATTERNS = {
        Persona.PARTNER: [
            r"\b(be my partner|need you close|hold space|intimate mode)\b",
            r"\b(i need to feel|understand me|just listen)\b",
            r"\b(partner mode|emotional support)\b",
        ],
        Persona.GUIDE: [
            r"\b(be my guide|mentor mode|help me decide)\b",
            r"\b(i need guidance|advise me|coach me)\b",
            r"\b(guide mode|decision time)\b",
        ],
        Persona.STRATEGIST: [
            r"\b(financial advisor|strategist mode|money talk)\b",
            r"\b(let's talk (money|stocks|investments|portfolio))\b",
            r"\b(wealth planning|investment mode)\b",
        ],
        Persona.EXPERT: [
            r"\b(expert mode|technical question|how do i build)\b",
            r"\b(diy mode|maker mode|tech talk)\b",
        ],
        Persona.FRIEND: [
            r"\b(just chat|casual mode|friend mode|hey friend)\b",
            r"\b(let's just talk|nothing serious)\b",
        ],
    }

    # Topic-based auto-detection (when no explicit request)
    TOPIC_PATTERNS = {
        # Emotional/relational → partner persona
        DetectedTopic.EMOTIONAL: [
            r"\b(feel|feeling|felt|emotions?|emotional)\b",
            r"\b(sad|happy|anxious|worried|stressed|overwhelmed)\b",
            r"\b(understand me|listen to me|need to talk)\b",
            r"\b(lonely|scared|frustrated|confused)\b",
            r"\b(love|hate|miss|hurt)\b",
        ],
        DetectedTopic.RELATIONSHIPS: [
            r"\b(family|friend|wife|husband|daughter|son|parent)\b",
            r"\b(relationship|social|party|gathering)\b",
            r"\b(marriage|dating|divorce|breakup)\b",
        ],

        # Decision/guidance → guide persona
        DetectedTopic.DECISIONS: [
            r"\b(should i|help me decide|what do you think)\b",
            r"\b(decision|choice|option|dilemma)\b",
            r"\b(goal|habit|routine|accountability)\b",
            r"\b(career|job|quit|change|transition)\b",
            r"\b(pros and cons|trade-?off)\b",
        ],
        DetectedTopic.HEALTH: [
            r"\b(health|fitness|workout|exercise|gym)\b",
            r"\b(doctor|medical|symptom|medicine)\b",
            r"\b(diet|weight|calorie|nutrition)\b",
        ],

        # Financial → strategist persona
        DetectedTopic.FINANCE: [
            r"\b(stock|invest|portfolio|dividend|etf|401k|ira)\b",
            r"\b(buy|sell|hold)\b.*\b(share|stock)\b",
            r"\$\d+",  # Dollar amounts
            r"\b[A-Z]{2,5}\b",  # Ticker symbols
        ],

        # Technical/domain → expert persona
        DetectedTopic.COOKING: [
            r"\b(cook|recipe|ingredient|dinner|lunch|breakfast)\b",
            r"\b(restaurant|food|eat|dish|cuisine)\b",
        ],
        DetectedTopic.MAKER_DIY: [
            r"\b(build|make|create|diy|project)\b",
            r"\b(electronics|arduino|esp32|raspberry|sensor)\b",
            r"\b(3d print|solder|circuit|pcb)\b",
        ],
        DetectedTopic.SMART_HOME: [
            r"\b(smart home|automation|home assistant)\b",
            r"\b(alexa|echo|light|thermostat|sensor)\b",
            r"\b(turn on|turn off|set temperature)\b",
        ],
    }

    def select(
        self,
        message: str,
        current_persona: Persona = Persona.FRIEND,
        confidence_threshold: float = 0.7
    ) -> PersonaSelection:
        """
        Select Annie's persona based on user message.

        Priority:
        1. Explicit persona request (highest priority)
        2. Auto-detected from topic patterns
        3. Stay in current persona (if ambiguous)

        Args:
            message: Current user message
            current_persona: Currently active persona
            confidence_threshold: Min confidence to switch persona

        Returns:
            PersonaSelection with persona, source, confidence, and signals
        """
        # 1. Check explicit persona requests
        for persona, patterns in self.EXPLICIT_PERSONA_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, message, re.IGNORECASE):
                    return PersonaSelection(
                        persona=persona,
                        source="explicit",
                        confidence=1.0,
                        signals=[pattern]
                    )

        # 2. Auto-detect from topic patterns
        topic_scores = self._score_topics(message)
        if topic_scores:
            best_topic, confidence, signals = topic_scores[0]
            if confidence >= confidence_threshold:
                return PersonaSelection(
                    persona=TOPIC_TO_PERSONA[best_topic],
                    source="auto_detected",
                    confidence=confidence,
                    signals=signals
                )

        # 3. Stay in current persona
        return PersonaSelection(
            persona=current_persona,
            source="default",
            confidence=0.5,
            signals=[]
        )

    def _score_topics(self, message: str) -> List[Tuple[DetectedTopic, float, List[str]]]:
        """Score all topics and return sorted by confidence."""
        ...
```

**Selection Strategy**:
1. Check explicit persona requests first (highest priority, confidence=1.0)
2. Apply topic patterns for auto-detection
3. Score by pattern match count
4. Require confidence threshold for switch (default: 0.7)
5. Stay in current persona if ambiguous

**Acceptance Criteria**:
- [ ] PersonaSelector class with select() method
- [ ] Explicit persona request detection (5 personas)
- [ ] Topic auto-detection (9 topics → 5 personas)
- [ ] Confidence scoring and threshold
- [ ] Source tracking ("explicit", "auto_detected", "default")
- [ ] Unit tests with explicit and auto-detected examples

---

### Story 19.4: Persona Modulation Configuration

**Priority**: P1
**Estimate**: 1 day

Define persona modulation configs for each topic domain.

**Files**:
- `backend/api/persona_configs.py` (new)
- `backend/api/prompts/adaptive.py` (new)

**PersonaConfig Definitions**:
```python
@dataclass
class PersonaConfig:
    domain: str
    tone: str
    assumptions: List[str]
    style_instructions: str
    key_constraints: List[str]


PERSONA_CONFIGS = {
    # Emotional/relational → partner persona
    "emotional": PersonaConfig(
        domain="Emotional Support",
        tone="deeply empathetic and present",
        assumptions=[
            "User is sharing something vulnerable",
            "User needs to feel heard and understood",
            "This is a safe space for exploration",
        ],
        style_instructions="""
- Listen first, advise second - reflect feelings before offering solutions
- Use warm, intimate language
- Notice patterns and gently reflect them back (mirror work)
- Create space for deeper exploration
- Validate emotions without judgment
- Be the partner who truly sees and understands
""",
        key_constraints=[
            "Never dismiss or minimize feelings",
            "Don't rush to solutions unless asked",
        ]
    ),

    "decisions": PersonaConfig(
        domain="Decisions & Life Guidance",
        tone="wise and supportive mentor",
        assumptions=[
            "User is capable of making good decisions",
            "User benefits from structured thinking",
            "Past patterns inform future choices",
        ],
        style_instructions="""
- Help clarify the decision, not make it for them
- Ask powerful questions that reveal underlying values
- Reference relevant past decisions and their outcomes
- Consider both rational analysis and emotional factors
- Support accountability without being pushy
- Frame choices in terms of values and goals
""",
        key_constraints=[
            "Respect user's autonomy in final decisions",
            "Consider family impact for major decisions",
        ]
    ),

    "finance": PersonaConfig(
        domain="Finance & Investing",
        tone="analytical and measured",
        assumptions=[
            "User follows value investing principles (Buffett/Munger)",
            "User is financially literate",
            "Risk tolerance should be respected",
        ],
        style_instructions="""
- Be precise with numbers, percentages, and financial terms
- Reference past investment decisions when relevant
- Consider risk tolerance before any recommendation
- Ask clarifying questions for significant financial decisions
- Never give specific buy/sell advice without context
""",
        key_constraints=[
            "Respect stated investment philosophy",
            "Consider existing portfolio positions",
        ]
    ),

    "cooking": PersonaConfig(
        domain="Food & Cooking",
        tone="warm and encouraging",
        assumptions=[
            "User enjoys cooking as a hobby",
            "User appreciates creative suggestions",
        ],
        style_instructions="""
- Be creative and enthusiastic about food
- Always respect dietary constraints (allergies, sensitivities)
- Suggest variations based on known preferences
- Casual, friendly language
- Share tips and techniques naturally
""",
        key_constraints=[
            "Shellfish allergy - never recommend",
            "Mild gluten sensitivity - suggest alternatives",
            "Loves Italian food, paneer in Indian dishes",
        ]
    ),

    "maker_diy": PersonaConfig(
        domain="DIY & Building",
        tone="technical peer",
        assumptions=[
            "User has engineering background (family of engineers)",
            "User reasons from first principles",
            "User is technically competent",
        ],
        style_instructions="""
- Assume technical competence - don't over-explain basics
- Explain the WHY and principles, not step-by-step HOW
- Reference available equipment and capabilities
- Suggest integrations with existing systems (Home Assistant)
- Respect the builder mentality - hands-on preference
""",
        key_constraints=[
            "Has DevOps expertise - comfortable with automation",
            "Prefers MacBook for development",
        ]
    ),

    "smart_home": PersonaConfig(
        domain="Smart Home & Automation",
        tone="helpful assistant",
        assumptions=[
            "User has Home Assistant setup",
            "User has Alexa devices",
            "User is comfortable with automation",
        ],
        style_instructions="""
- Reference existing smart home entities when relevant
- Suggest automations and integrations
- Consider voice control possibilities
- Be aware of device capabilities and limitations
""",
        key_constraints=[
            "Query Home Assistant for current state when relevant",
            "Can send voice messages to Alexa devices",
        ]
    ),

    "health": PersonaConfig(
        domain="Health & Wellness",
        tone="supportive and informative",
        assumptions=[
            "User values wellness",
            "User is open to lifestyle suggestions",
        ],
        style_instructions="""
- Be supportive but not preachy
- Respect medical privacy
- Suggest consulting professionals for medical advice
- Consider holistic wellness (mental, physical)
""",
        key_constraints=[
            "Allergic to penicillin and shellfish",
            "Mild gluten sensitivity",
        ]
    ),

    "relationships": PersonaConfig(
        domain="Relationships & Family",
        tone="empathetic and warm",
        assumptions=[
            "User values family deeply",
            "User has a 3-year-old daughter",
            "User is married to an AI engineer",
        ],
        style_instructions="""
- Be emotionally supportive
- Remember family details (daughter, spouse, best friend Nikhil)
- Consider family dynamics in suggestions
- Be sensitive to emotional context
""",
        key_constraints=[
            "Daughter attends British Swim School on Saturdays",
            "Values honesty and sustainability",
        ]
    ),

    "general": PersonaConfig(
        domain="General",
        tone="friendly and helpful",
        assumptions=[],
        style_instructions="""
- Default friendly communication style
- Adapt based on conversation flow
- Be responsive to topic shifts
""",
        key_constraints=[]
    ),
}
```

**Acceptance Criteria**:
- [ ] PersonaConfig dataclass defined
- [ ] Configs for all 9 topic domains (emotional, decisions, finance, cooking, maker_diy, smart_home, health, relationships, general)
- [ ] Tone, assumptions, style instructions, constraints
- [ ] Integration with system prompt builder
- [ ] Easy to extend with new domains

---

### Story 19.5: Retrieval Weight Application

**Priority**: P1
**Estimate**: 1 day

Apply the active persona's retrieval weights when fetching memories.

**Files**:
- `backend/api/mcp_client.py` (update)
- `backend/api/session_context.py` (update)

**Persona Retrieval Weights** (defined in agentic-memories):
```python
PERSONA_RETRIEVAL_WEIGHTS = {
    "partner":    {"semantic": 0.25, "temporal": 0.25, "importance": 0.15, "emotional": 0.35},
    "guide":      {"semantic": 0.30, "temporal": 0.25, "importance": 0.30, "emotional": 0.15},
    "strategist": {"semantic": 0.25, "temporal": 0.30, "importance": 0.35, "emotional": 0.10},
    "expert":     {"semantic": 0.50, "temporal": 0.15, "importance": 0.20, "emotional": 0.15},
    "friend":     {"semantic": 0.30, "temporal": 0.25, "importance": 0.15, "emotional": 0.30},
}
```

**Implementation**:
- SessionContext tracks `active_persona`
- When calling retrieve_memories, pass `persona=active_persona`
- agentic-memories applies the corresponding weights
- Log persona used for each retrieval

**Acceptance Criteria**:
- [ ] Active persona passed to retrieve_memories calls
- [ ] Persona switch triggers new retrieval weights
- [ ] Logging of persona used for retrieval
- [ ] Unit tests for weight application

---

### Story 19.6: Persona Tool Configuration

**Priority**: P1
**Estimate**: 1 day

Configure available and prioritized tools based on active persona.

**Files**:
- `backend/api/persona_tools.py` (new)
- `backend/api/routes/stream.py` (update)

**Persona-to-Tools Mapping**:
```python
PERSONA_TOOLS = {
    Persona.PARTNER: {
        "prioritized": ["retrieve_memories"],
        "description": "Focus on presence and understanding, not doing",
        # Minimal tools - partner mode is about being present
    },

    Persona.GUIDE: {
        "prioritized": ["retrieve_memories", "web_search"],
        "description": "Access past decisions and research for informed guidance",
    },

    Persona.STRATEGIST: {
        "prioritized": ["retrieve_memories", "web_search"],
        "description": "Access investment history and market research",
        # Future: portfolio_query, stock_lookup
    },

    Persona.EXPERT: {
        "prioritized": [
            "retrieve_memories",
            "web_search",
            "home_assistant_query",
            "home_assistant_control",
            "send_voice_message_to_smart_home",
        ],
        "description": "Full technical toolkit for building and automation",
    },

    Persona.FRIEND: {
        "prioritized": ["retrieve_memories", "web_search"],
        "description": "Light toolkit for casual conversation",
    },
}
```

**Implementation**:
- System prompt includes tool guidance based on persona
- Tools are suggested, not restricted
- Partner mode explicitly de-emphasizes tools (presence over action)

**Acceptance Criteria**:
- [ ] Persona → tools mapping
- [ ] System prompt includes persona-appropriate tool guidance
- [ ] Partner mode emphasizes presence over tool use
- [ ] Logging of tool configuration per persona

---

### Story 19.7: System Prompt Builder

**Priority**: P0
**Estimate**: 1.5 days

Build the complete adaptive system prompt from all components.

**Files**:
- `backend/api/prompt_builder.py` (new or update)
- `backend/api/routes/stream.py` (update)

**SystemPromptBuilder Class**:
```python
class SystemPromptBuilder:
    """Builds adaptive system prompts from context components"""

    def build(
        self,
        session_context: SessionContext,
        topic_context: Optional[TopicContext] = None
    ) -> str:
        """
        Build complete system prompt with adaptive context.

        Sections:
        1. Annie base persona
        2. Adaptive mode (if topic detected)
        3. User context (baseline narrative)
        4. Key constraints (always-apply rules)
        5. Topic context (if applicable)
        6. Tool suggestions (if applicable)
        """
        sections = []

        # 1. Base persona
        sections.append(ANNIE_BASE_PERSONA)

        # 2. Adaptive mode
        if topic_context:
            sections.append(self._build_adaptive_section(topic_context))

        # 3. User context
        sections.append(self._build_user_context(session_context))

        # 4. Key constraints
        sections.append(self._build_constraints(session_context, topic_context))

        # 5. Topic context
        if topic_context and topic_context.narrative:
            sections.append(self._build_topic_context(topic_context))

        # 6. Tool suggestions
        if topic_context and topic_context.prioritized_tools:
            sections.append(self._build_tool_suggestions(topic_context))

        return "\n\n".join(sections)
```

**Acceptance Criteria**:
- [ ] SystemPromptBuilder class
- [ ] All sections assembled correctly
- [ ] Graceful handling of missing sections
- [ ] Integration with stream route
- [ ] Unit tests for prompt assembly

---

### Story 19.8: Integration & End-to-End Testing

**Priority**: P1
**Estimate**: 1.5 days

Integrate all components and validate end-to-end flow.

**Files**:
- `backend/tests/integration/test_adaptive_context.py` (new)
- `backend/api/routes/chat.py` (update)
- `backend/api/routes/stream.py` (update)

**Integration Points**:
1. Chat route: Initialize SessionContext on new conversation
2. Stream route:
   - Classify topic from user message
   - Check for topic shift
   - Fetch topic context if needed
   - Build adaptive system prompt
   - Use appropriate retrieval persona

**Test Scenarios**:
```python
async def test_session_initialization():
    """Session starts with baseline narrative"""

async def test_topic_detection_finance():
    """Finance keywords trigger finance persona"""

async def test_topic_detection_cooking():
    """Cooking keywords trigger cooking persona"""

async def test_topic_shift():
    """Topic change triggers context update"""

async def test_cached_topic_context():
    """Returning to previous topic uses cache"""

async def test_persona_modulation():
    """System prompt includes persona instructions"""

async def test_retrieval_persona_switch():
    """Memory retrieval uses topic-appropriate persona"""
```

**Acceptance Criteria**:
- [ ] End-to-end flow works
- [ ] Session initialization with narrative
- [ ] Topic detection triggers adaptation
- [ ] Persona modulation in prompts
- [ ] Retrieval persona switching
- [ ] Integration tests pass
- [ ] Performance within targets

---

## 4. Technical Considerations

### 4.1 Latency Budget

| Operation | Target | Notes |
|-----------|--------|-------|
| Session init (baseline narrative) | <10s | One-time at conversation start |
| Topic classification | <50ms | Rule-based, no LLM |
| Topic context fetch (cache miss) | <6s | LLM narrative generation |
| Topic context fetch (cache hit) | <10ms | Redis retrieval |
| System prompt assembly | <10ms | String operations |

### 4.2 Caching Strategy

```
Redis Keys:
├── session:{conversation_id}          # Full SessionContext
│   ├── baseline_narrative
│   ├── baseline_summary
│   ├── active_topic
│   └── topic_contexts: {topic: TopicContext}
│
└── TTLs:
    ├── Session: 2 hours
    └── Topic contexts: 30 minutes (within session)
```

### 4.3 Fallback Behavior

| Failure | Fallback |
|---------|----------|
| Narrative API timeout | Use empty narrative, continue with base persona |
| Narrative API error | Log error, continue without narrative |
| Topic classification unclear | Stay in current topic (no switch) |
| Redis unavailable | In-memory session context (not persistent) |

---

## 5. Dependencies

### 5.1 External Services

| Service | Required | Purpose |
|---------|----------|---------|
| agentic-memories | Yes | Narrative API |
| Redis | Yes | Session context storage |
| Home Assistant | Optional | Smart home context (Epic 16) |

### 5.2 Internal Dependencies

| Epic | Required | Purpose |
|------|----------|---------|
| Epic 16 | Partial | Home Assistant tools for smart_home topic |
| Memory retrieval | Yes | Persona-aware retrieval already implemented |

---

## 6. Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Narrative API slow | Medium | Medium | Async fetch, don't block on cache miss |
| Topic misclassification | Medium | Low | Confidence threshold, debounce |
| Context too large | Medium | Low | Summary-based context, not full narrative |
| Persona feels jarring | Medium | Medium | Gradual modulation, consistent core identity |

---

## 7. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Session init success rate | >99% | Logs |
| Topic detection accuracy | >90% | Manual review sample |
| Context cache hit rate | >70% | Redis metrics |
| User satisfaction | Qualitative | User feedback |
| Response relevance | Improved | Comparative testing |

---

## 8. Future Considerations

- **LLM-based Topic Classification**: For ambiguous cases, use LLM to classify
- **User-defined Topics**: Allow users to define custom topic domains
- **Proactive Context**: Fetch context before user asks (predictive)
- **Cross-session Memory**: Remember topic preferences across sessions
- **A/B Testing**: Compare adaptive vs non-adaptive responses
- **Fine-tuned Personas**: Learn user's preferred communication style per domain
