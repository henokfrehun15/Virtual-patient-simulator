import type { ReactElement } from "react";
import { Navigate, createBrowserRouter } from "react-router-dom";

import { useAuth } from "../features/auth/AuthContext";
import { CoursePage } from "../pages/CoursePage";
import { CoursesPage } from "../pages/CoursesPage";
import { DashboardPage } from "../pages/DashboardPage";
import { DiseasePage } from "../pages/DiseasePage";
import { LoginPage } from "../pages/LoginPage";
import { RegisterPage } from "../pages/RegisterPage";

function RequireAuth({ children }: { children: ReactElement }) {
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="loading-screen">Loading…</div>;
  }
  if (user === null) {
    return <Navigate to="/login" replace />;
  }
  return children;
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
]);
