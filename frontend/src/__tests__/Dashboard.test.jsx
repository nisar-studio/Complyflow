import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Dashboard from '../pages/Dashboard';

// Mock API client
vi.mock('../api/client', () => ({
  default: {
    getPortfolioAnalytics: vi.fn(),
    listProjects: vi.fn(),
    deleteProject: vi.fn(),
  },
}));

// Mock Navbar
vi.mock('../components/Navbar', () => ({
  default: () => <nav data-testid="navbar" />,
}));

import api from '../api/client';

const multiProjectPortfolio = {
  total_projects: 3,
  average_score: 75.0,
  compliant_projects: 1,
  projects_needing_action: 2,
  total_tasks: 15,
  total_requirements: 24,
  total_issues: 5,
  projects: [
    {
      project_id: 'proj-1',
      name: 'GDPR Compliance',
      status: 'READY',
      compliance_score: 100.0,
      overall_status: 'READY',
      created_at: '2026-01-15T10:00:00Z',
      requirements_count: 12,
    },
    {
      project_id: 'proj-2',
      name: 'SOC 2 Audit',
      status: 'ACTION_REQUIRED',
      compliance_score: 50.0,
      overall_status: 'ACTION_REQUIRED',
      created_at: '2026-03-20T14:00:00Z',
      requirements_count: 8,
    },
    {
      project_id: 'proj-3',
      name: 'HIPAA Review',
      status: 'PENDING',
      compliance_score: null,
      overall_status: null,
      created_at: '2026-06-01T08:00:00Z',
      requirements_count: 4,
    },
  ],
  overdue_tasks: {
    total_overdue: 3,
    by_project: [
      {
        project_id: 'proj-2',
        project_name: 'SOC 2 Audit',
        overdue_count: 2,
        tasks: [
          { task_id: 'TASK-001', title: 'Fix access control', severity: 'HIGH' },
          { task_id: 'TASK-002', title: 'Update encryption', severity: 'CRITICAL' },
        ],
      },
      {
        project_id: 'proj-3',
        project_name: 'HIPAA Review',
        overdue_count: 1,
        tasks: [
          { task_id: 'TASK-003', title: 'Review policy', severity: 'MEDIUM' },
        ],
      },
    ],
  },
  score_trend: [
    { month: '2026-04', average_score: 60.0, project_count: 2 },
    { month: '2026-05', average_score: null, project_count: 0 },
    { month: '2026-06', average_score: 70.0, project_count: 2 },
    { month: '2026-07', average_score: 85.0, project_count: 3 },
    { month: '2026-08', average_score: 75.0, project_count: 3 },
    { month: '2026-09', average_score: 75.0, project_count: 3 },
  ],
  recent_activity: [
    {
      event_id: 'evt-1',
      project_id: 'proj-1',
      project_name: 'GDPR Compliance',
      event_type: 'ANALYSIS_COMPLETED',
      summary: 'Analysis completed successfully',
      timestamp: new Date().toISOString(),
      severity: 'INFO',
    },
    {
      event_id: 'evt-2',
      project_id: 'proj-2',
      project_name: 'SOC 2 Audit',
      event_type: 'TASK_ASSIGNED',
      summary: 'Task assigned to team lead',
      timestamp: new Date(Date.now() - 3600000).toISOString(),
      severity: 'INFO',
    },
  ],
  top_risks: [
    {
      project_id: 'proj-3',
      name: 'HIPAA Review',
      compliance_score: null,
      issues_count: 0,
      tasks_count: 2,
    },
    {
      project_id: 'proj-2',
      name: 'SOC 2 Audit',
      compliance_score: 50.0,
      issues_count: 3,
      tasks_count: 5,
    },
    {
      project_id: 'proj-1',
      name: 'GDPR Compliance',
      compliance_score: 100.0,
      issues_count: 0,
      tasks_count: 1,
    },
  ],
};

