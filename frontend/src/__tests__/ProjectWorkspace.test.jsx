import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ProjectWorkspace from '../pages/ProjectWorkspace';

// Mock child components
vi.mock('../components/Navbar', () => ({
  default: () => <div data-testid="navbar" />,
}));

vi.mock('../components/AgentActivity', () => ({
  default: () => <div data-testid="agent-activity" />,
}));

vi.mock('../components/ComplianceScore', () => ({
  default: () => <div data-testid="compliance-score" />,
}));

vi.mock('../components/RequirementsList', () => ({
  default: () => <div data-testid="requirements-list" />,
}));

vi.mock('../components/RemediationList', () => ({
  default: () => <div data-testid="remediation-list" />,
}));

vi.mock('../components/VerificationHistory', () => ({
  default: () => <div data-testid="verification-history" />,
}));

vi.mock('../components/DocumentViewer', () => ({
  default: () => <div data-testid="document-viewer" />,
}));

vi.mock('../components/AuditTimeline', () => ({
  default: () => <div data-testid="audit-timeline" />,
}));

vi.mock('../components/AnalyticsDashboard', () => ({
  default: () => <div data-testid="analytics-dashboard" />,
}));

vi.mock('../components/ProjectMembersModal', () => ({
  default: () => <div data-testid="project-members-modal" />,
}));

vi.mock('../components/FrameworkModal', () => ({
  default: () => <div data-testid="framework-modal" />,
}));

vi.mock('../hooks/useAgentEvents', () => ({
  useAgentEvents: () => ({
    events: [],
    isLive: false,
    currentTool: null,
    agentStatus: 'idle',
    errorMessage: null,
  }),
}));

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: { user_id: 'user-1', email: 'test@test.com', name: 'Test User' },
    loading: false,
  }),
}));

// Mock the API client
vi.mock('../api/client', () => ({
  default: {
    getProject: vi.fn(),
    getResults: vi.fn(),
    listMembers: vi.fn(),
  },
}));

import api from '../api/client';

const mockProject = {
  project_id: 'proj-1',
  name: 'Test Project',
  status: 'COMPLETED',
  framework: 'SOC 2',
  created_at: '2025-01-01T00:00:00Z',
};

const mockResults = {
  score: 75,
  overall_status: 'IN_PROGRESS',
  satisfied_count: 6,
  total_count: 8,
  missing_count: 1,
  conflict_count: 1,
  matches: [],
  requirements: [],
  overrides: [],
  tasks: [],
  documents: [],
};

const mockMembers = [
  { user_id: 'user-1', email: 'test@test.com', name: 'Test User', role: 'ADMIN' },
];

function renderWorkspace() {
  return render(
    <MemoryRouter initialEntries={['/projects/proj-1']}>
      <Routes>
        <Route path="/projects/:id" element={<ProjectWorkspace />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('ProjectWorkspace', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getProject.mockResolvedValue(mockProject);
    api.getResults.mockResolvedValue(mockResults);
    api.listMembers.mockResolvedValue(mockMembers);
  });

  it('loads project data on mount', async () => {
    renderWorkspace();
    await waitFor(() => {
      expect(api.getProject).toHaveBeenCalledWith('proj-1');
    });
  });

  it('renders all seven tab buttons', async () => {
    renderWorkspace();
    await waitFor(() => {
      expect(screen.getByText(/Agent Workspace/)).toBeInTheDocument();
    });
    expect(screen.getByText(/Compliance Results/)).toBeInTheDocument();
    expect(screen.getByText(/Remediation Plan/)).toBeInTheDocument();
    expect(screen.getByText(/Verification History/)).toBeInTheDocument();
    expect(screen.getByText(/Document.*Evidence Library/)).toBeInTheDocument();
    expect(screen.getByText(/Audit Activity Log/)).toBeInTheDocument();
    expect(screen.getByText(/Analytics/)).toBeInTheDocument();
  });

  it('starts with activity tab active', async () => {
    renderWorkspace();
    await waitFor(() => {
      expect(screen.getByTestId('agent-activity')).toBeInTheDocument();
    });
  });

  it('switches to results tab when clicked', async () => {
    renderWorkspace();
    await waitFor(() => {
      expect(screen.getByText(/Agent Workspace/)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText(/Compliance Results/));
    expect(screen.getByTestId('compliance-score')).toBeInTheDocument();
    expect(screen.getByTestId('requirements-list')).toBeInTheDocument();
  });

  it('switches to remediation tab when clicked', async () => {
    renderWorkspace();
    await waitFor(() => {
      expect(screen.getByText(/Agent Workspace/)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText(/Remediation Plan/));
    expect(screen.getByTestId('remediation-list')).toBeInTheDocument();
  });

  it('switches to history tab when clicked', async () => {
    renderWorkspace();
    await waitFor(() => {
      expect(screen.getByText(/Agent Workspace/)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText(/Verification History/));
    expect(screen.getByTestId('verification-history')).toBeInTheDocument();
  });

  it('switches to documents tab when clicked', async () => {
    renderWorkspace();
    await waitFor(() => {
      expect(screen.getByText(/Agent Workspace/)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText(/Document.*Evidence Library/));
    expect(screen.getByTestId('document-viewer')).toBeInTheDocument();
  });

  it('switches to audit tab when clicked', async () => {
    renderWorkspace();
    await waitFor(() => {
      expect(screen.getByText(/Agent Workspace/)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText(/Audit Activity Log/));
    expect(screen.getByTestId('audit-timeline')).toBeInTheDocument();
  });

  it('switches to analytics tab when clicked', async () => {
    renderWorkspace();
    await waitFor(() => {
      expect(screen.getByText(/Agent Workspace/)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText(/Analytics/));
    expect(screen.getByTestId('analytics-dashboard')).toBeInTheDocument();
  });

  it('shows loading state initially', async () => {
    // Mock a slow API response to keep loading state visible
    let resolveGetProject;
    api.getProject.mockReturnValueOnce(
      new Promise((resolve) => { resolveGetProject = resolve; })
    );
    render(
      <MemoryRouter initialEntries={['/projects/proj-1']}>
        <Routes>
          <Route path="/projects/:id" element={<ProjectWorkspace />} />
        </Routes>
      </MemoryRouter>
    );
    // Loading state renders Navbar + a flex centering div (with Loader2 spinner)
    await waitFor(() => {
      expect(screen.getByTestId('navbar')).toBeInTheDocument();
      expect(document.querySelector('.flex-1.flex.items-center.justify-center')).toBeInTheDocument();
    });
    resolveGetProject(mockProject);
  });
});
