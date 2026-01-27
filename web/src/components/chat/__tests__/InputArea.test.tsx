/**
 * Tests for InputArea component
 *
 * Tests cover:
 * - AC1: Auto-expanding textarea
 * - AC2: Send button enabled/disabled state
 * - AC3: Enter to send, Shift+Enter for newline
 * - AC9: Loading state during send
 * - AC10: Input disabled while Annie responds
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { InputArea } from '../InputArea';

// Mock the useToast hook
vi.mock('@/lib/hooks/useToast', () => ({
  useToast: () => ({
    toast: vi.fn(),
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
    dismiss: vi.fn(),
  }),
}));

describe('InputArea', () => {
  const mockOnSend = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockOnSend.mockResolvedValue(undefined);
  });

  describe('AC1: Auto-expanding textarea', () => {
    it('should render textarea', () => {
      render(<InputArea onSend={mockOnSend} />);
      expect(screen.getByRole('textbox', { name: /message input/i })).toBeInTheDocument();
    });

    it('should have placeholder text', () => {
      render(<InputArea onSend={mockOnSend} placeholder="Custom placeholder" />);
      expect(screen.getByPlaceholderText('Custom placeholder')).toBeInTheDocument();
    });

    it('should use default placeholder', () => {
      render(<InputArea onSend={mockOnSend} />);
      expect(screen.getByPlaceholderText('Type a message...')).toBeInTheDocument();
    });
  });

  describe('AC2: Send button enabled/disabled state', () => {
    it('should disable send button when input is empty', () => {
      render(<InputArea onSend={mockOnSend} />);
      const sendButton = screen.getByRole('button', { name: /send/i });
      expect(sendButton).toBeDisabled();
    });

    it('should enable send button when input has text', async () => {
      const user = userEvent.setup();
      render(<InputArea onSend={mockOnSend} />);

      const textarea = screen.getByRole('textbox');
      await user.type(textarea, 'Hello');

      const sendButton = screen.getByRole('button', { name: /send/i });
      expect(sendButton).not.toBeDisabled();
    });

    it('should disable send button when only whitespace', async () => {
      const user = userEvent.setup();
      render(<InputArea onSend={mockOnSend} />);

      const textarea = screen.getByRole('textbox');
      await user.type(textarea, '   ');

      const sendButton = screen.getByRole('button', { name: /send/i });
      expect(sendButton).toBeDisabled();
    });
  });

  describe('AC3: Enter to send, Shift+Enter for newline', () => {
    it('should send message on Enter key', async () => {
      const user = userEvent.setup();
      render(<InputArea onSend={mockOnSend} />);

      const textarea = screen.getByRole('textbox');
      await user.type(textarea, 'Hello');
      await user.keyboard('{Enter}');

      await waitFor(() => {
        expect(mockOnSend).toHaveBeenCalledWith('Hello', []);
      });
    });

    it('should insert newline on Shift+Enter', async () => {
      const user = userEvent.setup();
      render(<InputArea onSend={mockOnSend} />);

      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
      await user.type(textarea, 'Line 1{Shift>}{Enter}{/Shift}Line 2');

      expect(textarea.value).toContain('Line 1');
      expect(textarea.value).toContain('Line 2');
      expect(mockOnSend).not.toHaveBeenCalled();
    });

    it('should not send on Enter when input is empty', async () => {
      const user = userEvent.setup();
      render(<InputArea onSend={mockOnSend} />);

      const textarea = screen.getByRole('textbox');
      await user.keyboard('{Enter}');

      expect(mockOnSend).not.toHaveBeenCalled();
    });
  });

  describe('AC9: Loading state during send', () => {
    it('should show loading state while sending', async () => {
      const user = userEvent.setup();
      // Create a promise that doesn't resolve immediately
      let resolvePromise: () => void;
      const sendPromise = new Promise<void>((resolve) => {
        resolvePromise = resolve;
      });
      mockOnSend.mockReturnValue(sendPromise);

      render(<InputArea onSend={mockOnSend} />);

      const textarea = screen.getByRole('textbox');
      await user.type(textarea, 'Hello');

      const sendButton = screen.getByRole('button', { name: /send/i });
      await user.click(sendButton);

      // Button should show loading state
      expect(screen.getByRole('button', { name: /sending/i })).toBeInTheDocument();

      // Resolve the promise
      resolvePromise!();
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /send/i })).toBeInTheDocument();
      });
    });

    it('should disable textarea while sending', async () => {
      const user = userEvent.setup();
      let resolvePromise: () => void;
      const sendPromise = new Promise<void>((resolve) => {
        resolvePromise = resolve;
      });
      mockOnSend.mockReturnValue(sendPromise);

      render(<InputArea onSend={mockOnSend} />);

      const textarea = screen.getByRole('textbox');
      await user.type(textarea, 'Hello');
      await user.click(screen.getByRole('button', { name: /send/i }));

      expect(textarea).toBeDisabled();

      resolvePromise!();
      await waitFor(() => {
        expect(textarea).not.toBeDisabled();
      });
    });
  });

  describe('AC10: Input disabled while Annie responds', () => {
    it('should disable input when disabled prop is true', () => {
      render(<InputArea onSend={mockOnSend} disabled={true} />);

      expect(screen.getByRole('textbox')).toBeDisabled();
      expect(screen.getByRole('button', { name: /send/i })).toBeDisabled();
    });

    it('should disable file upload button when disabled', () => {
      render(<InputArea onSend={mockOnSend} disabled={true} />);

      expect(screen.getByRole('button', { name: /attach/i })).toBeDisabled();
    });
  });

  describe('AC11: Character count indicator', () => {
    it('should not show character count for short messages', async () => {
      const user = userEvent.setup();
      render(<InputArea onSend={mockOnSend} />);

      const textarea = screen.getByRole('textbox');
      await user.type(textarea, 'Short message');

      expect(screen.queryByText(/\d+$/)).not.toBeInTheDocument();
    });

    it('should show character count for messages over 500 chars', async () => {
      const user = userEvent.setup();
      render(<InputArea onSend={mockOnSend} />);

      const textarea = screen.getByRole('textbox');
      const longText = 'a'.repeat(550);
      await user.type(textarea, longText);

      expect(screen.getByText('550')).toBeInTheDocument();
    });
  });

  describe('File attachment button', () => {
    it('should render file attachment button', () => {
      render(<InputArea onSend={mockOnSend} />);
      expect(screen.getByRole('button', { name: /attach/i })).toBeInTheDocument();
    });

    it('should have hidden file input', () => {
      render(<InputArea onSend={mockOnSend} />);
      const fileInput = document.querySelector('input[type="file"]');
      expect(fileInput).toBeInTheDocument();
      expect(fileInput).toHaveClass('hidden');
    });
  });

  describe('Error handling', () => {
    it('should restore message on send error', async () => {
      const user = userEvent.setup();
      mockOnSend.mockRejectedValue(new Error('Network error'));

      render(<InputArea onSend={mockOnSend} />);

      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
      await user.type(textarea, 'Hello');
      await user.click(screen.getByRole('button', { name: /send/i }));

      await waitFor(() => {
        expect(textarea.value).toBe('Hello');
      });
    });
  });

  describe('Clear input after send', () => {
    it('should clear textarea after successful send', async () => {
      const user = userEvent.setup();
      render(<InputArea onSend={mockOnSend} />);

      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
      await user.type(textarea, 'Hello');
      await user.click(screen.getByRole('button', { name: /send/i }));

      await waitFor(() => {
        expect(textarea.value).toBe('');
      });
    });
  });
});
