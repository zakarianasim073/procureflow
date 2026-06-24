import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { vendorsApi } from "../api/vendors";
import DataTable from "../components/DataTable";
import StatusBadge from "../components/StatusBadge";
import Pagination from "../components/Pagination";
import LoadingSpinner from "../components/LoadingSpinner";
import Modal from "../components/Modal";
import type { Vendor } from "../types";

export default function VendorsPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [formData, setFormData] = useState({
    code: "",
    name: "",
    email: "",
    phone: "",
    city: "",
    country: "",
    payment_terms: "Net 30",
  });

  const { data, isLoading } = useQuery({
    queryKey: ["vendors", page],
    queryFn: () => vendorsApi.list({ page, page_size: pageSize }),
  });

  const createMutation = useMutation({
    mutationFn: () => vendorsApi.create(formData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vendors"] });
      setShowCreateModal(false);
      setFormData({ code: "", name: "", email: "", phone: "", city: "", country: "", payment_terms: "Net 30" });
    },
  });

  const columns = [
    {
      key: "code",
      header: "Code",
      render: (v: Vendor) => (
        <span style={{ fontWeight: 500, color: "var(--primary)" }}>{v.code}</span>
      ),
    },
    { key: "name", header: "Name" },
    { key: "email", header: "Email" },
    { key: "phone", header: "Phone" },
    { key: "city", header: "City" },
    { key: "country", header: "Country" },
    {
      key: "status",
      header: "Status",
      render: (v: Vendor) => <StatusBadge status={v.status} />,
    },
    {
      key: "tier",
      header: "Tier",
      render: (v: Vendor) => (
        <span className="badge badge-info">{v.tier?.replace(/_/g, " ").toUpperCase()}</span>
      ),
    },
  ];

  if (isLoading) return <LoadingSpinner />;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Vendors</h1>
        <button
          className="btn btn-primary"
          onClick={() => setShowCreateModal(true)}
        >
          <Plus size={18} />
          Add Vendor
        </button>
      </div>

      <DataTable
        columns={columns}
        data={data?.items ?? []}
        keyExtractor={(v) => v.id}
        emptyMessage="No vendors found"
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

      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Add New Vendor"
      >
        <div>
          <div className="form-group">
            <label className="form-label">Vendor Code *</label>
            <input
              className="form-input"
              value={formData.code}
              onChange={(e) => setFormData({ ...formData, code: e.target.value })}
              placeholder="e.g., V001"
            />
          </div>
          <div className="form-group">
            <label className="form-label">Company Name *</label>
            <input
              className="form-input"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="Company name"
            />
          </div>
          <div className="grid grid-cols-2" style={{ gap: "1rem" }}>
            <div className="form-group">
              <label className="form-label">Email</label>
              <input
                className="form-input"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                placeholder="vendor@example.com"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Phone</label>
              <input
                className="form-input"
                value={formData.phone}
                onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                placeholder="+1234567890"
              />
            </div>
          </div>
          <div className="grid grid-cols-2" style={{ gap: "1rem" }}>
            <div className="form-group">
              <label className="form-label">City</label>
              <input
                className="form-input"
                value={formData.city}
                onChange={(e) => setFormData({ ...formData, city: e.target.value })}
                placeholder="City"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Country</label>
              <input
                className="form-input"
                value={formData.country}
                onChange={(e) => setFormData({ ...formData, country: e.target.value })}
                placeholder="Country"
              />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Payment Terms</label>
            <select
              className="form-select"
              value={formData.payment_terms}
              onChange={(e) => setFormData({ ...formData, payment_terms: e.target.value })}
            >
              <option value="Net 15">Net 15</option>
              <option value="Net 30">Net 30</option>
              <option value="Net 45">Net 45</option>
              <option value="Net 60">Net 60</option>
            </select>
          </div>
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "1.5rem" }}>
            <button
              className="btn btn-primary"
              onClick={() => createMutation.mutate()}
              disabled={!formData.code || !formData.name || createMutation.isPending}
            >
              {createMutation.isPending ? "Creating..." : "Create Vendor"}
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => setShowCreateModal(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
