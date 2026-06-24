import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle, XCircle } from "lucide-react";
import { approvalsApi } from "../api/approvals";
import DataTable from "../components/DataTable";
import StatusBadge from "../components/StatusBadge";
import Pagination from "../components/Pagination";
import LoadingSpinner from "../components/LoadingSpinner";
import Modal from "../components/Modal";
import type { Approval } from "../types";

export default function ApprovalsPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [view, setView] = useState<"my-pending" | "all">("my-pending");
  const [decisionModal, setDecisionModal] = useState<{
    open: boolean;
    approval: Approval | null;
  }>({ open: false, approval: null });
  const [comment, setComment] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["approvals", view, page],
    queryFn: () =>
      view === "my-pending"
        ? approvalsApi.getMyPending({ page, page_size: pageSize })
        : approvalsApi.list({ page, page_size: pageSize }),
  });

  const approveMutation = useMutation({
    mutationFn: ({
      id,
      decision,
      comments,
    }: {
      id: number;
      decision: "approved" | "rejected";
      comments?: string;
    }) => approvalsApi.decide(id, decision, comments),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      setDecisionModal({ open: false, approval: null });
      setComment("");
    },
  });

  const columns = [
    {
      key: "entity_type",
      header: "Type",
      render: (a: Approval) => (
        <span style={{ textTransform: "capitalize" }}>
          {a.entity_type.replace(/_/g, " ")}
        </span>
      ),
    },
    { key: "step_name", header: "Step" },
    {
      key: "status",
      header: "Status",
      render: (a: Approval) => <StatusBadge status={a.status} />,
    },
    {
      key: "created_at",
      header: "Created",
      render: (a: Approval) =>
        new Date(a.created_at).toLocaleDateString(),
    },
    {
      key: "actions",
      header: "Actions",
      render: (a: Approval) => (
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {a.status === "pending" && (
            <>
              <button
                className="btn btn-success btn-sm"
                onClick={(e) => {
                  e.stopPropagation();
                  approveMutation.mutate({ id: a.id, decision: "approved" });
                }}
              >
                <CheckCircle size={14} />
                Approve
              </button>
              <button
                className="btn btn-danger btn-sm"
                onClick={(e) => {
                  e.stopPropagation();
                  setDecisionModal({ open: true, approval: a });
                }}
              >
                <XCircle size={14} />
                Reject
              </button>
            </>
          )}
          {a.status !== "pending" && (
            <span className="text-sm text-gray-500">
              {a.decided_at ? new Date(a.decided_at).toLocaleDateString() : "N/A"}
            </span>
          )}
        </div>
      ),
    },
  ];

  if (isLoading) return <LoadingSpinner />;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Approvals</h1>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button
            className={`btn ${view === "my-pending" ? "btn-primary" : "btn-secondary"} btn-sm`}
            onClick={() => setView("my-pending")}
          >
            My Pending
          </button>
          <button
            className={`btn ${view === "all" ? "btn-primary" : "btn-secondary"} btn-sm`}
            onClick={() => setView("all")}
          >
            All
          </button>
        </div>
      </div>

      <DataTable
        columns={columns}
        data={data?.items ?? []}
        keyExtractor={(a) => a.id}
        emptyMessage="No approvals found"
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

      {/* Rejection Modal */}
      <Modal
        isOpen={decisionModal.open}
        onClose={() => setDecisionModal({ open: false, approval: null })}
        title="Reject Approval"
      >
        <div>
          <div className="form-group">
            <label className="form-label">Reason for rejection</label>
            <textarea
              className="form-input"
              rows={3}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Provide a reason for rejection..."
            />
          </div>
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}>
            <button
              className="btn btn-danger"
              onClick={() => {
                if (decisionModal.approval) {
                  approveMutation.mutate({
                    id: decisionModal.approval.id,
                    decision: "rejected",
                    comments: comment,
                  });
                }
              }}
            >
              Confirm Reject
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => setDecisionModal({ open: false, approval: null })}
            >
              Cancel
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
