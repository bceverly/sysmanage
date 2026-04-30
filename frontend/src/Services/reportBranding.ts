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

  // Returns a public URL the <img> tag can use directly (cookie auth) —
  // adds a cache-buster so a freshly-uploaded logo refreshes immediately.
  logoUrl(bust?: string | number): string {
    const q = bust === undefined ? '' : `?t=${encodeURIComponent(String(bust))}`;
    return `/api/report-branding/logo${q}`;
  },
};
