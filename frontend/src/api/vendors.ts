/* Vendors API */
import apiClient from "./client";
import type { Vendor, PaginatedResponse } from "../types";

export const vendorsApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    sort_by?: string;
    sort_order?: string;
    status?: string;
    search?: string;
  }): Promise<PaginatedResponse<Vendor>> => {
    const response = await apiClient.get("/vendors/", { params });
    return response.data;
  },

  get: async (id: number): Promise<Vendor> => {
    const response = await apiClient.get(`/vendors/${id}`);
    return response.data;
  },

  create: async (data: Partial<Vendor>): Promise<Vendor> => {
    const response = await apiClient.post("/vendors/", data);
    return response.data;
  },

  update: async (id: number, data: Partial<Vendor>): Promise<Vendor> => {
    const response = await apiClient.put(`/vendors/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/vendors/${id}`);
  },
};
