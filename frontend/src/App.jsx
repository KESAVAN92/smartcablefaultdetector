import { NavLink, Route, Routes, Navigate } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Module1 from "./modules/Module1";
import Module2 from "./modules/Module2";
import Module3 from "./modules/Module3";
import Module4 from "./modules/Module4";
import Login from "./pages/Login";
import { AuthProvider, AuthContext } from "./auth";
import Notifications from "./components/Notifications";
import MLAnalytics from "./pages/MLAnalytics";

const links = [
  { to: "/", label: "Overview" },
  { to: "/module-1", label: "Module 1" },
  { to: "/module-2", label: "Module 2" },
  { to: "/module-3", label: "Module 3" },
  { to: "/module-4", label: "Module 4" },
  { to: "/ml-analytics", label: "ML Analytics" },
];

import { useContext } from "react";

function RequireAuth({ children }) {
  const { token } = useContext(AuthContext);
  if (!token) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <div className="app-shell">
        <aside className="sidebar">
          <p className="eyebrow">Cable Fault Detector</p>
          <h1>Monitoring Workspace</h1>
          <p className="sidebar-copy">
            A starter React frontend with four modules ready for features,
            charts, and API integration.
          </p>
          <nav className="nav-links">
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                className={({ isActive }) =>
                  isActive ? "nav-link active" : "nav-link"
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
        </aside>

        <main className="content">
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<Dashboard />} />
            <Route path="/module-1" element={<Module1 />} />
            <Route path="/module-2" element={<Module2 />} />
            <Route path="/module-3" element={<Module3 />} />
            <Route path="/ml-analytics" element={<MLAnalytics />} />
            <Route
              path="/module-4"
              element={
                <RequireAuth>
                  <Module4 />
                </RequireAuth>
              }
            />
          </Routes>
        </main>
        <Notifications />
      </div>
    </AuthProvider>
  );
}
