import axiosInstance from './api.js';

export interface ReportBranding {
  company_name: string | null;
  header_text: string | null;
  has_logo: boolean;
  logo_mime_type: string | null;
  updated_at: string | null;
}

export interface ReportBrandingUpdate {
  company_name?: string | null;
  header_text?: string | null;
}

export const reportBrandingService = {
  async get(): Promise<ReportBranding> {
    const r = await axiosInstance.get('/api/report-branding');
    return r.data;
  },

  async update(payload: ReportBrandingUpdate): Promise<ReportBranding> {
    const r = await axiosInstance.put('/api/report-branding', payload);
    return r.data;
  },

  async uploadLogo(file: globalThis.File): Promise<ReportBranding> {
    const form = new FormData();
    form.append('file', file);
    const r = await axiosInstance.post('/api/report-branding/logo', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return r.data;
  },

  async deleteLogo(): Promise<ReportBranding> {
    const r = await axiosInstance.delete('/api/report-branding/logo');
    return r.data;
  },

  // Fetch the logo bytes through axios so the request carries the
  // bearer token, then mint an object URL the <img> tag can render.
  // Caller must revoke the URL when done (handled by the React
  // component's effect-cleanup hook).
  async fetchLogoObjectUrl(): Promise<string | null> {
    try {
      const r = await axiosInstance.get('/api/report-branding/logo', {
        responseType: 'blob',
      });
      return globalThis.URL.createObjectURL(r.data as Blob);
    } catch {
      return null;
    }
  },
};
