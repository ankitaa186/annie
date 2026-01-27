import { render, screen } from '@testing-library/react';
import { LLMIndicator, getLLMDisplayName, LLM_DISPLAY_NAMES } from '../LLMIndicator';

// Mock Radix UI Tooltip
jest.mock('@radix-ui/react-tooltip', () => ({
  Provider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Root: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Trigger: ({ children, asChild }: { children: React.ReactNode; asChild?: boolean }) =>
    asChild ? children : <button>{children}</button>,
  Content: ({ children }: { children: React.ReactNode }) => (
    <div role="tooltip">{children}</div>
  ),
  Portal: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

describe('LLMIndicator', () => {
  describe('display name mapping', () => {
    it('maps gemini-3-pro-preview to Gemini 3 Pro', () => {
      expect(getLLMDisplayName('gemini-3-pro-preview')).toBe('Gemini 3 Pro');
    });

    it('maps grok-4 to Grok-4', () => {
      expect(getLLMDisplayName('grok-4')).toBe('Grok-4');
    });

    it('maps chatgpt-5 to ChatGPT-5', () => {
      expect(getLLMDisplayName('chatgpt-5')).toBe('ChatGPT-5');
    });

    it('returns original ID for unknown providers', () => {
      expect(getLLMDisplayName('custom-model-v1')).toBe('custom-model-v1');
    });

    it('returns Unknown LLM for null/undefined', () => {
      expect(getLLMDisplayName(null)).toBe('Unknown LLM');
      expect(getLLMDisplayName(undefined)).toBe('Unknown LLM');
    });
  });

  describe('rendering', () => {
    it('displays friendly name for known provider', () => {
      render(<LLMIndicator activeLLM="gemini-3-pro-preview" llmStatus="ok" />);

      expect(screen.getByText('Gemini 3 Pro')).toBeInTheDocument();
    });

    it('displays original ID for unknown provider', () => {
      render(<LLMIndicator activeLLM="custom-model" llmStatus="ok" />);

      expect(screen.getByText('custom-model')).toBeInTheDocument();
    });

    it('shows green dot for ok status', () => {
      render(<LLMIndicator activeLLM="grok-4" llmStatus="ok" />);

      const indicator = screen.getByRole('status');
      const dot = indicator.querySelector('.rounded-full');
      expect(dot).toHaveClass('bg-green-500');
    });

    it('shows yellow dot for degraded status', () => {
      render(<LLMIndicator activeLLM="grok-4" llmStatus="degraded" />);

      const indicator = screen.getByRole('status');
      const dot = indicator.querySelector('.rounded-full');
      expect(dot).toHaveClass('bg-yellow-500');
    });

    it('shows red dot for unavailable status', () => {
      render(<LLMIndicator activeLLM="grok-4" llmStatus="unavailable" />);

      const indicator = screen.getByRole('status');
      const dot = indicator.querySelector('.rounded-full');
      expect(dot).toHaveClass('bg-red-500');
    });
  });

  describe('loading state', () => {
    it('shows skeleton when loading', () => {
      render(<LLMIndicator activeLLM={null} llmStatus="unavailable" loading={true} />);

      expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'Loading LLM indicator');
    });

    it('shows animated pulse effect during loading', () => {
      render(<LLMIndicator activeLLM={null} llmStatus="unavailable" loading={true} />);

      const pulseElements = screen.getByRole('status').querySelectorAll('.animate-pulse');
      expect(pulseElements.length).toBeGreaterThan(0);
    });
  });

  describe('tooltip content', () => {
    it('shows Active AI Provider title', () => {
      render(<LLMIndicator activeLLM="gemini-3-pro-preview" llmStatus="ok" />);

      expect(screen.getByText('Active AI Provider')).toBeInTheDocument();
    });

    it('shows model name in tooltip', () => {
      render(<LLMIndicator activeLLM="gemini-3-pro-preview" llmStatus="ok" />);

      // The display name appears in both the main indicator and tooltip
      const modelTexts = screen.getAllByText('Gemini 3 Pro');
      expect(modelTexts.length).toBeGreaterThan(0);
    });

    it('shows model ID when different from display name', () => {
      render(<LLMIndicator activeLLM="gemini-3-pro-preview" llmStatus="ok" />);

      // Should show the raw ID in tooltip
      expect(screen.getByText('gemini-3-pro-preview')).toBeInTheDocument();
    });

    it('shows status text in tooltip', () => {
      render(<LLMIndicator activeLLM="grok-4" llmStatus="ok" />);

      expect(screen.getByText('Connected')).toBeInTheDocument();
    });

    it('shows Degraded status text when degraded', () => {
      render(<LLMIndicator activeLLM="grok-4" llmStatus="degraded" />);

      expect(screen.getByText('Degraded')).toBeInTheDocument();
    });

    it('shows Unavailable status text when unavailable', () => {
      render(<LLMIndicator activeLLM="grok-4" llmStatus="unavailable" />);

      expect(screen.getByText('Unavailable')).toBeInTheDocument();
    });
  });

  describe('accessibility', () => {
    it('has accessible status role', () => {
      render(<LLMIndicator activeLLM="grok-4" llmStatus="ok" />);

      const status = screen.getByRole('status');
      expect(status).toHaveAttribute('aria-label', 'Active LLM: Grok-4, Status: Connected');
    });

    it('updates aria-label based on status', () => {
      render(<LLMIndicator activeLLM="chatgpt-5" llmStatus="degraded" />);

      const status = screen.getByRole('status');
      expect(status).toHaveAttribute('aria-label', 'Active LLM: ChatGPT-5, Status: Degraded');
    });

    it('handles unknown LLM in aria-label', () => {
      render(<LLMIndicator activeLLM={null} llmStatus="unavailable" />);

      const status = screen.getByRole('status');
      expect(status).toHaveAttribute('aria-label', 'Active LLM: Unknown LLM, Status: Unavailable');
    });
  });

  describe('transitions', () => {
    it('applies transition classes for smooth color changes', () => {
      render(<LLMIndicator activeLLM="grok-4" llmStatus="ok" />);

      const indicator = screen.getByRole('status');
      expect(indicator).toHaveClass('transition-colors', 'duration-300');
    });
  });

  describe('LLM_DISPLAY_NAMES constant', () => {
    it('includes all expected Gemini variants', () => {
      expect(LLM_DISPLAY_NAMES['gemini-3-pro-preview']).toBe('Gemini 3 Pro');
      expect(LLM_DISPLAY_NAMES['gemini-2.0-flash-exp']).toBe('Gemini 2.0');
      expect(LLM_DISPLAY_NAMES['gemini-1.5-pro']).toBe('Gemini 1.5');
      expect(LLM_DISPLAY_NAMES['gemini-1.5-flash']).toBe('Gemini 1.5 Flash');
    });

    it('includes all expected Grok variants', () => {
      expect(LLM_DISPLAY_NAMES['grok-4']).toBe('Grok-4');
      expect(LLM_DISPLAY_NAMES['grok-3']).toBe('Grok-3');
      expect(LLM_DISPLAY_NAMES['grok-beta']).toBe('Grok Beta');
    });

    it('includes all expected ChatGPT variants', () => {
      expect(LLM_DISPLAY_NAMES['chatgpt-5']).toBe('ChatGPT-5');
      expect(LLM_DISPLAY_NAMES['gpt-4o']).toBe('GPT-4o');
      expect(LLM_DISPLAY_NAMES['gpt-4-turbo']).toBe('GPT-4 Turbo');
      expect(LLM_DISPLAY_NAMES['gpt-4']).toBe('GPT-4');
    });

    it('includes unknown fallback', () => {
      expect(LLM_DISPLAY_NAMES['unknown']).toBe('Unknown LLM');
    });
  });
});
