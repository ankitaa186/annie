/**
 * Central LLM model constants for the frontend.
 * Mirrors backend/api/constants.py — change a model here, it propagates everywhere.
 */

// ---- Model identifiers ----
export const MODEL_GROK_4 = 'grok-4-fast';
export const MODEL_GPT_5 = 'gpt-5.4';
export const MODEL_GEMINI_PRO = 'gemini-3.1-pro-preview';
export const MODEL_GEMINI_FLASH = 'gemini-3-flash-preview';
export const MODEL_GEMINI_LEGACY = 'gemini-2.5-pro';

export const DEFAULT_MODEL = MODEL_GROK_4;

// ---- Display names ----
export const MODEL_DISPLAY_NAMES: Record<string, string> = {
  [MODEL_GROK_4]: 'Grok-4',
  [MODEL_GPT_5]: 'ChatGPT-5',
  [MODEL_GEMINI_PRO]: 'Gemini 3 Pro',
  [MODEL_GEMINI_FLASH]: 'Gemini 3 Flash',
  [MODEL_GEMINI_LEGACY]: 'Gemini 2.5 Pro',
  // Legacy / additional variants kept for UI compat
  'gemini-2.0-flash-exp': 'Gemini 2.0',
  'gemini-1.5-pro': 'Gemini 1.5',
  'gemini-1.5-flash': 'Gemini 1.5 Flash',
  'grok-4': 'Grok-4',
  'grok-3': 'Grok-3',
  'grok-beta': 'Grok Beta',
  'chatgpt-5': 'ChatGPT-5',
  'gpt-4o': 'GPT-4o',
  'gpt-4-turbo': 'GPT-4 Turbo',
  'gpt-4': 'GPT-4',
  unknown: 'Unknown LLM',
};

export function getLLMDisplayName(
  modelId: string | undefined | null,
): string {
  if (!modelId) return MODEL_DISPLAY_NAMES.unknown ?? 'Unknown LLM';
  return MODEL_DISPLAY_NAMES[modelId] ?? modelId;
}
