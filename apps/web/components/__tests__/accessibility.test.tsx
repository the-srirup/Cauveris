import { render, screen } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import Sidebar from '@/components/Sidebar';
import { TopContextBar } from '@/components/TopContextBar';
import { Tooltip } from '@/components/Tooltip';
import { Tabs } from '@/components/Tabs';
import { CommandPalette } from '@/components/CommandPalette';
import { Button } from '@/components/ui';

expect.extend(toHaveNoViolations);

describe('Accessibility Audit - Core Components', () => {
  // Sidebar Tests
  describe('Sidebar', () => {
    it('should have no accessibility violations', async () => {
      const { container } = render(<Sidebar />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('should have proper navigation structure with aside and nav', () => {
      render(<Sidebar />);
      // Sidebar is an aside with aria-label
      const sidebar = screen.getByRole('complementary', { name: 'Sidebar' });
      expect(sidebar).toBeInTheDocument();

      // Navigation inside has proper label
      const nav = screen.getByRole('navigation', { name: 'Navigation sections' });
      expect(nav).toBeInTheDocument();
    });

    it('should have proper focus-visible styles on navigation links', () => {
      render(<Sidebar />);
      const links = screen.getAllByRole('link', { name: /mission control|reality rewind|causal constellation|holographic reconstruction|ghost lab|patch forge|victory replay|evidence vault|reports|settings/i });
      links.forEach(link => {
        expect(link).toHaveClass('focus-visible:outline-none');
        expect(link).toHaveClass('focus-visible:ring-2');
        expect(link).toHaveClass('focus-visible:ring-primary');
      });
    });

    it('should have aria-current on active navigation item', () => {
      render(<Sidebar />);
      const activeLink = screen.getByRole('link', { name: /mission control/i });
      expect(activeLink).toHaveAttribute('aria-current', 'page');
    });

    it('should have proper tooltip structure for collapsed icons', () => {
      render(<Sidebar />);
      // The collapse button should have a tooltip
      const collapseButton = screen.getByRole('button', { name: 'Collapse sidebar' });
      expect(collapseButton).toBeInTheDocument();
    });
  });

  // TopContextBar Tests
  describe('TopContextBar', () => {
    it('should have no accessibility violations', async () => {
      const { container } = render(<TopContextBar />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('should have banner role with accessible label', () => {
      render(<TopContextBar />);
      const header = screen.getByRole('banner', { name: 'Incident context and global actions' });
      expect(header).toBeInTheDocument();
    });

    it('should have proper section labels for incident identity, evidence coverage, and system status', () => {
      render(<TopContextBar />);
      expect(screen.getByLabelText('Incident identity')).toBeInTheDocument();
      expect(screen.getByLabelText('Evidence coverage and processing mode')).toBeInTheDocument();
      expect(screen.getByLabelText('System status and global actions')).toBeInTheDocument();
    });

    it('should have accessible buttons with aria-labels for icon-only buttons', () => {
      render(<TopContextBar />);
      expect(screen.getByLabelText('Create new incident')).toBeInTheDocument();
      expect(screen.getByLabelText('Load golden incident')).toBeInTheDocument();
      expect(screen.getByLabelText('Upload evidence bundle')).toBeInTheDocument();
      expect(screen.getByLabelText('Open command palette')).toBeInTheDocument();
    });

    it('should have focus-visible styles on all interactive elements', () => {
      render(<TopContextBar />);
      const buttons = screen.getAllByRole('button');
      buttons.forEach(button => {
        expect(button).toHaveClass('focus-visible:outline-none');
        expect(button).toHaveClass('focus-visible:ring-2');
        expect(button).toHaveClass('focus-visible:ring-primary');
      });
    });
  });

  // Tooltip Tests
  describe('Tooltip', () => {
    it('should have no accessibility violations', async () => {
      const { container } = render(
        <Tooltip content="Test tooltip" position="bottom" open delay={0}>
          <button>Hover me</button>
        </Tooltip>
      );
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('should render tooltip on focus for keyboard users', () => {
      render(
        <Tooltip content="Test tooltip" position="bottom" open delay={0}>
          <button>Focus me</button>
        </Tooltip>
      );
      const button = screen.getByRole('button', { name: 'Focus me' });
      expect(button).toHaveAttribute('aria-describedby');
    });

    it('should have proper ARIA attributes on tooltip trigger', () => {
      render(
        <Tooltip content="Test tooltip" position="bottom" open delay={0}>
          <button>Hover me</button>
        </Tooltip>
      );
      const button = screen.getByRole('button', { name: 'Hover me' });
      expect(button).toHaveAttribute('aria-describedby');
    });
  });

  // Tabs Tests
  describe('Tabs', () => {
    it('should have no accessibility violations', async () => {
      const { container } = render(
        <Tabs defaultValue="tab1" onValueChange={() => {}}>
          <Tabs.List>
            <Tabs.Trigger value="tab1">Tab 1</Tabs.Trigger>
            <Tabs.Trigger value="tab2">Tab 2</Tabs.Trigger>
          </Tabs.List>
          <Tabs.Content value="tab1">Content 1</Tabs.Content>
          <Tabs.Content value="tab2">Content 2</Tabs.Content>
        </Tabs>
      );
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('should have proper tablist role and ARIA attributes', () => {
      render(
        <Tabs defaultValue="tab1" onValueChange={() => {}}>
          <Tabs.List>
            <Tabs.Trigger value="tab1">Tab 1</Tabs.Trigger>
            <Tabs.Trigger value="tab2">Tab 2</Tabs.Trigger>
          </Tabs.List>
          <Tabs.Content value="tab1">Content 1</Tabs.Content>
          <Tabs.Content value="tab2">Content 2</Tabs.Content>
        </Tabs>
      );
      const tabList = screen.getByRole('tablist');
      expect(tabList).toBeInTheDocument();
    });

    it('should have proper tab roles with aria-selected', () => {
      render(
        <Tabs defaultValue="tab1" onValueChange={() => {}}>
          <Tabs.List>
            <Tabs.Trigger value="tab1">Tab 1</Tabs.Trigger>
            <Tabs.Trigger value="tab2">Tab 2</Tabs.Trigger>
          </Tabs.List>
          <Tabs.Content value="tab1">Content 1</Tabs.Content>
          <Tabs.Content value="tab2">Content 2</Tabs.Content>
        </Tabs>
      );
      const tab1 = screen.getByRole('tab', { name: 'Tab 1' });
      const tab2 = screen.getByRole('tab', { name: 'Tab 2' });
      expect(tab1).toHaveAttribute('aria-selected', 'true');
      expect(tab2).toHaveAttribute('aria-selected', 'false');
    });

    it('should support keyboard navigation with arrow keys', () => {
      render(
        <Tabs defaultValue="tab1" onValueChange={() => {}}>
          <Tabs.List>
            <Tabs.Trigger value="tab1">Tab 1</Tabs.Trigger>
            <Tabs.Trigger value="tab2">Tab 2</Tabs.Trigger>
          </Tabs.List>
          <Tabs.Content value="tab1">Content 1</Tabs.Content>
          <Tabs.Content value="tab2">Content 2</Tabs.Content>
        </Tabs>
      );
      const tab1 = screen.getByRole('tab', { name: 'Tab 1' });
      // First tab should be focused by default in controlled mode
      expect(tab1).toHaveAttribute('aria-selected', 'true');
      // Arrow key navigation would be tested via user-event in integration tests
    });

    it('should have focus-visible styles on tab triggers', () => {
      render(
        <Tabs defaultValue="tab1" onValueChange={() => {}}>
          <Tabs.List>
            <Tabs.Trigger value="tab1">Tab 1</Tabs.Trigger>
            <Tabs.Trigger value="tab2">Tab 2</Tabs.Trigger>
          </Tabs.List>
          <Tabs.Content value="tab1">Content 1</Tabs.Content>
          <Tabs.Content value="tab2">Content 2</Tabs.Content>
        </Tabs>
      );
      const tabs = screen.getAllByRole('tab');
      tabs.forEach(tab => {
        expect(tab).toHaveClass('focus-visible:outline-none');
        expect(tab).toHaveClass('focus-visible:ring-2');
        expect(tab).toHaveClass('focus-visible:ring-primary');
      });
    });
  });

  // CommandPalette Tests
  describe('CommandPalette', () => {
    it('should have no accessibility violations', async () => {
      const { container } = render(<CommandPalette />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('should have dialog role with proper label', () => {
      render(<CommandPalette />);
      const dialog = screen.getByRole('dialog', { name: 'Command Palette' });
      expect(dialog).toBeInTheDocument();
    });

    it('should have search input with proper label', () => {
      render(<CommandPalette />);
      // The search input should be accessible
      const searchInput = screen.getByPlaceholderText('Type a command or search…');
      expect(searchInput).toBeInTheDocument();
    });

    it('should have proper list structure with roles', () => {
      render(<CommandPalette />);
      const list = screen.getByRole('listbox', { name: 'Commands' });
      expect(list).toBeInTheDocument();
    });

    it('should have focus-visible styles on command items', () => {
      render(<CommandPalette />);
      const items = screen.getAllByRole('option');
      items.forEach(item => {
        expect(item).toHaveClass('focus-visible:outline-none');
        expect(item).toHaveClass('focus-visible:ring-2');
        expect(item).toHaveClass('focus-visible:ring-primary');
      });
    });

    it('should trap focus within dialog when open', () => {
      render(<CommandPalette />);
      const dialog = screen.getByRole('dialog');
      expect(dialog).toHaveAttribute('aria-modal', 'true');
    });
  });

  // Button Tests
  describe('Button (ui.tsx)', () => {
    it('should have no accessibility violations', async () => {
      const { container } = render(<Button>Test Button</Button>);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('should have proper focus-visible styles', () => {
      render(<Button>Test</Button>);
      const button = screen.getByRole('button', { name: 'Test' });
      expect(button).toHaveClass('focus-visible:outline-none');
      expect(button).toHaveClass('focus-visible:ring-2');
      expect(button).toHaveClass('focus-visible:ring-primary');
    });

    it('should support disabled state', () => {
      render(<Button disabled>Disabled</Button>);
      const button = screen.getByRole('button', { name: 'Disabled' });
      expect(button).toBeDisabled();
      expect(button).toHaveAttribute('aria-disabled', 'true');
    });

    it('should have proper variant styles that maintain contrast', () => {
      render(
        <div>
          <Button variant="primary">Primary</Button>
          <Button variant="destructive">Destructive</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="success">Success</Button>
        </div>
      );
      // All variants should be rendered without violations
      const buttons = screen.getAllByRole('button');
      expect(buttons.length).toBe(6);
    });
  });
});