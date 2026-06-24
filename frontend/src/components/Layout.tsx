import { Outlet, NavLink, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  ShoppingCart,
  FileText,
  Building2,
  CheckSquare,
  FileSignature,
  Receipt,
  CreditCard,
  LogOut,
  User,
} from "lucide-react";
import { useAppStore } from "../store/appStore";

const navItems = [
  { to: "/admin/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/admin/purchase-requests", icon: ShoppingCart, label: "Purchase Requests" },
  { to: "/admin/purchase-orders", icon: FileText, label: "Purchase Orders" },
  { to: "/admin/vendors", icon: Building2, label: "Vendors" },
  { to: "/admin/approvals", icon: CheckSquare, label: "Approvals" },
  { to: "/admin/contracts", icon: FileSignature, label: "Contracts" },
  { to: "/admin/running-bills", icon: Receipt, label: "Running Bills" },
  { to: "/admin/letters-of-credit", icon: CreditCard, label: "Letters of Credit" },
];

export default function Layout() {
  const navigate = useNavigate();
  const { auth, logout } = useAppStore();

  const handleLogout = () => {
    logout();
    navigate("/settings");
  };

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <ShoppingCart size={24} />
          <div className="brand-stack" style={{ gap: "0.15rem" }}>
            <span>ProcureFlow</span>
            <span style={{ fontSize: "0.75rem", color: "var(--gray-400)", letterSpacing: "0.08em" }}>@zmnasim73</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/admin/dashboard"}
              className={({ isActive }) =>
                `sidebar-link ${isActive ? "active" : ""}`
              }
            >
              <item.icon size={18} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div style={{ marginTop: "auto", paddingTop: "1rem" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.75rem",
              color: "var(--gray-400)",
              fontSize: "0.875rem",
              borderTop: "1px solid rgba(255,255,255,0.1)",
            }}
          >
            <User size={16} />
            <div style={{ flex: 1 }}>
              <div style={{ color: "white", fontWeight: 500 }}>
                {auth.user?.name || "Guest"}
              </div>
              <div style={{ fontSize: "0.75rem" }}>{auth.user?.plan || "free"}</div>
            </div>
          </div>

          <button
            onClick={handleLogout}
            className="sidebar-link"
            style={{ width: "100%", border: "none", background: "none", cursor: "pointer" }}
          >
            <LogOut size={18} />
            Sign Out
          </button>
        </div>
      </aside>

      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
