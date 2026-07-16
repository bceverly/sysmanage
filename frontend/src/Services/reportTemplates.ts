// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import axiosInstance from './api.js';

export interface ReportTemplate {
  id: string;
  name: string;
  description: string | null;
  base_report_type: string;
  selected_fields: string[];
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface ReportTemplateCreate {
  name: string;
  description?: string | null;
  base_report_type: string;
  selected_fields: string[];
  enabled?: boolean;
}

export type ReportTemplateUpdate = Partial<ReportTemplateCreate>;

export interface ReportTemplateField {
  code: string;
  label: string;
}

export const reportTemplatesService = {
  async list(): Promise<ReportTemplate[]> {
    const r = await axiosInstance.get('/api/v1/report-templates');
    return r.data;
  },

  async get(id: string): Promise<ReportTemplate> {
    const r = await axiosInstance.get(`/api/v1/report-templates/${id}`);
    return r.data;
  },

  async create(payload: ReportTemplateCreate): Promise<ReportTemplate> {
    const r = await axiosInstance.post('/api/v1/report-templates', payload);
    return r.data;
  },

  async update(id: string, payload: ReportTemplateUpdate): Promise<ReportTemplate> {
    const r = await axiosInstance.put(`/api/v1/report-templates/${id}`, payload);
    return r.data;
  },

  async remove(id: string): Promise<void> {
    await axiosInstance.delete(`/api/v1/report-templates/${id}`);
  },

  async fieldsFor(baseType: string): Promise<{ base_report_type: string; fields: ReportTemplateField[] }> {
    const r = await axiosInstance.get(`/api/v1/report-templates/fields/${baseType}`);
    return r.data;
  },

  async baseTypes(): Promise<string[]> {
    const r = await axiosInstance.get('/api/v1/report-templates/base-types');
    return r.data.base_types;
  },
};
