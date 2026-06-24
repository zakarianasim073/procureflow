import { useQuery } from "@tanstack/react-query";
import {
  ShoppingCart,
  CheckSquare,
  Building2,
  DollarSign,
  TrendingUp,
  AlertTriangle,
} from "lucide-react";
import { purchaseRequestsApi } from "../api/purchase-requests";
import { vendorsApi } from "../api/vendors";
import { approvalsApi } from "../api/approvals";
import LoadingSpinner from "../components/LoadingSpinner";
import StatusBadge from "../components/StatusBadge";
import { useNavigate } from "react-router-dom";

export default function DashboardPage() {
  const navigate = useNavigate();

  const { data: prData, isLoading: prLoading } = useQuery({
    queryKey: ["dashboard-purchase-requests"],
    queryFn: () => purchaseRequestsApi.list({ page_size: 5 }),
  });

  const { data: pendingApprovals, isLoading: approvalsLoading } = useQuery({
    queryKey: ["dashboard-pending-approvals"],
    queryFn: () => approvalsApi.getMyPending({ page_size: 5 }),
  });

  const { data: vendorData } = useQuery({
    queryKey: ["dashboard-vendors"],
    queryFn: () => vendorsApi.list({ page_size: 1 }),
  });

  const stats = {
    totalPRs: prData?.total ?? 0,
    pendingApprovals: pendingApprovals?.total ?? 0,
    totalVendors: vendorData?.total ?? 0,
    pendingPRs:
      prData?.items?.filter((pr) => pr.status === "pending_approval").length ??
      0,
  };

  if (prLoading || approvalsLoading) {
    return <LoadingSpinner />;
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Dashboard</h1>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-4" style={{ marginBottom: "2rem" }}>
        <div className="stat-card">
          <div className="stat-card-icon" style={{ background: "var(--primary-light)" }}>
            <ShoppingCart size={20} color="var(--primary)" />
          </div>
          <div className="stat-card-value">{stats.totalPRs}</div>
          <div className="stat-card-label">Purchase Requests</div>
        </div>

        <div
          className="stat-card"
          style={{ cursor: "pointer" }}
          onClick={() => navigate("/approvals")}
        >
          <div className="stat-card-icon" style={{ background: "#fef3c7" }}>
            <CheckSquare size={20} color="var(--warning)" />
          </div>
          <div className="stat-card-value">{stats.pendingApprovals}</div>
          <div className="stat-card-label">Pending Approvals</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-icon" style={{ background: "#dcfce7" }}>
            <Building2 size={20} color="var(--success)" />
          </div>
          <div className="stat-card-value">{stats.totalVendors}</div>
          <div className="stat-card-label">Active Vendors</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-icon" style={{ background: "#ede9fe" }}>
            <TrendingUp size={20} color="#7c3aed" />
          </div>
          <div className="stat-card-value">{stats.pendingPRs}</div>
          <div className="stat-card-label">Pending PRs</div>
        </div>
      </div>

      {/* Recent Purchase Requests */}
      <div className="card" style={{ marginBottom: "1.5rem" }}>
        <div className="card-header">
          <h2 style={{ fontSize: "1.125rem", fontWeight: 600 }}>
            Recent Purchase Requests
          </h2>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => navigate("/purchase-requests")}
          >
            View All
          </button>
        </div>

        <div className="table-container" style={{ border: "none" }}>
          <table>
            <thead>
              <tr>
                <th>PR #</th>
                <th>Title</th>
                <th>Status</th>
                <th>Amount</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {prData?.items?.map((pr) => (
                <tr
                  key={pr.id}
                  style={{ cursor: "pointer" }}
                  onClick={() => navigate("/purchase-requests")}
                >
                  <td style={{ fontWeight: 500 }}>{pr.pr_number}</td>
                  <td>{pr.title}</td>
                  <td>
                    <StatusBadge status={pr.status} />
                  </td>
                  <td>
                    {pr.estimated_total
                      ? `${pr.currency} ${pr.estimated_total.toLocaleString()}`
                      : "-"}
                  </td>
                  <td className="text-sm text-gray-500">
                    {new Date(pr.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
              {(!prData?.items || prData.items.length === 0) && (
                <tr>
                  <td colSpan={5} className="text-center text-gray-500">
                    No purchase requests yet
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pending Approvals */}
      <div className="card">
        <div className="card-header">
          <h2 style={{ fontSize: "1.125rem", fontWeight: 600 }}>
            My Pending Approvals
          </h2>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => navigate("/approvals")}
          >
            View All
          </button>
        </div>

        <div className="table-container" style={{ border: "none" }}>
          <table>
            <thead>
              <tr>
                <th>Type</th>
                <th>Step</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {pendingApprovals?.items?.map((approval) => (
                <tr
                  key={approval.id}
                  style={{ cursor: "pointer" }}
                  onClick={() => navigate("/approvals")}
                >
                  <td>{approval.entity_type.replace(/_/g, " ")}</td>
                  <td>{approval.step_name}</td>
                  <td>
                    <StatusBadge status={approval.status} />
                  </td>
                  <td className="text-sm text-gray-500">
                    {new Date(approval.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
              {(!pendingApprovals?.items || pendingApprovals.items.length === 0) && (
                <tr>
                  <td colSpan={4} className="text-center text-gray-500">
                    No pending approvals
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
