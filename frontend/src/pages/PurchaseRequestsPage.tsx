import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import { purchaseRequestsApi } from "../api/purchase-requests";
import DataTable from "../components/DataTable";
import StatusBadge from "../components/StatusBadge";
import Pagination from "../components/Pagination";
import LoadingSpinner from "../components/LoadingSpinner";
import Modal from "../components/Modal";
import type { PurchaseRequest } from "../types";

export default function PurchaseRequestsPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [showCreateModal, setShowCreateModal] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["purchase-requests", page, statusFilter],
    queryFn: () =>
      purchaseRequestsApi.list({
        page,
        page_size: pageSize,
        status: statusFilter || undefined,
      }),
  });

  const submitMutation = useMutation({
    mutationFn: (id: number) => purchaseRequestsApi.submit(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["purchase-requests"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => purchaseRequestsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["purchase-requests"] });
    },
  });

  const columns = [
    {
      key: "pr_number",
      header: "PR #",
      render: (pr: PurchaseRequest) => (
        <span style={{ fontWeight: 500 }}>{pr.pr_number}</span>
      ),
    },
    { key: "title", header: "Title" },
    {
      key: "status",
      header: "Status",
      render: (pr: PurchaseRequest) => <StatusBadge status={pr.status} />,
    },
    {
      key: "estimated_total",
      header: "Amount",
      render: (pr: PurchaseRequest) =>
        pr.estimated_total
          ? `${pr.currency} ${pr.estimated_total.toLocaleString()}`
          : "-",
    },
    {
      key: "priority",
      header: "Priority",
      render: (pr: PurchaseRequest) => (
        <span
          style={{
            textTransform: "capitalize",
            color:
              pr.priority === "high"
                ? "var(--danger)"
                : pr.priority === "normal"
                ? "var(--gray-600)"
                : "var(--gray-500)",
          }}
        >
          {pr.priority}
        </span>
      ),
    },
    {
      key: "created_at",
      header: "Created",
      render: (pr: PurchaseRequest) =>
        new Date(pr.created_at).toLocaleDateString(),
    },
    {
      key: "actions",
      header: "Actions",
      render: (pr: PurchaseRequest) => (
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {pr.status === "draft" && (
            <>
              <button
                className="btn btn-primary btn-sm"
                onClick={(e) => {
                  e.stopPropagation();
                  submitMutation.mutate(pr.id);
                }}
              >
                Submit
              </button>
              <button
                className="btn btn-danger btn-sm"
                onClick={(e) => {
                  e.stopPropagation();
                  if (confirm("Delete this purchase request?")) {
                    deleteMutation.mutate(pr.id);
                  }
                }}
              >
                Delete
              </button>
            </>
          )}
        </div>
      ),
    },
  ];

  if (isLoading) return <LoadingSpinner />;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Purchase Requests</h1>
        <button
          className="btn btn-primary"
          onClick={() => setShowCreateModal(true)}
        >
          <Plus size={18} />
          New Request
        </button>
      </div>

      {/* Filters */}
      <div
        style={{
          display: "flex",
          gap: "1rem",
          marginBottom: "1rem",
          alignItems: "flex-end",
        }}
      >
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label">Status Filter</label>
          <select
            className="form-select"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
          >
            <option value="">All Statuses</option>
            <option value="draft">Draft</option>
            <option value="pending_approval">Pending Approval</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>
      </div>

      <DataTable
        columns={columns}
        data={data?.items ?? []}
        keyExtractor={(pr) => pr.id}
        emptyMessage="No purchase requests found"
      />

      {data && (
        <Pagination
          page={page}
          totalPages={data.total_pages}
          total={data.total}
          pageSize={pageSize}
          onPageChange={setPage}
        />
      )}

      {/* Create Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="New Purchase Request"
      >
        <p className="text-gray-500 text-sm">
          Use the API to create purchase requests. This form is a placeholder for
          the full implementation.
        </p>
        <div style={{ marginTop: "1rem" }}>
          <button
            className="btn btn-secondary w-full"
            onClick={() => setShowCreateModal(false)}
          >
            Close
          </button>
        </div>
      </Modal>
    </div>
  );
}
