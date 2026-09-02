import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import DocumentViewer from '../components/DocumentViewer';

// Mock API client
vi.mock('../api/client', () => ({
  default: {
    getDocuments: vi.fn(),
    getDocument: vi.fn(),
    getDocumentVersions: vi.fn(),
    getDocumentVersion: vi.fn(),
    bulkDeleteDocuments: vi.fn(),
  },
}));

import api from '../api/client';

const mockDocuments = [
  {
    doc_id: 'insurance_policy',
    name: 'insurance_policy.pdf',
    role: 'evidence',
    status: 'OK',
    total_pages: 3,
    total_chunks: 5,
    total_characters: 1500,
    file_size: 5000,
    file_type: '.pdf',
    uploaded_at: '2026-09-01T10:00:00Z',
    version_number: 2,
    supported_requirements: [
      { requirement_id: 'REQ-001', title: 'Insurance Coverage', status: 'SATISFIED' },
    ],
  },
  {
    doc_id: 'requirements_doc',
    name: 'requirements.pdf',
    role: 'requirements',
    status: 'OK',
    total_pages: 1,
    total_chunks: 2,
    total_characters: 500,
    file_size: 2000,
    file_type: '.pdf',
    uploaded_at: '2026-09-01T09:00:00Z',
    supported_requirements: [],
  },
];

const mockDocumentDetail = {
  doc_id: 'insurance_policy',
  name: 'insurance_policy.pdf',
  role: 'evidence',
  status: 'OK',
  total_pages: 3,
  total_chunks: 5,
  total_characters: 1500,
  file_size: 5000,
  file_type: '.pdf',
  uploaded_at: '2026-09-01T10:00:00Z',
  raw_text: 'Insurance policy text content here.',
  chunks: [
    { chunk_id: 'c1', chunk_index: 0, text: 'Insurance policy text content here.', page_number: 1, token_estimate: 50 },
  ],
  supported_requirements: [
    { requirement_id: 'REQ-001', title: 'Insurance Coverage', status: 'SATISFIED', quote: 'Coverage limit $1M', page_number: 1 },
  ],
};

const mockVersions = [
  {
    version_id: 'insurance_policy_v1',
    version_number: 1,
    name: 'insurance_policy_old.pdf',
    role: 'evidence',
    uploaded_at: '2026-08-15T10:00:00Z',
    uploaded_by: 'user1',
  },
  {
    version_id: 'insurance_policy_v2',
    version_number: 2,
    name: 'insurance_policy.pdf',
    role: 'evidence',
    uploaded_at: '2026-09-01T10:00:00Z',
    uploaded_by: 'user1',
  },
];

function renderViewer(projectId = 'proj-1') {
  return render(<DocumentViewer projectId={projectId} />);
}

