import { useState, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ShoppingCart, AlertCircle } from "lucide-react";
import { useAppStore } from "../store/appStore";

export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAppStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const ok = await login(email, password);
      if (!ok) {
        setError("Login failed. Please check your credentials.");
        return;
      }
      navigate("/");
    } catch (err: any) {
      setError(err.response?.data?.detail || "Login failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <div style={{ textAlign: "center", marginBottom: "2rem" }}>
          <div
            style={{
              width: "3.5rem",
              height: "3.5rem",
              background: "linear-gradient(135deg, #2563eb, #14b8a6)",
              borderRadius: "1rem",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 1rem",
              boxShadow: "0 14px 32px rgba(37,99,235,0.25)",
            }}
          >
            <ShoppingCart size={26} color="white" />
          </div>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 800, marginBottom: "0.25rem", letterSpacing: "-0.03em" }}>
            ProcureFlow
          </h1>
          <div className="brand-handle" style={{ margin: "0 auto 0.5rem" }}>
            @zmnasim73
          </div>
          <p style={{ color: "var(--gray-500)", fontSize: "0.875rem" }}>
            a Procurement intelligence System owner access
          </p>
        </div>

        {error && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.75rem",
              background: "#fee2e2",
              color: "#991b1b",
              borderRadius: "0.375rem",
              fontSize: "0.875rem",
              marginBottom: "1rem",
            }}
          >
            <AlertCircle size={16} />
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Email</label>
            <input
              type="email"
              className="form-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="owner@example.com"
              required
              autoFocus
            />
          </div>

          <div className="form-group">
            <label className="form-label">Password</label>
            <input
              type="password"
              className="form-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              required
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary w-full"
            style={{ marginTop: "0.5rem" }}
            disabled={loading}
          >
            {loading ? (
              <div className="spinner" style={{ width: "1rem", height: "1rem", borderColor: "rgba(255,255,255,0.3)", borderTopColor: "white" }} />
            ) : (
              "Enter Owner Dashboard"
            )}
          </button>
        </form>

        <p
          style={{
            marginTop: "1.5rem",
            textAlign: "center",
            fontSize: "0.75rem",
            color: "var(--gray-400)",
          }}
        >
          Contact your administrator to get access
        </p>
      </div>
    </div>
  );
}
