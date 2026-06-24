/* Approvals API */
import apiClient from "./client";
import type { Approval, PaginatedResponse } from "../types";

export const approvalsApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    status?: string;
    entity_type?: string;
  }): Promise<PaginatedResponse<Approval>> => {
    const response = await apiClient.get("/approvals/", { params });
    return response.data;
  },

  getMyPending: async (params?: {
    page?: number;
    page_size?: number;
  }): Promise<PaginatedResponse<Approval>> => {
    const response = await apiClient.get("/approvals/my-pending", { params });
    return response.data;
  },

  decide: async (
    id: number,
    decision: "approved" | "rejected",
    comments?: string
  ): Promise<Approval> => {
    const response = await apiClient.post(`/approvals/${id}/decide`, {
      decision,
      comments,
    });
    return response.data;
  },
};