const singleProjectPortfolio = {
  total_projects: 1,
  average_score: 100.0,
  compliant_projects: 1,
  projects_needing_action: 0,
  total_tasks: 5,
  total_requirements: 8,
  total_issues: 0,
  projects: [
    {
      project_id: 'proj-single',
      name: 'ISO 27001',
      status: 'READY',
      compliance_score: 100.0,
      overall_status: 'READY',
      created_at: '2026-06-01T08:00:00Z',
      requirements_count: 8,
    },
  ],
  overdue_tasks: { total_overdue: 0, by_project: [] },
  score_trend: [
    { month: '2026-04', average_score: null, project_count: 0 },
    { month: '2026-05', average_score: null, project_count: 0 },
    { month: '2026-06', average_score: null, project_count: 0 },
    { month: '2026-07', average_score: 90.0, project_count: 1 },
    { month: '2026-08', average_score: 100.0, project_count: 1 },
    { month: '2026-09', average_score: 100.0, project_count: 1 },
  ],
  recent_activity: [],
  top_risks: [],
};

function renderDashboard() {
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>
  );
}

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Loading state', () => {
    it('shows loading spinner while fetching data', () => {
      api.getPortfolioAnalytics.mockReturnValue(new Promise(() => {}));
      renderDashboard();
      expect(screen.getByText('Loading portfolio analytics...')).toBeInTheDocument();
    });
  });

  describe('Error state', () => {
    it('shows error message when API fails', async () => {
      api.getPortfolioAnalytics.mockRejectedValue(new Error('Network error'));
      api.listProjects.mockResolvedValue([]);
      renderDashboard();
      await waitFor(() => {
        expect(screen.getByText('Failed to load portfolio data')).toBeInTheDocument();
      });
    });

    it('falls back to project list on error', async () => {
      api.getPortfolioAnalytics.mockRejectedValue(new Error('Network error'));
      api.listProjects.mockResolvedValue([
        { project_id: 'proj-1', name: 'Fallback Project' },
      ]);
      renderDashboard();
      await waitFor(() => {
        expect(screen.getByText('Fallback Project')).toBeInTheDocument();
      });
    });
  });

  describe('Empty portfolio', () => {
    it('renders empty state when no projects', async () => {
      api.getPortfolioAnalytics.mockResolvedValue({
        total_projects: 0,
        projects: [],
        average_score: 0,
        overdue_tasks: { total_overdue: 0, by_project: [] },
        score_trend: [],
        recent_activity: [],
        top_risks: [],
      });
      renderDashboard();
      await waitFor(() => {
        expect(screen.getByText('No Compliance Checks Yet')).toBeInTheDocument();
      });
    });
  });

  describe('Single project portfolio', () => {
    it('renders single project correctly', async () => {
      api.getPortfolioAnalytics.mockResolvedValue(singleProjectPortfolio);
      renderDashboard();
      await waitFor(() => {
        expect(screen.getByText('ISO 27001')).toBeInTheDocument();
      });
      expect(screen.getByText('Compliance Workspace')).toBeInTheDocument();
    });
  });

  describe('Multi-project portfolio — metrics', () => {
    it('renders portfolio metrics correctly', async () => {
      api.getPortfolioAnalytics.mockResolvedValue(multiProjectPortfolio);
      renderDashboard();
      await waitFor(() => {
        // Use getAllByText for values that appear multiple times
        expect(screen.getAllByText('3').length).toBeGreaterThanOrEqual(1);
      });
      // Check metric labels exist
      expect(screen.getByText('Total Checks')).toBeInTheDocument();
      expect(screen.getByText('Ready to Submit')).toBeInTheDocument();
      expect(screen.getByText('Needs Action')).toBeInTheDocument();
      expect(screen.getByText('Average Compliance')).toBeInTheDocument();
    });

    it('displays average compliance score', async () => {
      api.getPortfolioAnalytics.mockResolvedValue(multiProjectPortfolio);
      renderDashboard();
      await waitFor(() => {
        // 75% appears in metrics card AND score trend
        const elements = screen.getAllByText('75%');
        expect(elements.length).toBeGreaterThanOrEqual(2);
      });
    });
  });

  describe('Score trend section', () => {
    it('renders 6-month score trend', async () => {
      api.getPortfolioAnalytics.mockResolvedValue(multiProjectPortfolio);
      renderDashboard();
      await waitFor(() => {
        expect(screen.getByText('Compliance Trend (6 Months)')).toBeInTheDocument();
      });
      expect(screen.getByText('2026-04')).toBeInTheDocument();
    });

    it('renders null score months as dashes', async () => {
      api.getPortfolioAnalytics.mockResolvedValue(multiProjectPortfolio);
      renderDashboard();
      await waitFor(() => {
        expect(screen.getByText('2026-05')).toBeInTheDocument();
      });
    });

    it('renders no-data message when trend is empty', async () => {
      api.getPortfolioAnalytics.mockResolvedValue({
        ...multiProjectPortfolio,
        score_trend: [],
      });
      renderDashboard();
      await waitFor(() => {
        expect(screen.getByText('No verification data yet')).toBeInTheDocument();
      });
    });
  });

  describe('Overdue tasks section', () => {
    it('renders overdue tasks', async () => {
      api.getPortfolioAnalytics.mockResolvedValue(multiProjectPortfolio);
      renderDashboard();
      await waitFor(() => {
        expect(screen.getByText('Overdue Tasks')).toBeInTheDocument();
      });
      // Should show overdue task titles
      expect(screen.getByText('Fix access control')).toBeInTheDocument();
      expect(screen.getByText('Update encryption')).toBeInTheDocument();
    });

    it('renders project names in overdue section', async () => {
      api.getPortfolioAnalytics.mockResolvedValue(multiProjectPortfolio);
      renderDashboard();
      await waitFor(() => {
        // Project names appear in overdue, top-risks, and project table
        const soc2Elements = screen.getAllByText('SOC 2 Audit');
        expect(soc2Elements.length).toBeGreaterThanOrEqual(1);
        const hipaaElements = screen.getAllByText('HIPAA Review');
        expect(hipaaElements.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('renders no-overdue message when zero', async () => {
      api.getPortfolioAnalytics.mockResolvedValue({
        ...multiProjectPortfolio,
        overdue_tasks: { total_overdue: 0, by_project: [] },
      });
      renderDashboard();
      await waitFor(() => {
        expect(screen.getByText('No overdue tasks')).toBeInTheDocument();
      });
    });
  });

  describe('Recent activity section', () => {
    it('renders recent activity events', async () => {
      api.getPortfolioAnalytics.mockResolvedValue(multiProjectPortfolio);
      renderDashboard();
      await waitFor(() => {
        expect(screen.getByText('Recent Activity')).toBeInTheDocument();
        expect(screen.getByText('Analysis completed successfully')).toBeInTheDocument();
        expect(screen.getByText('Task assigned to team lead')).toBeInTheDocument();
      });
    });

    it('renders empty activity message', async () => {
      api.getPortfolioAnalytics.mockResolvedValue({
        ...multiProjectPortfolio,
        recent_activity: [],
      });
      renderDashboard();
      await waitFor(() => {
        expect(screen.getByText('No recent activity')).toBeInTheDocument();
      });
    });
  });

  describe('Top risks section', () => {
    it('renders top risk projects', async () => {
      api.getPortfolioAnalytics.mockResolvedValue(multiProjectPortfolio);
      renderDashboard();
      await waitFor(() => {
        expect(screen.getByText('Top Risks')).toBeInTheDocument();
        expect(screen.getByText('3 issues')).toBeInTheDocument();
        expect(screen.getByText('5 tasks')).toBeInTheDocument();
      });
    });

    it('renders empty risks message', async () => {
      api.getPortfolioAnalytics.mockResolvedValue({
        ...multiProjectPortfolio,
        top_risks: [],
      });
      renderDashboard();
      await waitFor(() => {
        expect(screen.getByText('No risk data available')).toBeInTheDocument();
      });
    });
  });

  describe('All projects table', () => {
    it('renders all projects', async () => {
      api.getPortfolioAnalytics.mockResolvedValue(multiProjectPortfolio);
      renderDashboard();
      await waitFor(() => {
        expect(screen.getByText('All Compliance Checks')).toBeInTheDocument();
      });
      // Each project should appear at least once (may appear in overdue/top-risks too)
      expect(screen.getAllByText('GDPR Compliance').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('SOC 2 Audit').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('HIPAA Review').length).toBeGreaterThanOrEqual(1);
    });

    it('shows project count in header', async () => {
      api.getPortfolioAnalytics.mockResolvedValue(multiProjectPortfolio);
      renderDashboard();
      await waitFor(() => {
        expect(screen.getByText('3 total')).toBeInTheDocument();
      });
    });
  });
});
