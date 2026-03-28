"""
Central LLM provider and model constants.
Change a model or provider here — it propagates everywhere.
"""

# ---- API Providers (who you're calling) ----
PROVIDER_XAI = "xai"
PROVIDER_OPENAI = "openai"
PROVIDER_GOOGLE = "google"

# ---- Model identifiers (what gets sent to the API / what users set in LLM_MODEL) ----
MODEL_GROK_4 = "grok-4-fast"
MODEL_GPT_5 = "gpt-5.4"
MODEL_GEMINI_PRO = "gemini-3.1-pro-preview"
MODEL_GEMINI_FLASH = "gemini-3-flash-preview"
MODEL_GEMINI_LEGACY = "gemini-2.5-pro"

# ---- Model → API provider mapping ----
MODEL_TO_PROVIDER = {
    MODEL_GROK_4: PROVIDER_XAI,
    MODEL_GPT_5: PROVIDER_OPENAI,
    MODEL_GEMINI_PRO: PROVIDER_GOOGLE,
    MODEL_GEMINI_FLASH: PROVIDER_GOOGLE,
    MODEL_GEMINI_LEGACY: PROVIDER_GOOGLE,
}

# ---- Valid models users can select via LLM_MODEL env var ----
PRIMARY_MODELS = [MODEL_GROK_4, MODEL_GPT_5, MODEL_GEMINI_PRO]

# All known models (including fallback-only)
ALL_MODELS = [MODEL_GROK_4, MODEL_GPT_5, MODEL_GEMINI_PRO, MODEL_GEMINI_FLASH, MODEL_GEMINI_LEGACY]

# Default when LLM_MODEL env var is not set
DEFAULT_MODEL = MODEL_GEMINI_PRO

# ---- Model → API key env var mapping ----
MODEL_API_KEY_MAP = {
    MODEL_GROK_4: "XAI_API_KEY",
    MODEL_GPT_5: "OPENAI_API_KEY",
    MODEL_GEMINI_PRO: "GOOGLE_API_KEY",
    MODEL_GEMINI_FLASH: "GOOGLE_API_KEY",
    MODEL_GEMINI_LEGACY: "GOOGLE_API_KEY",
}

# ---- Fallback chain (data-driven) ----
FALLBACK_CHAIN = {
    MODEL_GROK_4: [MODEL_GPT_5],
    MODEL_GPT_5: [MODEL_GROK_4],
    MODEL_GEMINI_PRO: [MODEL_GPT_5, MODEL_GEMINI_FLASH, MODEL_GROK_4],
    MODEL_GEMINI_FLASH: [MODEL_GROK_4],
    MODEL_GEMINI_LEGACY: [MODEL_GROK_4],
}

# ---- Models with internal tool handling (provider manages its own tool loop) ----
MODELS_WITH_INTERNAL_TOOL_HANDLING = {MODEL_GPT_5, MODEL_GEMINI_PRO, MODEL_GEMINI_FLASH, MODEL_GEMINI_LEGACY}

# ---- Backward compat: old LLM_PROVIDER values → new model names ----
LEGACY_PROVIDER_TO_MODEL = {
    "grok-4": MODEL_GROK_4,
    "chatgpt-5": MODEL_GPT_5,
    "gpt-5.2": MODEL_GPT_5,
    "gemini-3.1-pro-preview": MODEL_GEMINI_PRO,
}

# ---- Display names for UI ----
MODEL_DISPLAY_NAMES = {
    MODEL_GROK_4: "Grok-4",
    MODEL_GPT_5: "ChatGPT-5",
    MODEL_GEMINI_PRO: "Gemini 3.1 Pro",
    MODEL_GEMINI_FLASH: "Gemini 3 Flash",
    MODEL_GEMINI_LEGACY: "Gemini 2.5 Pro",
}
