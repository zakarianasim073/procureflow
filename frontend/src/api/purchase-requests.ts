/* Purchase Requests API */
import apiClient from "./client";
import type { PurchaseRequest, PaginatedResponse } from "../types";

export const purchaseRequestsApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    sort_by?: string;
    sort_order?: string;
    status?: string;
  }): Promise<PaginatedResponse<PurchaseRequest>> => {
    const response = await apiClient.get("/purchase-requests/", { params });
    return response.data;
  },

  get: async (id: number): Promise<PurchaseRequest> => {
    const response = await apiClient.get(`/purchase-requests/${id}`);
    return response.data;
  },

  create: async (data: Partial<PurchaseRequest>): Promise<PurchaseRequest> => {
    const response = await apiClient.post("/purchase-requests/", data);
    return response.data;
  },

  update: async (
    id: number,
    data: Partial<PurchaseRequest>
  ): Promise<PurchaseRequest> => {
    const response = await apiClient.put(`/purchase-requests/${id}`, data);
    return response.data;
  },

  submit: async (id: number): Promise<PurchaseRequest> => {
    const response = await apiClient.post(`/purchase-requests/${id}/submit`);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/purchase-requests/${id}`);
  },
};
