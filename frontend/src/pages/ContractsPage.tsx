import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { contractsApi } from "../api/contracts";
import DataTable from "../components/DataTable";
import StatusBadge from "../components/StatusBadge";
import Pagination from "../components/Pagination";
import LoadingSpinner from "../components/LoadingSpinner";
import type { Contract } from "../types";

export default function ContractsPage() {
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);

  const { data, isLoading } = useQuery({
    queryKey: ["contracts", page],
    queryFn: () => contractsApi.list({ page, page_size: pageSize }),
  });

  const columns = [
    {
      key: "contract_number",
      header: "Contract #",
      render: (c: Contract) => (
        <span style={{ fontWeight: 500, color: "var(--primary)" }}>
          {c.contract_number}
        </span>
      ),
    },
    { key: "title", header: "Title" },
    {
      key: "contract_type",
      header: "Type",
      render: (c: Contract) => (
        <span style={{ textTransform: "capitalize" }}>
          {c.contract_type.replace(/_/g, " ")}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (c: Contract) => <StatusBadge status={c.status} />,
    },
    {
      key: "contract_value",
      header: "Value",
      render: (c: Contract) =>
        c.contract_value
          ? `${c.currency} ${c.contract_value.toLocaleString()}`
          : "-",
    },
    {
      key: "start_date",
      header: "Start",
      render: (c: Contract) =>
        c.start_date ? new Date(c.start_date).toLocaleDateString() : "-",
    },
    {
      key: "end_date",
      header: "End",
      render: (c: Contract) =>
        c.end_date ? new Date(c.end_date).toLocaleDateString() : "-",
    },
  ];

  if (isLoading) return <LoadingSpinner />;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Contracts</h1>
      </div>

      <DataTable
        columns={columns}
        data={data?.items ?? []}
        keyExtractor={(c) => c.id}
        emptyMessage="No contracts found"
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
