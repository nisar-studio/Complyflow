import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ShieldCheck, Plus, LayoutDashboard, LogOut, ChevronDown, User } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const ROLE_BADGE = {
  ADMIN:    { label: 'Admin',    cls: 'bg-purple-500/15 text-purple-400 border-purple-500/25' },
  AUDITOR:  { label: 'Auditor',  cls: 'bg-brand-500/15 text-brand-400 border-brand-500/25' },
  REVIEWER: { label: 'Reviewer', cls: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/25' },
  VIEWER:   { label: 'Viewer',   cls: 'bg-slate-500/15 text-slate-400 border-slate-500/25' },
};

export default function Navbar({ projectRole }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  const isActive = (path) => {
    if (path === '/') return location.pathname === '/';
    return location.pathname.startsWith(path);
  };

  const handleLogout = async () => {
    setMenuOpen(false);
    await logout();
    navigate('/login');
  };

  const badge = projectRole ? ROLE_BADGE[projectRole] : null;

  return (
    <header className="sticky top-0 z-50 border-b border-slate-800 bg-slate-950/80 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand */}
        <Link to="/" className="flex items-center space-x-3 group">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 p-0.5 shadow-lg shadow-brand-500/20 group-hover:scale-105 transition-transform">
            <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
              <ShieldCheck className="w-5 h-5 text-brand-400" />
            </div>
          </div>
          <div>
            <span className="text-lg font-bold bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-200 to-slate-400">
              ComplyFlow
            </span>
            <span className="hidden sm:inline-block ml-2 px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider rounded bg-brand-500/10 text-brand-400 border border-brand-500/20">
              AI Agent
            </span>
          </div>
        </Link>

        {/* Right side */}
        <nav className="flex items-center space-x-1 sm:space-x-3">
          {user && (
            <Link
              to="/dashboard"
              className={`flex items-center space-x-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive('/dashboard')
                  ? 'bg-slate-900 text-white border border-slate-800'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
              }`}
            >
              <LayoutDashboard className="w-4 h-4" />
              <span className="hidden sm:inline">Dashboard</span>
            </Link>
          )}

          {user && (
            <Link
              to="/projects/new"
              className="hidden sm:flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-semibold bg-brand-600 hover:bg-brand-500 text-white shadow-lg shadow-brand-600/25 transition-all hover:scale-[1.02] active:scale-[0.98]"
            >
              <Plus className="w-4 h-4" />
              <span>New Check</span>
            </Link>
          )}

          {user ? (
            <div className="relative">
              <button
                onClick={() => setMenuOpen((v) => !v)}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-900 hover:bg-slate-800 text-sm text-slate-300 transition"
              >
                <User className="w-4 h-4 text-slate-400" />
                <span className="hidden sm:inline max-w-[140px] truncate">{user.name}</span>
                {badge && (
                  <span className={`hidden sm:inline px-1.5 py-0.5 text-[10px] font-mono uppercase rounded border ${badge.cls}`}>
                    {badge.label}
                  </span>
                )}
                <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
              </button>

              {menuOpen && (
                <div className="absolute right-0 mt-2 w-56 rounded-xl border border-slate-700 bg-slate-900 shadow-2xl overflow-hidden z-50">
                  <div className="px-4 py-3 border-b border-slate-800">
                    <p className="text-sm font-medium text-white truncate">{user.name}</p>
                    <p className="text-xs text-slate-500 truncate">{user.email}</p>
                  </div>
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-2 px-4 py-3 text-sm text-red-400 hover:bg-red-500/10 transition"
                  >
                    <LogOut className="w-4 h-4" />
                    Sign out
                  </button>
                </div>
              )}
            </div>
          ) : (
            <Link
              to="/login"
              className="flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-semibold bg-brand-600 hover:bg-brand-500 text-white shadow-lg shadow-brand-600/25 transition-all hover:scale-[1.02] active:scale-[0.98]"
            >
              Sign in
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
