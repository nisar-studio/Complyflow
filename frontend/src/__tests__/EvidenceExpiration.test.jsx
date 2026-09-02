import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
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
    getEvidenceLifecycle: vi.fn(),
    getExpiringEvidence: vi.fn(),
  },
}));

import api from '../api/client';

const mockDocActive = {
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
  expires_at: '2027-06-30T00:00:00Z',
  version_number: 1,
  supported_requirements: [],
  raw_text: 'Test content',
  chunks: [{ chunk_id: 'c1', text: 'Test', page_number: 1, token_estimate: 1 }],
};

const mockDocExpired = {
  doc_id: 'safety_cert',
  name: 'safety_cert.pdf',
  role: 'evidence',
  status: 'OK',
  total_pages: 1,
  total_chunks: 2,
  total_characters: 500,
  file_size: 2000,
  file_type: '.pdf',
  uploaded_at: '2026-01-01T10:00:00Z',
  expires_at: '2026-06-01T00:00:00Z',
  version_number: 1,
  supported_requirements: [],
  raw_text: 'Safety cert',
  chunks: [{ chunk_id: 'c1', text: 'Safety', page_number: 1, token_estimate: 1 }],
};

const mockDocNoExpiration = {
  doc_id: 'general_policy',
  name: 'general_policy.pdf',
  role: 'evidence',
  status: 'OK',
  total_pages: 1,
  total_chunks: 1,
  total_characters: 300,
  file_size: 1000,
  file_type: '.pdf',
  uploaded_at: '2026-09-01T10:00:00Z',
  expires_at: null,
  version_number: 1,
  supported_requirements: [],
  raw_text: 'General',
  chunks: [{ chunk_id: 'c1', text: 'General', page_number: 1, token_estimate: 1 }],
};

const mockVersionActive = {
  version_id: 'test_proj_insurance_policy_v1',
  project_id: 'test_proj',
  doc_id: 'insurance_policy',
  version_number: 1,
  name: 'insurance_policy.pdf',
  role: 'evidence',
  uploaded_at: '2026-09-01T10:00:00Z',
  expires_at: '2027-06-30T00:00:00Z',
};

const mockVersionExpired = {
  version_id: 'test_proj_safety_cert_v1',
  project_id: 'test_proj',
  doc_id: 'safety_cert',
  version_number: 1,
  name: 'safety_cert.pdf',
  role: 'evidence',
  uploaded_at: '2026-01-01T10:00:00Z',
  expires_at: '2026-06-01T00:00:00Z',
};

function renderViewer(projectId = 'test_proj') {
  return render(<DocumentViewer projectId={projectId} />);
}

describe('EvidenceExpiration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getDocuments.mockResolvedValue([]);
    api.getDocument.mockResolvedValue(null);
    api.getDocumentVersions.mockResolvedValue([]);
    api.getDocumentVersion.mockResolvedValue(null);
    api.bulkDeleteDocuments.mockResolvedValue({});
    api.getEvidenceLifecycle.mockResolvedValue([]);
    api.getExpiringEvidence.mockResolvedValue({ expiring_soon: [], expired: [] });
  });

  describe('Expiration badge in document list', () => {
    it('shows active expiration badge for document with future expires_at', async () => {
      api.getDocuments.mockResolvedValue([mockDocActive]);
      api.getDocument.mockResolvedValue(mockDocActive);
      api.getDocumentVersions.mockResolvedValue([mockVersionActive]);
      api.getDocumentVersion.mockResolvedValue(mockVersionActive);

      renderViewer();

      await waitFor(() => {
        expect(screen.getByText('insurance_policy.pdf')).toBeInTheDocument();
      });

      // The document list item should show an expiration badge
      await waitFor(() => {
        const expBadge = screen.getByText(/Exp:/);
        expect(expBadge).toBeInTheDocument();
      });
    });

    it('shows expired badge for document with past expires_at', async () => {
      api.getDocuments.mockResolvedValue([mockDocExpired]);
      api.getDocument.mockResolvedValue(mockDocExpired);
      api.getDocumentVersions.mockResolvedValue([mockVersionExpired]);
      api.getDocumentVersion.mockResolvedValue(mockVersionExpired);

      renderViewer();

      await waitFor(() => {
        expect(screen.getByText('safety_cert.pdf')).toBeInTheDocument();
      });

      await waitFor(() => {
        expect(screen.getByText('Expired')).toBeInTheDocument();
      });
    });

    it('does not show expiration badge when expires_at is null', async () => {
      api.getDocuments.mockResolvedValue([mockDocNoExpiration]);
      api.getDocument.mockResolvedValue(mockDocNoExpiration);
      api.getDocumentVersions.mockResolvedValue([]);
      api.getDocumentVersion.mockResolvedValue(null);

      renderViewer();

      await waitFor(() => {
        expect(screen.getByText('general_policy.pdf')).toBeInTheDocument();
      });

      // Should not have any expiration-related text in the list
      expect(screen.queryByText(/Expired/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Expires/)).not.toBeInTheDocument();
    });
  });

  describe('Version history expiration display', () => {
    it('shows expiration date in version history when versions exist', async () => {
      api.getDocuments.mockResolvedValue([mockDocActive]);
      api.getDocument.mockResolvedValue(mockDocActive);
      api.getDocumentVersions.mockResolvedValue([mockVersionActive]);
      api.getDocumentVersion.mockResolvedValue(mockVersionActive);

      renderViewer();

      await waitFor(() => {
        expect(screen.getByText(/Version History/)).toBeInTheDocument();
      });

      // Version button should show expiration date
      await waitFor(() => {
        const expButtons = screen.getAllByText(/exp:/);
        expect(expButtons.length).toBeGreaterThanOrEqual(1);
      });
    });
  });

  describe('Multiple documents with mixed expiration states', () => {
    it('renders different badges for different expiration states', async () => {
      api.getDocuments.mockResolvedValue([mockDocActive, mockDocExpired, mockDocNoExpiration]);
      api.getDocument.mockResolvedValue(mockDocActive);
      api.getDocumentVersions.mockResolvedValue([mockVersionActive]);
      api.getDocumentVersion.mockResolvedValue(mockVersionActive);

      renderViewer();

      await waitFor(() => {
        expect(screen.getByText('insurance_policy.pdf')).toBeInTheDocument();
        expect(screen.getByText('safety_cert.pdf')).toBeInTheDocument();
        expect(screen.getByText('general_policy.pdf')).toBeInTheDocument();
      });

      // Active doc should show expiration badge
      await waitFor(() => {
        expect(screen.getByText(/Exp:/)).toBeInTheDocument();
      });

      // Expired doc should show expired badge
      await waitFor(() => {
        expect(screen.getByText('Expired')).toBeInTheDocument();
      });
    });
  });
});
