import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import VerificationHistory from '../components/VerificationHistory';

// Mock API client
vi.mock('../api/client', () => ({
  default: {
    getVerificationRuns: vi.fn(),
    getVerificationDelta: vi.fn(),
    downloadReportPdf: vi.fn(),
    downloadReportJson: vi.fn(),
  },
}));

import api from '../api/client';

const mockRunWithSummary = {
  run_id: 'run_2',
  run_number: 2,
  trigger: 'REMEDIATION_VERIFICATION',
  overall_status: 'ACTION_REQUIRED',
  compliance_score: 75.0,
  satisfied_count: 7,
  total_count: 10,
  timestamp: '2026-09-01T10:00:00Z',
  summary: 'Verification completed with 75% compliance.',
  executive_summary: {
    overall_assessment: 'The project has achieved moderate compliance with 75% of requirements satisfied.',
    strengths: [
      'Access control policy is comprehensive and well-documented',
      'Data governance framework meets industry standards',
    ],
    key_risks: [
      'Encryption policy documentation is still missing',
      'Incident response plan needs updated contact information',
    ],
    priority_actions: [
      'Upload encryption policy documentation',
      'Update incident response contact details',
    ],
    notable_findings: [
      'Two requirements moved from MISSING to SATISFIED since last verification',
    ],
  },
};

const mockRunWithNoSummary = {
  run_id: 'run_1',
  run_number: 1,
  trigger: 'INITIAL_ANALYSIS',
  overall_status: 'ACTION_REQUIRED',
  compliance_score: 50.0,
  satisfied_count: 5,
  total_count: 10,
  timestamp: '2026-08-15T10:00:00Z',
  summary: 'Initial analysis completed with 50% compliance.',
  // No executive_summary — simulates pre-v1.2.0 run
};

const mockRunWithNullSummary = {
  run_id: 'run_3',
  run_number: 3,
  trigger: 'REMEDIATION_VERIFICATION',
  overall_status: 'READY',
  compliance_score: 100.0,
  satisfied_count: 10,
  total_count: 10,
  timestamp: '2026-09-02T10:00:00Z',
  summary: 'All requirements satisfied.',
  executive_summary: null, // AI generation failed
};

function renderHistory(projectId = 'proj-1') {
  return render(<VerificationHistory projectId={projectId} />);
}

describe('VerificationHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Loading state', () => {
    it('shows loading state', () => {
      api.getVerificationRuns.mockReturnValue(new Promise(() => {}));
      renderHistory();
      expect(screen.getByText('Loading verification history...')).toBeInTheDocument();
    });
  });

  describe('Empty state', () => {
    it('shows empty state when no runs', async () => {
      api.getVerificationRuns.mockResolvedValue([]);
      renderHistory();
      await waitFor(() => {
        expect(screen.getByText('No Verification Runs Yet')).toBeInTheDocument();
      });
    });
  });

  describe('Runs with executive summary', () => {
    it('renders executive summary when present', async () => {
      api.getVerificationRuns.mockResolvedValue([mockRunWithSummary]);
      renderHistory();
      await waitFor(() => {
        expect(screen.getByText('Executive Summary')).toBeInTheDocument();
        expect(screen.getByText('AI-Generated')).toBeInTheDocument();
        expect(screen.getByText(mockRunWithSummary.executive_summary.overall_assessment)).toBeInTheDocument();
      });
    });

    it('renders strengths section', async () => {
      api.getVerificationRuns.mockResolvedValue([mockRunWithSummary]);
      renderHistory();
      await waitFor(() => {
        expect(screen.getByText('Strengths')).toBeInTheDocument();
        expect(screen.getByText(/Access control policy is comprehensive/)).toBeInTheDocument();
      });
    });

    it('renders key risks section', async () => {
      api.getVerificationRuns.mockResolvedValue([mockRunWithSummary]);
      renderHistory();
      await waitFor(() => {
        expect(screen.getByText('Key Risks')).toBeInTheDocument();
        expect(screen.getByText(/Encryption policy documentation is still missing/)).toBeInTheDocument();
      });
    });

    it('renders priority actions section', async () => {
      api.getVerificationRuns.mockResolvedValue([mockRunWithSummary]);
      renderHistory();
      await waitFor(() => {
        expect(screen.getByText('Priority Actions')).toBeInTheDocument();
        expect(screen.getByText(/Upload encryption policy documentation/)).toBeInTheDocument();
      });
    });

    it('renders notable findings section', async () => {
      api.getVerificationRuns.mockResolvedValue([mockRunWithSummary]);
      renderHistory();
      await waitFor(() => {
        expect(screen.getByText('Notable Findings')).toBeInTheDocument();
        expect(screen.getByText(/Two requirements moved from MISSING/)).toBeInTheDocument();
      });
    });
  });

  describe('Runs without executive summary', () => {
    it('does not show executive summary section for old runs', async () => {
      api.getVerificationRuns.mockResolvedValue([mockRunWithNoSummary]);
      renderHistory();
      await waitFor(() => {
        expect(screen.getByText('Run 1')).toBeInTheDocument();
      });
      expect(screen.queryByText('Executive Summary')).not.toBeInTheDocument();
    });

    it('does not show executive summary section when null', async () => {
      api.getVerificationRuns.mockResolvedValue([mockRunWithNullSummary]);
      renderHistory();
      await waitFor(() => {
        expect(screen.getByText('Run 3')).toBeInTheDocument();
      });
      expect(screen.queryByText('Executive Summary')).not.toBeInTheDocument();
    });
  });

  describe('Mixed runs', () => {
    it('shows summary only for runs that have it', async () => {
      api.getVerificationRuns.mockResolvedValue([mockRunWithNoSummary, mockRunWithSummary]);
      renderHistory();
      await waitFor(() => {
        // Should show the summary for run_2
        expect(screen.getByText('Executive Summary')).toBeInTheDocument();
        expect(screen.getByText(mockRunWithSummary.executive_summary.overall_assessment)).toBeInTheDocument();
      });
    });
  });

  describe('Run selection', () => {
    it('shows run details when selected', async () => {
      api.getVerificationRuns.mockResolvedValue([mockRunWithNoSummary, mockRunWithSummary]);
      renderHistory();
      await waitFor(() => {
        expect(screen.getByText('Run 2')).toBeInTheDocument();
        expect(screen.getByText('Run 1')).toBeInTheDocument();
        expect(screen.getByText('Verification Snapshots & Audit Reports')).toBeInTheDocument();
      });
      // Should show satisfied counts
      expect(screen.getByText(/Satisfied: 7\/10/)).toBeInTheDocument();
      expect(screen.getByText(/Satisfied: 5\/10/)).toBeInTheDocument();
    });
  });
});
