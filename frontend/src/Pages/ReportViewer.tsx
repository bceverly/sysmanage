import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Box,
  Button,
  CircularProgress,
  Alert,
} from '@mui/material';

import {
  ArrowBack as BackIcon,
  GetApp as DownloadIcon,
} from '@mui/icons-material';
import api from '../Services/api';

const ReportViewer: React.FC = () => {
  const { reportId } = useParams<{ reportId: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [htmlContent, setHtmlContent] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timeoutRef = useRef<number | null>(null);

  const fetchReportHtml = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await api.get(`/api/reports/view/${reportId}`, {
        responseType: 'text', // Important: get raw HTML
      });

      setHtmlContent(response.data);
    } catch (error: unknown) {
      console.error('Error fetching report:', error);
      const errorMessage = error && typeof error === 'object' && 'response' in error
        ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail || 'Failed to load report'
        : 'Failed to load report';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  }, [reportId]);

  useEffect(() => {
    if (reportId) {
      fetchReportHtml();
    }
  }, [reportId, fetchReportHtml]);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  const handleGeneratePdf = async () => {
    try {
      const response = await api.get(`/api/reports/generate/${reportId}`, {
        responseType: 'blob', // Important for binary data
      });

      // Create blob and download
      const blob = new Blob([response.data], { type: 'application/pdf' });
      const url = window.URL.createObjectURL(blob);

      // Open in new tab instead of downloading
      window.open(url, '_blank');

      // Clean up the URL object
      timeoutRef.current = setTimeout(() => window.URL.revokeObjectURL(url), 100);

    } catch (error: unknown) {
      console.error('Error generating PDF:', error);
      const errorMessage = error && typeof error === 'object' && 'response' in error
        ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail || 'Unknown error'
        : 'Unknown error';
      alert(`Error generating PDF: ${errorMessage}`);
    }
  };

  const handleGoBack = () => {
    navigate('/reports');
  };

  if (loading) {
    return (
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '400px'
        }}
      >
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Box sx={{ p: 3 }}>
        <Box sx={{ mb: 3, display: 'flex', alignItems: 'center', gap: 2 }}>
          <Button
            variant="outlined"
            startIcon={<BackIcon />}
            onClick={handleGoBack}
          >
            {t('common.back', 'Back')}
          </Button>
        </Box>

        <Alert severity="error">
          {error}
        </Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      {/* Header with Back and PDF buttons */}
      <Box sx={{ mb: 3, display: 'flex', alignItems: 'center', gap: 2, justifyContent: 'space-between' }}>
        <Button
          variant="outlined"
          startIcon={<BackIcon />}
          onClick={handleGoBack}
        >
          {t('common.back', 'Back')}
        </Button>

        <Button
          variant="contained"
          startIcon={<DownloadIcon />}
          onClick={handleGeneratePdf}
        >
          {t('reports.generatePdf', 'Generate PDF')}
        </Button>
      </Box>

      {/* Report Content */}
      <Box
        sx={{
          border: '1px solid #ddd',
          borderRadius: 2,
          overflow: 'hidden',
          backgroundColor: 'white',
          minHeight: '600px'
        }}
      >
        <iframe
          srcDoc={htmlContent}
          style={{
            width: '100%',
            height: '80vh',
            border: 'none',
            minHeight: '600px'
          }}
          title="Report Content"
        />
      </Box>
    </Box>
  );
};

export default ReportViewer;