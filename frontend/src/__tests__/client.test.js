import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock axios before importing the client
vi.mock('axios', () => {
  const mockClient = {
    create: vi.fn(() => mockClient),
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  };
  return {
    default: mockClient,
  };
});

import axios from 'axios';
import { api } from '../api/client';

describe('API Client', () => {
  // Capture calls made during module import (before any beforeEach)
  const createCall = axios.create.mock.calls[0]?.[0];

  describe('client configuration', () => {
    it('creates axios instance with correct base configuration', () => {
      expect(createCall).toBeDefined();
      expect(createCall).toEqual(
        expect.objectContaining({
          withCredentials: true,
          xsrfCookieName: 'complyflow_csrf',
          xsrfHeaderName: 'X-CSRF-Token',
        })
      );
    });

    it('sets correct headers', () => {
      expect(createCall).toEqual(
        expect.objectContaining({
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
          }),
        })
      );
    });
  });

  describe('Project endpoints', () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('createProject sends FormData via POST', async () => {
      axios.post.mockResolvedValueOnce({ data: { project_id: 'proj-1' } });
      const result = await api.createProject('Test Project');
      expect(axios.post).toHaveBeenCalledWith(
        '/projects',
        expect.any(FormData),
        expect.objectContaining({
          headers: { 'Content-Type': 'multipart/form-data' },
        })
      );
      expect(result).toEqual({ project_id: 'proj-1' });
    });

    it('listProjects calls GET /projects', async () => {
      axios.get.mockResolvedValueOnce({ data: { projects: [] } });
      const result = await api.listProjects();
      expect(axios.get).toHaveBeenCalledWith('/projects');
      expect(result).toEqual([]);
    });

    it('getProject calls GET /projects/:id', async () => {
      axios.get.mockResolvedValueOnce({ data: { project_id: 'proj-1' } });
      const result = await api.getProject('proj-1');
      expect(axios.get).toHaveBeenCalledWith('/projects/proj-1');
      expect(result).toEqual({ project_id: 'proj-1' });
    });

    it('deleteProject calls DELETE /projects/:id', async () => {
      axios.delete.mockResolvedValueOnce({ data: { ok: true } });
      const result = await api.deleteProject('proj-1');
      expect(axios.delete).toHaveBeenCalledWith('/projects/proj-1');
      expect(result).toEqual({ ok: true });
    });
  });

  describe('Document endpoints', () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('uploadDocuments sends FormData via POST', async () => {
      axios.post.mockResolvedValueOnce({ data: { uploaded: 2 } });
      const file1 = new File(['test'], 'req.txt', { type: 'text/plain' });
      const result = await api.uploadDocuments('proj-1', file1, [], false);
      expect(axios.post).toHaveBeenCalledWith(
        '/projects/proj-1/documents',
        expect.any(FormData),
        expect.objectContaining({
          headers: { 'Content-Type': 'multipart/form-data' },
        })
      );
      expect(result).toEqual({ uploaded: 2 });
    });

    it('getDocuments calls GET /projects/:id/documents', async () => {
      axios.get.mockResolvedValueOnce({ data: { documents: [] } });
      const result = await api.getDocuments('proj-1');
      expect(axios.get).toHaveBeenCalledWith('/projects/proj-1/documents');
      expect(result).toEqual([]);
    });
  });

  describe('Analysis endpoints', () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('startAnalysis calls POST /projects/:id/analyze', async () => {
      axios.post.mockResolvedValueOnce({ data: { status: 'ANALYZING' } });
      const result = await api.startAnalysis('proj-1');
      expect(axios.post).toHaveBeenCalledWith('/projects/proj-1/analyze');
      expect(result).toEqual({ status: 'ANALYZING' });
    });

    it('startVerification calls POST /projects/:id/verify', async () => {
      axios.post.mockResolvedValueOnce({ data: { status: 'VERIFYING' } });
      const result = await api.startVerification('proj-1');
      expect(axios.post).toHaveBeenCalledWith('/projects/proj-1/verify');
      expect(result).toEqual({ status: 'VERIFYING' });
    });
  });

  describe('Results and Events', () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('getResults calls GET /projects/:id/results', async () => {
      axios.get.mockResolvedValueOnce({ data: { score: 75 } });
      const result = await api.getResults('proj-1');
      expect(axios.get).toHaveBeenCalledWith('/projects/proj-1/results');
      expect(result).toEqual({ score: 75 });
    });

    it('getEvents calls GET /projects/:id/events', async () => {
      axios.get.mockResolvedValueOnce({ data: { events: [] } });
      const result = await api.getEvents('proj-1');
      expect(axios.get).toHaveBeenCalledWith('/projects/proj-1/events');
      expect(result).toEqual([]);
    });
  });

  describe('Authentication endpoints', () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('login calls POST /auth/login with credentials', async () => {
      axios.post.mockResolvedValueOnce({ data: { user: { email: 'a@b.com' } } });
      const result = await api.login('a@b.com', 'password');
      expect(axios.post).toHaveBeenCalledWith('/auth/login', {
        email: 'a@b.com',
        password: 'password',
      });
      expect(result).toEqual({ user: { email: 'a@b.com' } });
    });

    it('register calls POST /auth/register', async () => {
      axios.post.mockResolvedValueOnce({ data: { user: { email: 'a@b.com' } } });
      const result = await api.register('a@b.com', 'Test', 'pass');
      expect(axios.post).toHaveBeenCalledWith('/auth/register', {
        email: 'a@b.com',
        name: 'Test',
        password: 'pass',
      });
    });

    it('logout calls POST /auth/logout', async () => {
      axios.post.mockResolvedValueOnce({ data: { ok: true } });
      await api.logout();
      expect(axios.post).toHaveBeenCalledWith('/auth/logout');
    });

    it('getMe calls GET /auth/me', async () => {
      axios.get.mockResolvedValueOnce({ data: { user: { id: '1' } } });
      const result = await api.getMe();
      expect(axios.get).toHaveBeenCalledWith('/auth/me');
      expect(result).toEqual({ id: '1' });
    });
  });

  describe('Task status update', () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('updateTaskStatus calls PUT /projects/:id/tasks/:taskId/status', async () => {
      axios.put.mockResolvedValueOnce({ data: { status: 'RESOLVED' } });
      const result = await api.updateTaskStatus('proj-1', 'task-1', 'RESOLVED');
      expect(axios.put).toHaveBeenCalledWith('/projects/proj-1/tasks/task-1/status', {
        status: 'RESOLVED',
      });
      expect(result).toEqual({ status: 'RESOLVED' });
    });
  });

  describe('Task due date', () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('setTaskDueDate calls PUT /projects/:id/tasks/:taskId/due-date', async () => {
      axios.put.mockResolvedValueOnce({ data: { status: 'updated', due_date: '2026-12-31T23:59:59Z' } });
      const result = await api.setTaskDueDate('proj-1', 'task-1', '2026-12-31T23:59:59Z');
      expect(axios.put).toHaveBeenCalledWith('/projects/proj-1/tasks/task-1/due-date', {
        due_date: '2026-12-31T23:59:59Z',
      });
      expect(result).toEqual({ status: 'updated', due_date: '2026-12-31T23:59:59Z' });
    });

    it('setTaskDueDate with null clears due date', async () => {
      axios.put.mockResolvedValueOnce({ data: { status: 'updated', due_date: null } });
      const result = await api.setTaskDueDate('proj-1', 'task-1', null);
      expect(axios.put).toHaveBeenCalledWith('/projects/proj-1/tasks/task-1/due-date', {
        due_date: null,
      });
      expect(result.due_date).toBeNull();
    });
  });

  describe('Member endpoints', () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('listMembers calls GET /projects/:id/members', async () => {
      axios.get.mockResolvedValueOnce({ data: { members: [] } });
      const result = await api.listMembers('proj-1');
      expect(axios.get).toHaveBeenCalledWith('/projects/proj-1/members');
      expect(result).toEqual([]);
    });

    it('addMember calls POST /projects/:id/members', async () => {
      axios.post.mockResolvedValueOnce({ data: { ok: true } });
      await api.addMember('proj-1', 'user@test.com', 'REVIEWER');
      expect(axios.post).toHaveBeenCalledWith('/projects/proj-1/members', {
        email: 'user@test.com',
        role: 'REVIEWER',
      });
    });
  });

  describe('Override endpoints', () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('saveOverride calls POST with requirement ID', async () => {
      axios.post.mockResolvedValueOnce({ data: { ok: true } });
      await api.saveOverride('proj-1', 'REQ-001', {
        overridden_status: 'SATISFIED',
        auditor_reason: 'Verified',
      });
      expect(axios.post).toHaveBeenCalledWith(
        '/projects/proj-1/requirements/REQ-001/override',
        {
          overridden_status: 'SATISFIED',
          auditor_reason: 'Verified',
        }
      );
    });

    it('deleteOverride calls DELETE with requirement ID', async () => {
      axios.delete.mockResolvedValueOnce({ data: { ok: true } });
      await api.deleteOverride('proj-1', 'REQ-001');
      expect(axios.delete).toHaveBeenCalledWith('/projects/proj-1/requirements/REQ-001/override');
    });
  });

  describe('Analytics endpoints', () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('getProjectAnalytics calls GET /projects/:id/analytics', async () => {
      axios.get.mockResolvedValueOnce({ data: { score_trend: [] } });
      const result = await api.getProjectAnalytics('proj-1');
      expect(axios.get).toHaveBeenCalledWith('/projects/proj-1/analytics');
      expect(result).toEqual({ score_trend: [] });
    });

    it('getPortfolioAnalytics calls GET /analytics/portfolio', async () => {
      axios.get.mockResolvedValueOnce({ data: { projects: [] } });
      const result = await api.getPortfolioAnalytics();
      expect(axios.get).toHaveBeenCalledWith('/analytics/portfolio');
      expect(result).toEqual({ projects: [] });
    });
  });

  describe('Framework endpoints', () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('listFrameworks calls GET /projects/:id/frameworks', async () => {
      axios.get.mockResolvedValueOnce({ data: { frameworks: [] } });
      const result = await api.listFrameworks('proj-1');
      expect(axios.get).toHaveBeenCalledWith('/projects/proj-1/frameworks');
      expect(result).toEqual([]);
    });

    it('applyFramework calls POST /projects/:id/frameworks/:fid/apply', async () => {
      axios.post.mockResolvedValueOnce({ data: { ok: true } });
      await api.applyFramework('proj-1', 'fw-1');
      expect(axios.post).toHaveBeenCalledWith('/projects/proj-1/frameworks/fw-1/apply');
    });
  });
});
