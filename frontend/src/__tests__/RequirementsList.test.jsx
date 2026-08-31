import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import RequirementsList from '../components/RequirementsList';

// Mock DocumentViewer
vi.mock('../components/DocumentViewer', () => ({
  default: () => <div data-testid="document-viewer" />,
}));

// Mock the API client
vi.mock('../api/client', () => ({
  default: {
    saveOverride: vi.fn(),
    deleteOverride: vi.fn(),
    bulkSaveOverrides: vi.fn(),
    bulkSaveNotes: vi.fn(),
  },
}));

const sampleMatches = [
  {
    requirement_id: 'REQ-001',
    title: 'Access Control Policy',
    description: 'Organization must have a documented access control policy',
    status: 'SATISFIED',
    priority: 'CRITICAL',
    evidence: [
      { document_name: 'policy.pdf', quote: 'All users must be authenticated', page_number: 1 },
    ],
  },
  {
    requirement_id: 'REQ-002',
    title: 'Data Encryption',
    description: 'Data must be encrypted at rest and in transit',
    status: 'MISSING',
    priority: 'HIGH',
    evidence: [],
  },
  {
    requirement_id: 'REQ-003',
    title: 'Incident Response Plan',
    description: 'Organization must maintain an incident response plan',
    status: 'CONFLICT',
    priority: 'MEDIUM',
    evidence: [
      { document_name: 'plan-a.pdf', quote: 'Report within 24 hours', page_number: 3 },
      { document_name: 'plan-b.pdf', quote: 'Report within 72 hours', page_number: 5 },
    ],
  },
];

describe('RequirementsList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset URL search params
    window.history.replaceState = vi.fn();
    Object.defineProperty(window, 'location', {
      value: { search: '', href: 'http://localhost/' },
      writable: true,
    });
  });

  it('renders requirements with their titles', () => {
    render(<RequirementsList matches={sampleMatches} requirements={sampleMatches} />);
    expect(screen.getByText('Access Control Policy')).toBeInTheDocument();
    expect(screen.getByText('Data Encryption')).toBeInTheDocument();
    expect(screen.getByText('Incident Response Plan')).toBeInTheDocument();
  });

  it('displays requirement IDs', () => {
    render(<RequirementsList matches={sampleMatches} requirements={sampleMatches} />);
    expect(screen.getByText('REQ-001')).toBeInTheDocument();
    expect(screen.getByText('REQ-002')).toBeInTheDocument();
    expect(screen.getByText('REQ-003')).toBeInTheDocument();
  });

  it('shows status badges', () => {
    render(<RequirementsList matches={sampleMatches} requirements={sampleMatches} />);
    expect(screen.getByText('SATISFIED')).toBeInTheDocument();
    expect(screen.getByText('MISSING')).toBeInTheDocument();
    expect(screen.getByText('CONFLICT')).toBeInTheDocument();
  });

  it('shows total and showing counts', () => {
    render(<RequirementsList matches={sampleMatches} requirements={sampleMatches} />);
    // Showing count
    expect(screen.getByText(/Showing 3 of 3/)).toBeInTheDocument();
  });

  it('displays empty state when no matches', () => {
    render(<RequirementsList matches={[]} requirements={[]} />);
    expect(screen.getByText('No Matching Requirements')).toBeInTheDocument();
  });

  describe('search and filter', () => {
    it('filters by search query', () => {
      render(<RequirementsList matches={sampleMatches} requirements={sampleMatches} />);
      const searchInput = screen.getByPlaceholderText(/Search by ID, title/);
      fireEvent.change(searchInput, { target: { value: 'encryption' } });
      expect(screen.getByText('Data Encryption')).toBeInTheDocument();
      expect(screen.queryByText('Access Control Policy')).not.toBeInTheDocument();
    });

    it('filters by status pill click (Missing)', () => {
      render(<RequirementsList matches={sampleMatches} requirements={sampleMatches} />);
      // Click the "Missing" status filter button
      const missingBtn = screen.getByText('Missing', { selector: 'button span' });
      fireEvent.click(missingBtn.closest('button'));
      expect(screen.getByText('Data Encryption')).toBeInTheDocument();
      expect(screen.queryByText('Access Control Policy')).not.toBeInTheDocument();
    });
  });

  describe('priority display', () => {
    it('shows priority badges', () => {
      render(<RequirementsList matches={sampleMatches} requirements={sampleMatches} />);
      expect(screen.getByText('CRITICAL')).toBeInTheDocument();
      expect(screen.getByText('HIGH')).toBeInTheDocument();
      expect(screen.getByText('MEDIUM')).toBeInTheDocument();
    });
  });

  describe('override display', () => {
    it('shows override badge when overrides exist', () => {
      const overrides = [
        {
          requirement_id: 'REQ-002',
          overridden_status: 'SATISFIED',
          auditor_reason: 'Verified via alternative evidence',
          created_at: '2025-01-01T00:00:00Z',
        },
      ];
      render(
        <RequirementsList
          matches={sampleMatches}
          requirements={sampleMatches}
          overrides={overrides}
          projectId="proj-1"
        />
      );
      expect(screen.getByText(/Human Override/)).toBeInTheDocument();
    });

    it('shows dual status when overridden (AI line-through + Auditor badge)', () => {
      const overrides = [
        {
          requirement_id: 'REQ-002',
          overridden_status: 'SATISFIED',
          auditor_reason: 'Alternative evidence',
          created_at: '2025-01-01T00:00:00Z',
        },
      ];
      render(
        <RequirementsList
          matches={sampleMatches}
          requirements={sampleMatches}
          overrides={overrides}
          projectId="proj-1"
        />
      );
      expect(screen.getByText(/AI: MISSING/)).toBeInTheDocument();
      expect(screen.getByText(/Auditor: SATISFIED/)).toBeInTheDocument();
    });
  });

  it('renders keyboard shortcut hints', () => {
    render(<RequirementsList matches={sampleMatches} requirements={sampleMatches} />);
    expect(screen.getByText(/Press/)).toBeInTheDocument();
  });
});
