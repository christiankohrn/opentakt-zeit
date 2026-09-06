import type { ReactNode } from "react";
import { Navigate, Outlet, RouterProvider, createBrowserRouter } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import Layout from "./components/Layout";
import HrCalendar from "./pages/HrCalendar";
import HrDay from "./pages/HrDay";
import HrModels from "./pages/HrModels";
import HrPlausibility from "./pages/HrPlausibility";
import HrUserMonth from "./pages/HrUserMonth";
import HrUsers from "./pages/HrUsers";
import Account from "./pages/Account";
import ForgotPassword from "./pages/ForgotPassword";
import Login from "./pages/Login";
import SetPassword from "./pages/SetPassword";
import Settings from "./pages/Settings";
import Stamp from "./pages/Stamp";
import Times from "./pages/Times";
import { ThemeProvider } from "./theme";

function Guard({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) {
    return <div className="p-8 text-muted">Laden …</div>;
  }
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function HrGuard() {
  const { user } = useAuth();
  if (!user || !["hr", "admin", "supervisor"].includes(user.role)) {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}

function AdminGuard() {
  const { user } = useAuth();
  if (!user || user.role !== "admin") {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}

function AppShell() {
  return (
    <Guard>
      <Layout />
    </Guard>
  );
}

const router = createBrowserRouter([
  { path: "/login", element: <Login /> },
  { path: "/passwort-vergessen", element: <ForgotPassword /> },
  { path: "/passwort-setzen", element: <SetPassword /> },
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Stamp /> },
      { path: "zeiten", element: <Times /> },
      { path: "konto", element: <Account /> },
      {
        element: <HrGuard />,
        children: [
          { path: "pruefung", element: <HrPlausibility /> },
          { path: "personal", element: <HrUsers /> },
          { path: "personal/:id", element: <HrUserMonth /> },
          { path: "personal/:id/tag/:date", element: <HrDay /> },
          { path: "modelle", element: <HrModels /> },
          { path: "feiertage", element: <HrCalendar /> },
        ],
      },
      {
        element: <AdminGuard />,
        children: [{ path: "einstellungen", element: <Settings /> }],
      },
    ],
  },
]);

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </ThemeProvider>
  );
}
