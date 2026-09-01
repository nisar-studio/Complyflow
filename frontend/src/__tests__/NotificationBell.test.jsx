import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import NotificationBell from '../components/NotificationBell';

// Mock the API client
vi.mock('../api/client', () => ({
  default: {
    getUnreadCount: vi.fn(),
    getNotifications: vi.fn(),
    markNotificationRead: vi.fn(),
    markAllNotificationsRead: vi.fn(),
  },
}));

import api from '../api/client';

function makeNotifications(count = 2) {
  return Array.from({ length: count }, (_, i) => ({
    notification_id: `notif-${i + 1}`,
    type: 'TASK_ASSIGNED',
    title: `Notification ${i + 1}`,
    message: `Message ${i + 1}`,
    is_read: false,
    created_at: new Date().toISOString(),
    project_id: 'proj-1',
  }));
}

describe('NotificationBell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getUnreadCount.mockResolvedValue({ unread_count: 0 });
    api.getNotifications.mockResolvedValue({ notifications: [] });
  });

  it('renders bell icon', () => {
    render(<NotificationBell />);
    expect(screen.getByTitle('Notifications')).toBeInTheDocument();
  });

  it('displays unread count badge when count > 0', async () => {
    api.getUnreadCount.mockResolvedValue({ unread_count: 3 });
    render(<NotificationBell />);
    await waitFor(() => {
      expect(screen.getByText('3')).toBeInTheDocument();
    });
  });

  it('does not display badge when count is 0', async () => {
    api.getUnreadCount.mockResolvedValue({ unread_count: 0 });
    render(<NotificationBell />);
    await waitFor(() => {
      expect(screen.queryByText('0')).not.toBeInTheDocument();
    });
  });

  it('shows "99+" for counts over 99', async () => {
    api.getUnreadCount.mockResolvedValue({ unread_count: 150 });
    render(<NotificationBell />);
    await waitFor(() => {
      expect(screen.getByText('99+')).toBeInTheDocument();
    });
  });

  it('opens dropdown on click and fetches notifications', async () => {
    const notifs = makeNotifications(2);
    api.getNotifications.mockResolvedValue({ notifications: notifs });

    render(<NotificationBell />);
    const bellButton = screen.getByTitle('Notifications');
    await userEvent.click(bellButton);

    await waitFor(() => {
      expect(screen.getByText('Notification 1')).toBeInTheDocument();
      expect(screen.getByText('Notification 2')).toBeInTheDocument();
    });
    expect(api.getNotifications).toHaveBeenCalled();
  });

  it('shows loading state while fetching', async () => {
    let resolvePromise;
    api.getNotifications.mockReturnValueOnce(
      new Promise((resolve) => { resolvePromise = resolve; })
    );

    render(<NotificationBell />);
    await userEvent.click(screen.getByTitle('Notifications'));

    await waitFor(() => {
      expect(screen.getByText('Loading...')).toBeInTheDocument();
    });

    resolvePromise({ notifications: [] });
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });
  });

  it('shows empty state when no notifications', async () => {
    api.getNotifications.mockResolvedValue({ notifications: [] });
    render(<NotificationBell />);
    await userEvent.click(screen.getByTitle('Notifications'));

    await waitFor(() => {
      expect(screen.getByText('No notifications')).toBeInTheDocument();
    });
  });

  it('marks single notification as read', async () => {
    const notifs = makeNotifications(1);
    api.getNotifications.mockResolvedValue({ notifications: notifs });
    api.markNotificationRead.mockResolvedValue({ status: 'read' });

    render(<NotificationBell />);
    await userEvent.click(screen.getByTitle('Notifications'));

    await waitFor(() => {
      expect(screen.getByText('Notification 1')).toBeInTheDocument();
    });

    const markReadBtn = screen.getByTitle('Mark as read');
    await userEvent.click(markReadBtn);

    expect(api.markNotificationRead).toHaveBeenCalledWith('notif-1');
  });

  it('marks all notifications as read', async () => {
    api.getUnreadCount.mockResolvedValue({ unread_count: 2 });
    const notifs = makeNotifications(2);
    api.getNotifications.mockResolvedValue({ notifications: notifs });
    api.markAllNotificationsRead.mockResolvedValue({ count: 2 });

    render(<NotificationBell />);
    await userEvent.click(screen.getByTitle('Notifications'));

    await waitFor(() => {
      expect(screen.getByText('Mark all read')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText('Mark all read'));
    expect(api.markAllNotificationsRead).toHaveBeenCalled();
  });

  it('closes dropdown when clicking outside', async () => {
    api.getNotifications.mockResolvedValue({ notifications: makeNotifications(1) });
    render(<NotificationBell />);
    await userEvent.click(screen.getByTitle('Notifications'));

    await waitFor(() => {
      expect(screen.getByText('Notification 1')).toBeInTheDocument();
    });

    // Click the backdrop overlay
    const backdrop = document.querySelector('.fixed.inset-0');
    if (backdrop) fireEvent.click(backdrop);

    await waitFor(() => {
      expect(screen.queryByText('Notification 1')).not.toBeInTheDocument();
    });
  });

  it('passes projectId to API calls', async () => {
    api.getUnreadCount.mockResolvedValue({ unread_count: 1 });
    api.getNotifications.mockResolvedValue({ notifications: makeNotifications(1) });

    render(<NotificationBell projectId="proj-123" />);
    await waitFor(() => {
      expect(api.getUnreadCount).toHaveBeenCalledWith('proj-123');
    });

    await userEvent.click(screen.getByTitle('Notifications'));
    await waitFor(() => {
      expect(api.getNotifications).toHaveBeenCalledWith(
        expect.objectContaining({ project_id: 'proj-123' })
      );
    });
  });
});
