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
    const r = await axiosInstance.get('/api/report-templates');
    return r.data;
  },

  async get(id: string): Promise<ReportTemplate> {
    const r = await axiosInstance.get(`/api/report-templates/${id}`);
    return r.data;
  },

  async create(payload: ReportTemplateCreate): Promise<ReportTemplate> {
    const r = await axiosInstance.post('/api/report-templates', payload);
    return r.data;
  },

  async update(id: string, payload: ReportTemplateUpdate): Promise<ReportTemplate> {
    const r = await axiosInstance.put(`/api/report-templates/${id}`, payload);
    return r.data;
  },

  async remove(id: string): Promise<void> {
    await axiosInstance.delete(`/api/report-templates/${id}`);
  },

  async fieldsFor(baseType: string): Promise<{ base_report_type: string; fields: ReportTemplateField[] }> {
    const r = await axiosInstance.get(`/api/report-templates/fields/${baseType}`);
    return r.data;
  },

  async baseTypes(): Promise<string[]> {
    const r = await axiosInstance.get('/api/report-templates/base-types');
    return r.data.base_types;
  },
};