describe('DocumentViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Loading state', () => {
    it('shows loading state', () => {
      api.getDocuments.mockReturnValue(new Promise(() => {}));
      renderViewer();
      expect(screen.getByText(/Loading document library/)).toBeInTheDocument();
    });
  });

  describe('Empty state', () => {
    it('shows empty state when no documents', async () => {
      api.getDocuments.mockResolvedValue([]);
      renderViewer();
      await waitFor(() => {
        expect(screen.getByText('No Documents Uploaded')).toBeInTheDocument();
      });
    });
  });

  describe('Document list', () => {
    it('renders document list', async () => {
      api.getDocuments.mockResolvedValue(mockDocuments);
      api.getDocument.mockResolvedValue(mockDocumentDetail);
      api.getDocumentVersions.mockResolvedValue(mockVersions);
      renderViewer();
      await waitFor(() => {
        expect(screen.getByText('insurance_policy.pdf')).toBeInTheDocument();
        expect(screen.getByText('requirements.pdf')).toBeInTheDocument();
      });
    });

    it('shows document counts', async () => {
      api.getDocuments.mockResolvedValue(mockDocuments);
      api.getDocument.mockResolvedValue(mockDocumentDetail);
      api.getDocumentVersions.mockResolvedValue(mockVersions);
      renderViewer();
      await waitFor(() => {
        // Text may be split across elements
        const totalText = screen.getByText((content) => content.includes('Total Files'));
        expect(totalText).toBeInTheDocument();
      });
    });

    it('shows version indicator for versioned documents', async () => {
      api.getDocuments.mockResolvedValue(mockDocuments);
      api.getDocument.mockResolvedValue(mockDocumentDetail);
      api.getDocumentVersions.mockResolvedValue(mockVersions);
      renderViewer();
      await waitFor(() => {
        // Version 2 badge should appear for insurance_policy
        const v2Badge = screen.getByText('v2');
        expect(v2Badge).toBeInTheDocument();
      });
    });
  });

  describe('Version history', () => {
    it('renders version history panel when versions exist', async () => {
      api.getDocuments.mockResolvedValue(mockDocuments);
      api.getDocument.mockResolvedValue(mockDocumentDetail);
      api.getDocumentVersions.mockResolvedValue(mockVersions);
      renderViewer();
      await waitFor(() => {
        expect(screen.getByText(/Version History/)).toBeInTheDocument();
        expect(screen.getByText(/2 versions/)).toBeInTheDocument();
      });
    });

    it('shows version buttons', async () => {
      api.getDocuments.mockResolvedValue(mockDocuments);
      api.getDocument.mockResolvedValue(mockDocumentDetail);
      api.getDocumentVersions.mockResolvedValue(mockVersions);
      renderViewer();
      await waitFor(() => {
        // Version buttons contain v1 and v2 text
        const buttons = screen.getAllByRole('button');
        const versionButtons = buttons.filter(b => b.textContent.includes('v1') || b.textContent.includes('v2'));
        expect(versionButtons.length).toBeGreaterThanOrEqual(2);
      });
    });

    it('shows viewing indicator for selected version', async () => {
      api.getDocuments.mockResolvedValue(mockDocuments);
      api.getDocument.mockResolvedValue(mockDocumentDetail);
      api.getDocumentVersions.mockResolvedValue(mockVersions);
      renderViewer();
      await waitFor(() => {
        expect(screen.getByText(/Viewing v/)).toBeInTheDocument();
      });
    });

    it('handles empty version history gracefully', async () => {
      api.getDocuments.mockResolvedValue(mockDocuments);
      api.getDocument.mockResolvedValue(mockDocumentDetail);
      api.getDocumentVersions.mockResolvedValue([]);
      renderViewer();
      await waitFor(() => {
        expect(screen.getByText('insurance_policy.pdf')).toBeInTheDocument();
      });
      // Version History panel should not appear
      expect(screen.queryByText(/Version History/)).not.toBeInTheDocument();
    });
  });

  describe('Document detail', () => {
    it('shows document overview with name and metadata', async () => {
      api.getDocuments.mockResolvedValue(mockDocuments);
      api.getDocument.mockResolvedValue(mockDocumentDetail);
      api.getDocumentVersions.mockResolvedValue(mockVersions);
      renderViewer();
      await waitFor(() => {
        // Name appears in both list and detail view
        const nameElements = screen.getAllByText('insurance_policy.pdf');
        expect(nameElements.length).toBeGreaterThanOrEqual(2);
        // Characters count may be formatted differently
        const charText = screen.getByText((content) => content.includes('characters'));
        expect(charText).toBeInTheDocument();
      });
    });

    it('shows supported requirements', async () => {
      api.getDocuments.mockResolvedValue(mockDocuments);
      api.getDocument.mockResolvedValue(mockDocumentDetail);
      api.getDocumentVersions.mockResolvedValue(mockVersions);
      renderViewer();
      await waitFor(() => {
        expect(screen.getByText(/Verified Citations/)).toBeInTheDocument();
        expect(screen.getByText('REQ-001')).toBeInTheDocument();
      });
    });

    it('renders document chunks', async () => {
      api.getDocuments.mockResolvedValue(mockDocuments);
      api.getDocument.mockResolvedValue(mockDocumentDetail);
      api.getDocumentVersions.mockResolvedValue(mockVersions);
      renderViewer();
      await waitFor(() => {
        expect(screen.getByText(/Insurance policy text content here/)).toBeInTheDocument();
      });
    });
  });
});
