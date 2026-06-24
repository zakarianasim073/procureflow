/* Contracts API */
import apiClient from "./client";
import type { Contract, PaginatedResponse } from "../types";

export const contractsApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    sort_by?: string;
    sort_order?: string;
    status?: string;
    vendor_id?: number;
  }): Promise<PaginatedResponse<Contract>> => {
    const response = await apiClient.get("/contracts/", { params });
    return response.data;
  },

  get: async (id: number): Promise<Contract> => {
    const response = await apiClient.get(`/contracts/${id}`);
    return response.data;
  },

  create: async (data: Partial<Contract>): Promise<Contract> => {
    const response = await apiClient.post("/contracts/", data);
    return response.data;
  },

  update: async (id: number, data: Partial<Contract>): Promise<Contract> => {
    const response = await apiClient.put(`/contracts/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/contracts/${id}`);
  },
};
