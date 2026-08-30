import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Landing from './pages/Landing';
import Dashboard from './pages/Dashboard';
import NewProject from './pages/NewProject';
import ProjectWorkspace from './pages/ProjectWorkspace';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';

/** Redirect unauthenticated users to /login */
function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <span className="w-8 h-8 border-2 border-brand-400/30 border-t-brand-400 rounded-full animate-spin" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

/** Redirect already-logged-in users away from auth pages */
function GuestOnly({ children }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (user) return <Navigate to="/dashboard" replace />;
  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          {/* Public */}
          <Route path="/" element={<Landing />} />
          <Route
            path="/login"
            element={<GuestOnly><LoginPage /></GuestOnly>}
          />
          <Route
            path="/register"
            element={<GuestOnly><RegisterPage /></GuestOnly>}
          />

          {/* Protected */}
          <Route
            path="/dashboard"
            element={<RequireAuth><Dashboard /></RequireAuth>}
          />
          <Route
            path="/projects/new"
            element={<RequireAuth><NewProject /></RequireAuth>}
          />
          <Route
            path="/projects/:id"
            element={<RequireAuth><ProjectWorkspace /></RequireAuth>}
          />

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Router>
    </AuthProvider>
  );
}
