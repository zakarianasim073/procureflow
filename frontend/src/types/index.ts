/* TypeScript type definitions */

export interface User {
  id: number;
  email: string;
  username: string;
  full_name: string;
  role: UserRole;
  status: UserStatus;
  department?: string;
  phone?: string;
  is_superuser: boolean;
  created_at: string;
  updated_at: string;
  last_login_at?: string;
}

export enum UserRole {
  ADMIN = "admin",
  MANAGER = "manager",
  BUYER = "buyer",
  APPROVER = "approver",
  VIEWER = "viewer",
}

export enum UserStatus {
  ACTIVE = "active",
  INACTIVE = "inactive",
  PENDING = "pending",
  SUSPENDED = "suspended",
}

export interface Vendor {
  id: number;
  code: string;
  name: string;
  legal_name?: string;
  status: VendorStatus;
  tier: VendorTier;
  contact_person?: string;
  email?: string;
  phone?: string;
  city?: string;
  state?: string;
  country?: string;
  payment_terms?: string;
  currency: string;
  overall_rating?: number;
  iso_certified: boolean;
  credit_limit?: number;
  notes?: string;
  created_at: string;
  updated_at: string;
}

export enum VendorStatus {
  ACTIVE = "active",
  INACTIVE = "inactive",
  PENDING_VERIFICATION = "pending_verification",
  BLACKLISTED = "blacklisted",
  ON_HOLD = "on_hold",
}

export enum VendorTier {
  TIER_1 = "tier_1",
  TIER_2 = "tier_2",
  TIER_3 = "tier_3",
  TIER_4 = "tier_4",
}

export interface PurchaseRequest {
  id: number;
  pr_number: string;
  title: string;
  description?: string;
  status: PRStatus;
  requester_id: number;
  department?: string;
  cost_center?: string;
  estimated_total?: number;
  currency: string;
  required_date?: string;
  priority: string;
  justification?: string;
  notes?: string;
  items: PurchaseRequestItem[];
  created_at: string;
  updated_at: string;
  submitted_at?: string;
}

export enum PRStatus {
  DRAFT = "draft",
  PENDING_APPROVAL = "pending_approval",
  APPROVED = "approved",
  REJECTED = "rejected",
  CANCELLED = "cancelled",
  CONVERTED_TO_ORDER = "converted_to_order",
}

export interface PurchaseRequestItem {
  id: number;
  line_number: number;
  item_code?: string;
  item_name: string;
  description?: string;
  category?: string;
  quantity: number;
  unit_of_measure: string;
  estimated_unit_price?: number;
  estimated_total_price?: number;
  specification_url?: string;
  notes?: string;
}

export interface PurchaseOrder {
  id: number;
  po_number: string;
  title: string;
  status: POStatus;
  vendor_id: number;
  purchase_request_id?: number;
  payment_terms?: string;
  delivery_terms?: string;
  subtotal: number;
  tax_amount: number;
  shipping_cost: number;
  total_amount: number;
  currency: string;
  order_date?: string;
  expected_delivery_date?: string;
  notes?: string;
  items: PurchaseOrderItem[];
  created_at: string;
  updated_at: string;
}

export enum POStatus {
  DRAFT = "draft",
  PENDING_APPROVAL = "pending_approval",
  APPROVED = "approved",
  SENT_TO_VENDOR = "sent_to_vendor",
  ACKNOWLEDGED = "acknowledged",
  PARTIALLY_RECEIVED = "partially_received",
  FULLY_RECEIVED = "fully_received",
  CLOSED = "closed",
  CANCELLED = "cancelled",
}

export interface PurchaseOrderItem {
  id: number;
  line_number: number;
  item_code?: string;
  item_name: string;
  description?: string;
  category?: string;
  quantity_ordered: number;
  quantity_received: number;
  unit_of_measure: string;
  unit_price: number;
  total_price: number;
  notes?: string;
}

export interface Approval {
  id: number;
  status: ApprovalStatus;
  entity_type: ApprovalEntityType;
  entity_id: number;
  approver_id: number;
  step_name: string;
  step_order: number;
  is_final_step: boolean;
  comments?: string;
  decided_at?: string;
  due_date?: string;
  created_at: string;
  updated_at: string;
}

export enum ApprovalStatus {
  PENDING = "pending",
  APPROVED = "approved",
  REJECTED = "rejected",
  CANCELLED = "cancelled",
}

export enum ApprovalEntityType {
  PURCHASE_REQUEST = "purchase_request",
  PURCHASE_ORDER = "purchase_order",
  CONTRACT = "contract",
  VENDOR = "vendor",
}

export interface Contract {
  id: number;
  contract_number: string;
  title: string;
  description?: string;
  contract_type: string;
  status: ContractStatus;
  vendor_id: number;
  contract_value?: number;
  currency: string;
  start_date?: string;
  end_date?: string;
  signed_date?: string;
  payment_terms?: string;
  notes?: string;
  auto_renew: boolean;
  created_at: string;
  updated_at: string;
}

export enum ContractStatus {
  DRAFT = "draft",
  PENDING_APPROVAL = "pending_approval",
  ACTIVE = "active",
  EXPIRED = "expired",
  TERMINATED = "terminated",
  CANCELLED = "cancelled",
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface ApiError {
  detail: string;
  error_code?: string;
  errors?: unknown;
}

export interface DashboardStats {
  total_purchase_requests: number;
  pending_approvals: number;
  active_orders: number;
  total_vendors: number;
  monthly_spend: number;
  pending_pr_count: number;
}
