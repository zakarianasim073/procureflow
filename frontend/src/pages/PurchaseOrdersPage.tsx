import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { purchaseOrdersApi } from "../api/purchase-orders";
import DataTable from "../components/DataTable";
import StatusBadge from "../components/StatusBadge";
import Pagination from "../components/Pagination";
import LoadingSpinner from "../components/LoadingSpinner";
import type { PurchaseOrder } from "../types";

export default function PurchaseOrdersPage() {
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);

  const { data, isLoading } = useQuery({
    queryKey: ["purchase-orders", page],
    queryFn: () => purchaseOrdersApi.list({ page, page_size: pageSize }),
  });

  const columns = [
    {
      key: "po_number",
      header: "PO #",
      render: (po: PurchaseOrder) => (
        <span style={{ fontWeight: 500, color: "var(--primary)" }}>
          {po.po_number}
        </span>
      ),
    },
    { key: "title", header: "Title" },
    {
      key: "status",
      header: "Status",
      render: (po: PurchaseOrder) => <StatusBadge status={po.status} />,
    },
    {
      key: "total_amount",
      header: "Total",
      render: (po: PurchaseOrder) =>
        `${po.currency} ${po.total_amount.toLocaleString()}`,
    },
    {
      key: "expected_delivery_date",
      header: "Delivery",
      render: (po: PurchaseOrder) =>
        po.expected_delivery_date
          ? new Date(po.expected_delivery_date).toLocaleDateString()
          : "-",
    },
    {
      key: "created_at",
      header: "Created",
      render: (po: PurchaseOrder) =>
        new Date(po.created_at).toLocaleDateString(),
    },
  ];

  if (isLoading) return <LoadingSpinner />;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Purchase Orders</h1>
      </div>

      <DataTable
        columns={columns}
        data={data?.items ?? []}
        keyExtractor={(po) => po.id}
        emptyMessage="No purchase orders found"
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
    </div>
  );
}
