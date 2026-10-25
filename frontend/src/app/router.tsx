import type { ReactElement } from "react";
import { Navigate, createBrowserRouter } from "react-router-dom";

import { useAuth } from "../features/auth/AuthContext";
import { AppShell } from "./AppShell";
import { CoursePage } from "../pages/CoursePage";
import { CoursesPage } from "../pages/CoursesPage";
import { DashboardPage } from "../pages/DashboardPage";
import { DiseasePage } from "../pages/DiseasePage";
import { LoginPage } from "../pages/LoginPage";
import { ProgressPage } from "../pages/ProgressPage";
import { RegisterPage } from "../pages/RegisterPage";
import { ReportPage } from "../pages/ReportPage";
import { ScenarioPage } from "../pages/ScenarioPage";
import { SessionPage } from "../pages/SessionPage";
import { SettingsPage } from "../pages/SettingsPage";

function RequireAuth({ children }: { children: ReactElement }) {
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="loading-screen">Loading…</div>;
  }
  if (user === null) {
    return <Navigate to="/login" replace />;
  }
  return <AppShell>{children}</AppShell>;
}

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  {
    path: "/",
    element: (
      <RequireAuth>
        <DashboardPage />
      </RequireAuth>
    ),
  },
  {
    path: "/courses",
    element: (
      <RequireAuth>
        <CoursesPage />
      </RequireAuth>
    ),
  },
  {
    path: "/courses/:courseId",
    element: (
      <RequireAuth>
        <CoursePage />
      </RequireAuth>
    ),
  },
  {
    path: "/diseases/:diseaseId",
    element: (
      <RequireAuth>
        <DiseasePage />
      </RequireAuth>
    ),
  },
  {
    path: "/scenarios/:scenarioId",
    element: (
      <RequireAuth>
        <ScenarioPage />
      </RequireAuth>
    ),
  },
  {
    path: "/sessions/:sessionId",
    element: (
      <RequireAuth>
        <SessionPage />
      </RequireAuth>
    ),
  },
  {
    path: "/sessions/:sessionId/report",
    element: (
      <RequireAuth>
        <ReportPage />
      </RequireAuth>
    ),
  },
  {
    path: "/settings",
    element: (
      <RequireAuth>
        <SettingsPage />
      </RequireAuth>
    ),
  },
  {
    path: "/progress",
    element: (
      <RequireAuth>
        <ProgressPage />
      </RequireAuth>
    ),
  },
]);
