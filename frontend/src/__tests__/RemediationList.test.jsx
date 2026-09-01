import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import RemediationList from '../components/RemediationList';

// Mock TaskUploadPanel
vi.mock('../components/TaskUploadPanel', () => ({
  default: () => <div data-testid="task-upload-panel" />,
}));

// Mock the API client
vi.mock('../api/client', () => ({
  default: {
    updateTaskStatus: vi.fn(),
    assignTask: vi.fn(),
    setTaskDueDate: vi.fn(),
  },
}));

import api from '../api/client';

// Helper to create fresh task copies (component mutates task.status in-place)
function makeTasks() {
  return [
    {
      task_id: 'TASK-001',
      title: 'Fix access control',
      description: 'Implement proper RBAC',
      severity: 'CRITICAL',
      status: 'OPEN',
      related_requirement_id: 'REQ-001',
    },
    {
      task_id: 'TASK-002',
      title: 'Update privacy policy',
      description: 'Review and update privacy documentation',
      severity: 'MEDIUM',
      status: 'RESOLVED',
      related_requirement_id: 'REQ-002',
    },
    {
      task_id: 'TASK-003',
      title: 'Add encryption',
      description: 'Encrypt data at rest',
      severity: 'HIGH',
      status: 'OPEN',
      related_requirement_id: 'REQ-003',
    },
  ];
}

