/* Purchase Orders API */
import apiClient from "./client";
import type { PurchaseOrder, PaginatedResponse } from "../types";

export const purchaseOrdersApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    sort_by?: string;
    sort_order?: string;
    status?: string;
    vendor_id?: number;
  }): Promise<PaginatedResponse<PurchaseOrder>> => {
    const response = await apiClient.get("/purchase-orders/", { params });
    return response.data;
  },

  get: async (id: number): Promise<PurchaseOrder> => {
    const response = await apiClient.get(`/purchase-orders/${id}`);
    return response.data;
  },

  create: async (data: Partial<PurchaseOrder>): Promise<PurchaseOrder> => {
    const response = await apiClient.post("/purchase-orders/", data);
    return response.data;
  },

  update: async (
    id: number,
    data: Partial<PurchaseOrder>
  ): Promise<PurchaseOrder> => {
    const response = await apiClient.put(`/purchase-orders/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/purchase-orders/${id}`);
  },
};
