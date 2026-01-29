import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HealthIndicator } from '../HealthIndicator';
import type { HealthState } from '@/lib/hooks/useHealth';

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

const healthyState: HealthState = {
  backend: 'ok',
  mcp: 'ok',
  redis: 'ok',
  memories: 'ok',
  llm: 'ok',
};

const degradedState: HealthState = {
  backend: 'ok',
  mcp: 'degraded',
  redis: 'ok',
  memories: 'unavailable',
  llm: 'ok',
};

const allUnavailableState: HealthState = {
  backend: 'unavailable',
  mcp: 'unavailable',
  redis: 'unavailable',
  memories: 'unavailable',
  llm: 'unavailable',
};

describe('HealthIndicator', () => {
  const defaultProps = {
    healthState: healthyState,
    loading: false,
    error: null,
    lastCheck: new Date('2026-01-26T10:00:00Z'),
    hasDegradedServices: false,
  };

  describe('healthy state', () => {
    it('renders correct number of status dots for all services', () => {
      render(<HealthIndicator {...defaultProps} />);

      // Should have 4 service dots (backend, mcp, redis, memories)
      const buttons = screen.getAllByRole('button');
      expect(buttons).toHaveLength(4);
    });

    it('applies green color class for ok status', () => {
      render(<HealthIndicator {...defaultProps} />);

      const buttons = screen.getAllByRole('button');
      buttons.forEach((button) => {
        expect(button).toHaveClass('bg-green-500');
      });
    });

    it('does not show warning indicator when all services healthy', () => {
      render(<HealthIndicator {...defaultProps} />);

      // Warning icon should not be present
      expect(screen.queryByText('Some services are not fully operational')).not.toBeInTheDocument();
    });
  });

  describe('degraded state', () => {
    it('applies yellow color class for degraded status', () => {
      render(
        <HealthIndicator
          {...defaultProps}
          healthState={degradedState}
          hasDegradedServices={true}
        />
      );

      // Find the MCP button (second one, index 1)
      const buttons = screen.getAllByRole('button');
      expect(buttons[1]).toHaveClass('bg-yellow-500');
    });

    it('applies red color class for unavailable status', () => {
      render(
        <HealthIndicator
          {...defaultProps}
          healthState={degradedState}
          hasDegradedServices={true}
        />
      );

      // Find the memories button (fourth one, index 3)
      const buttons = screen.getAllByRole('button');
      expect(buttons[3]).toHaveClass('bg-red-500');
    });

    it('shows warning indicator when services are degraded', () => {
      render(
        <HealthIndicator
          {...defaultProps}
          healthState={degradedState}
          hasDegradedServices={true}
        />
      );

      // Warning tooltip should be present
      expect(screen.getByText('Some services are not fully operational')).toBeInTheDocument();
    });
  });

  describe('loading state', () => {
    it('shows loading skeleton when loading', () => {
      render(<HealthIndicator {...defaultProps} loading={true} />);

      expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'Loading health status');
      expect(screen.getByText('Loading health status...')).toBeInTheDocument();
    });

    it('shows animated pulse effect during loading', () => {
      render(<HealthIndicator {...defaultProps} loading={true} />);

      const skeletonDots = screen
        .getByRole('status')
        .querySelectorAll('.animate-pulse');
      expect(skeletonDots.length).toBeGreaterThan(0);
    });
  });

  describe('error state', () => {
    it('shows error indicator when error and no lastCheck', () => {
      render(
        <HealthIndicator
          {...defaultProps}
          error="Connection refused"
          lastCheck={null}
        />
      );

      expect(screen.getByRole('alert')).toHaveAttribute('aria-label', 'Health check failed');
    });

    it('shows offline text when in error state', () => {
      render(
        <HealthIndicator
          {...defaultProps}
          error="Connection refused"
          lastCheck={null}
        />
      );

      expect(screen.getByText('Offline')).toBeInTheDocument();
    });

    it('shows normal state with error tooltip when error but has lastCheck', () => {
      render(
        <HealthIndicator
          {...defaultProps}
          healthState={healthyState}
          error="Temporary error"
          lastCheck={new Date()}
        />
      );

      // Should still show status dots (graceful degradation - show last known state)
      const buttons = screen.getAllByRole('button');
      expect(buttons.length).toBe(4);
    });
  });

  describe('tooltips', () => {
    it('shows component name in tooltip', async () => {
      render(<HealthIndicator {...defaultProps} />);

      // Tooltip content is always rendered in our mock
      expect(screen.getByText('Backend API')).toBeInTheDocument();
      expect(screen.getByText('MCP Server')).toBeInTheDocument();
      expect(screen.getByText('Redis')).toBeInTheDocument();
      expect(screen.getByText('Memories')).toBeInTheDocument();
    });

    it('shows status text in tooltip', () => {
      render(<HealthIndicator {...defaultProps} />);

      // All services should show "Healthy" in tooltip
      const healthyTexts = screen.getAllByText('Healthy');
      expect(healthyTexts.length).toBe(4);
    });

    it('shows last check timestamp in tooltip', () => {
      const lastCheck = new Date('2026-01-26T10:00:00Z');
      render(<HealthIndicator {...defaultProps} lastCheck={lastCheck} />);

      // Should show formatted time
      const timeString = lastCheck.toLocaleTimeString();
      const lastCheckTexts = screen.getAllByText(`Last checked: ${timeString}`);
      expect(lastCheckTexts.length).toBeGreaterThan(0);
    });
  });

  describe('accessibility', () => {
    it('has accessible status role', () => {
      render(<HealthIndicator {...defaultProps} />);

      expect(screen.getByRole('status')).toHaveAttribute(
        'aria-label',
        'System health indicators'
      );
    });

    it('each dot has accessible label', () => {
      render(<HealthIndicator {...defaultProps} />);

      expect(screen.getByLabelText('Backend API: Healthy')).toBeInTheDocument();
      expect(screen.getByLabelText('MCP Server: Healthy')).toBeInTheDocument();
      expect(screen.getByLabelText('Redis: Healthy')).toBeInTheDocument();
      expect(screen.getByLabelText('Memories: Healthy')).toBeInTheDocument();
    });

    it('degraded services have correct aria labels', () => {
      render(
        <HealthIndicator
          {...defaultProps}
          healthState={degradedState}
          hasDegradedServices={true}
        />
      );

      expect(screen.getByLabelText('MCP Server: Degraded')).toBeInTheDocument();
      expect(screen.getByLabelText('Memories: Unavailable')).toBeInTheDocument();
    });
  });

  describe('transitions', () => {
    it('applies transition classes for smooth color changes', () => {
      render(<HealthIndicator {...defaultProps} />);

      const buttons = screen.getAllByRole('button');
      buttons.forEach((button) => {
        expect(button).toHaveClass('transition-colors', 'duration-300');
      });
    });
  });
});