describe('RemediationList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders all tasks', () => {
    render(<RemediationList tasks={makeTasks()} projectId="proj-1" />);
    expect(screen.getByText('Fix access control')).toBeInTheDocument();
    expect(screen.getByText('Update privacy policy')).toBeInTheDocument();
    expect(screen.getByText('Add encryption')).toBeInTheDocument();
  });

  it('shows task count', () => {
    render(<RemediationList tasks={makeTasks()} projectId="proj-1" />);
    expect(screen.getByText('3 Action Items')).toBeInTheDocument();
  });

  it('shows critical count when there are critical tasks', () => {
    render(<RemediationList tasks={makeTasks()} projectId="proj-1" />);
    expect(screen.getByText('1 Critical')).toBeInTheDocument();
  });

  it('renders empty state when no tasks', () => {
    render(<RemediationList tasks={[]} projectId="proj-1" />);
    expect(screen.getByText('No Action Items Required!')).toBeInTheDocument();
  });

  it('renders empty filter state when no tasks match filters', () => {
    render(<RemediationList tasks={makeTasks()} projectId="proj-1" />);
    const searchInput = screen.getByPlaceholderText(/Search tasks by ID/);
    fireEvent.change(searchInput, { target: { value: 'nonexistent xyz' } });
    expect(screen.getByText(/No remediation tasks match/)).toBeInTheDocument();
  });

  describe('search and filter', () => {
    it('filters tasks by title search', () => {
      render(<RemediationList tasks={makeTasks()} projectId="proj-1" />);
      const searchInput = screen.getByPlaceholderText(/Search tasks by ID/);
      fireEvent.change(searchInput, { target: { value: 'access' } });
      expect(screen.getByText('Fix access control')).toBeInTheDocument();
      expect(screen.queryByText('Update privacy policy')).not.toBeInTheDocument();
    });

    it('filters tasks by severity', () => {
      render(<RemediationList tasks={makeTasks()} projectId="proj-1" />);
      const severitySelect = screen.getByDisplayValue(/All Severities/);
      fireEvent.change(severitySelect, { target: { value: 'CRITICAL' } });
      expect(screen.getByText('Fix access control')).toBeInTheDocument();
      expect(screen.queryByText('Update privacy policy')).not.toBeInTheDocument();
    });
  });

  describe('resolve/reopen', () => {
    it('shows "Mark Resolved" for OPEN tasks', () => {
      render(<RemediationList tasks={makeTasks()} projectId="proj-1" />);
      expect(screen.getAllByText('Mark Resolved').length).toBe(2);
    });

    it('shows "Reopen" for RESOLVED tasks', () => {
      render(<RemediationList tasks={makeTasks()} projectId="proj-1" />);
      expect(screen.getByText('Reopen')).toBeInTheDocument();
    });

    it('calls updateTaskStatus when resolve is clicked', async () => {
      api.updateTaskStatus.mockResolvedValueOnce({});
      const user = userEvent.setup();
      render(<RemediationList tasks={makeTasks()} projectId="proj-1" />);

      const resolveButtons = screen.getAllByText('Mark Resolved');
      await user.click(resolveButtons[0]);

      expect(api.updateTaskStatus).toHaveBeenCalledWith('proj-1', 'TASK-001', 'RESOLVED');
    });

    it('shows success message after resolving', async () => {
      api.updateTaskStatus.mockResolvedValueOnce({});
      const user = userEvent.setup();
      render(<RemediationList tasks={makeTasks()} projectId="proj-1" />);

      const resolveButtons = screen.getAllByText('Mark Resolved');
      await user.click(resolveButtons[0]);

      await waitFor(() => {
        expect(screen.getByText(/resolved successfully/)).toBeInTheDocument();
      });
    });

    it('shows error message on failure', async () => {
      api.updateTaskStatus.mockRejectedValueOnce({
        response: { data: { detail: 'Permission denied' } },
      });
      const user = userEvent.setup();
      render(<RemediationList tasks={makeTasks()} projectId="proj-1" />);

      const resolveButtons = screen.getAllByText('Mark Resolved');
      await user.click(resolveButtons[0]);

      await waitFor(() => {
        expect(screen.getByText('Permission denied')).toBeInTheDocument();
      });
    });

    it('calls updateTaskStatus with correct arguments for resolve', async () => {
      api.updateTaskStatus.mockResolvedValueOnce({});
      const user = userEvent.setup();
      render(<RemediationList tasks={makeTasks()} projectId="proj-1" />);

      const resolveButtons = screen.getAllByText('Mark Resolved');
      expect(resolveButtons.length).toBe(2);
      await user.click(resolveButtons[0]);

      expect(api.updateTaskStatus).toHaveBeenCalledWith('proj-1', 'TASK-001', 'RESOLVED');
    });
  });

  it('does not show resolve/reopen buttons when projectId is not provided', () => {
    render(<RemediationList tasks={makeTasks()} />);
    expect(screen.queryByText('Mark Resolved')).not.toBeInTheDocument();
    expect(screen.queryByText('Reopen')).not.toBeInTheDocument();
  });

  it('displays severity badges', () => {
    render(<RemediationList tasks={makeTasks()} projectId="proj-1" />);
    expect(screen.getByText('CRITICAL SEVERITY')).toBeInTheDocument();
    expect(screen.getByText('MEDIUM SEVERITY')).toBeInTheDocument();
    expect(screen.getByText('HIGH SEVERITY')).toBeInTheDocument();
  });

  it('displays task IDs', () => {
    render(<RemediationList tasks={makeTasks()} projectId="proj-1" />);
    expect(screen.getByText('TASK-001')).toBeInTheDocument();
    expect(screen.getByText('TASK-002')).toBeInTheDocument();
    expect(screen.getByText('TASK-003')).toBeInTheDocument();
  });

  describe('Due Date functionality', () => {
    it('shows set due date button when no due_date is set', () => {
      render(<RemediationList tasks={makeTasks()} projectId="proj-1" />);
      const buttons = screen.getAllByText('Set due date');
      expect(buttons.length).toBe(3); // all tasks have no due_date
    });

    it('shows due date when set', () => {
      const tasks = makeTasks();
      tasks[0].due_date = '2026-12-31T23:59:59Z';
      render(<RemediationList tasks={tasks} projectId="proj-1" />);
      expect(screen.getByText(/Due:/)).toBeInTheDocument();
      // Date formatting varies by locale — just check the element exists
      const dueBadge = screen.getByText(/Due:/).closest('span');
      expect(dueBadge).toBeInTheDocument();
    });

    it('shows overdue badge for past due dates on OPEN tasks', () => {
      const tasks = makeTasks();
      tasks[0].due_date = '2020-01-01T00:00:00Z';
      tasks[0].status = 'OPEN';
      render(<RemediationList tasks={tasks} projectId="proj-1" />);
      expect(screen.getByText('Overdue')).toBeInTheDocument();
    });

    it('does not show overdue for resolved tasks', () => {
      const tasks = makeTasks();
      tasks[0].due_date = '2020-01-01T00:00:00Z';
      tasks[0].status = 'RESOLVED';
      render(<RemediationList tasks={tasks} projectId="proj-1" />);
      expect(screen.queryByText('Overdue')).not.toBeInTheDocument();
    });

    it('shows date input after clicking set due date', async () => {
      const user = userEvent.setup();
      render(<RemediationList tasks={makeTasks()} projectId="proj-1" />);

      const setButtons = screen.getAllByText('Set due date');
      expect(setButtons.length).toBe(3);
      await user.click(setButtons[0]);

      // Date input should appear after clicking
      const dateInput = screen.getByRole('textbox', { type: 'date' });
      expect(dateInput).toBeInTheDocument();

      // Clear button should appear for tasks without due date
      expect(screen.getByText('Cancel')).toBeInTheDocument();
    });

    it('does not show due date UI when projectId is not provided', () => {
      render(<RemediationList tasks={makeTasks()} />);
      expect(screen.queryByText('Set due date')).not.toBeInTheDocument();
    });
  });
});
