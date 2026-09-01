import React, { useState, useEffect, useCallback } from "react";
import { Bell, Check, CheckCheck, X } from "lucide-react";
import api from "../api/client";

export default function NotificationBell({ projectId, className = "" }) {
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const fetchUnreadCount = useCallback(async () => {
    try {
      const data = await api.getUnreadCount(projectId || null);
      setUnreadCount(data.unread_count || 0);
    } catch {
      // silently fail
    }
  }, [projectId]);

  const fetchNotifications = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getNotifications({ project_id: projectId || undefined, limit: 20 });
      setNotifications(data.notifications || []);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 30000); // poll every 30s
    return () => clearInterval(interval);
  }, [fetchUnreadCount]);

  useEffect(() => {
    if (isOpen) {
      fetchNotifications();
    }
  }, [isOpen, fetchNotifications]);

  const handleMarkRead = async (notifId) => {
    try {
      await api.markNotificationRead(notifId);
      setNotifications(prev => prev.map(n => n.notification_id === notifId ? { ...n, is_read: true } : n));
      setUnreadCount(prev => Math.max(0, prev - 1));
    } catch {
      // silently fail
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await api.markAllNotificationsRead(projectId || undefined);
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch {
      // silently fail
    }
  };

  const formatTime = (dateStr) => {
    if (!dateStr) return "";
    try {
      const d = new Date(dateStr);
      const now = new Date();
      const diff = now - d;
      if (diff < 60000) return "just now";
      if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
      if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
      return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    } catch {
      return dateStr;
    }
  };

  return (
    <div className={`relative ${className}`}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 text-slate-400 hover:text-white transition-colors"
        title="Notifications"
      >
        <Bell className="w-5 h-5" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-red-500 text-white text-[10px] font-bold px-1">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div className="absolute right-0 top-full mt-2 w-80 max-h-96 bg-slate-900 border border-slate-800 rounded-xl shadow-2xl z-50 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
              <h3 className="text-sm font-bold text-white">Notifications</h3>
              <div className="flex items-center gap-2">
                {unreadCount > 0 && (
                  <button
                    onClick={handleMarkAllRead}
                    className="text-[10px] text-brand-400 hover:text-brand-300 font-mono"
                  >
                    Mark all read
                  </button>
                )}
                <button
                  onClick={() => setIsOpen(false)}
                  className="text-slate-400 hover:text-white"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="overflow-y-auto max-h-80">
              {loading ? (
                <div className="px-4 py-8 text-center text-slate-500 text-xs font-mono">
                  Loading...
                </div>
              ) : notifications.length === 0 ? (
                <div className="px-4 py-8 text-center text-slate-500 text-xs font-mono">
                  No notifications
                </div>
              ) : (
                notifications.map((notif) => (
                  <div
                    key={notif.notification_id}
                    className={`px-4 py-3 border-b border-slate-800/50 transition-colors ${
                      notif.is_read ? "bg-transparent" : "bg-slate-800/30"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-semibold text-white">
                            {notif.title}
                          </span>
                          {!notif.is_read && (
                            <span className="w-1.5 h-1.5 rounded-full bg-brand-400 flex-shrink-0" />
                          )}
                        </div>
                        <p className="text-[11px] text-slate-400 mt-0.5 line-clamp-2">
                          {notif.message}
                        </p>
                        <span className="text-[10px] text-slate-600 font-mono mt-1 block">
                          {formatTime(notif.created_at)}
                        </span>
                      </div>
                      {!notif.is_read && (
                        <button
                          onClick={() => handleMarkRead(notif.notification_id)}
                          className="text-slate-500 hover:text-brand-400 flex-shrink-0 mt-0.5"
                          title="Mark as read"
                        >
                          <Check className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
