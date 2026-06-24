import clsx from "clsx";

interface StatusBadgeProps {
  status: string;
  size?: "sm" | "md";
}

const statusStyles: Record<string, string> = {
  draft: "badge-gray",
  pending_approval: "badge-warning",
  pending: "badge-warning",
  approved: "badge-success",
  rejected: "badge-danger",
  cancelled: "badge-danger",
  active: "badge-success",
  inactive: "badge-gray",
  closed: "badge-gray",
  completed: "badge-success",
};

function formatStatus(status: string): string {
  return status
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function StatusBadge({ status, size = "sm" }: StatusBadgeProps) {
  const style = statusStyles[status] || "badge-gray";

  return (
    <span className={clsx("badge", style, size === "sm" && "text-xs")}>
      {formatStatus(status)}
    </span>
  );
}
