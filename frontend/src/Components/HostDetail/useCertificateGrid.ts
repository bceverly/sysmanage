// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Certificates DataGrid concerns for the Host Detail page: filter/search state,
// column-visibility preferences, dynamic page sizing and pagination model.

import { useEffect, useMemo, useState } from 'react';
import { useColumnVisibility } from '../../hooks/useColumnVisibility';
import { useTablePageSize } from '../../hooks/useTablePageSize';

export const useCertificateGrid = () => {
    const [certificateFilter, setCertificateFilter] = useState<'all' | 'ca' | 'server' | 'client'>('server');
    const [certificatePaginationModel, setCertificatePaginationModel] = useState({ page: 0, pageSize: 10 });
    const [certificateSearchTerm, setCertificateSearchTerm] = useState<string>('');

    // Column visibility preferences for Certificates grid
    const {
        hiddenColumns: hiddenCertificatesColumns,
        setHiddenColumns: setHiddenCertificatesColumns,
        resetPreferences: resetCertificatesPreferences,
        getColumnVisibilityModel: getCertificatesColumnVisibilityModel,
    } = useColumnVisibility('hostdetail-certificates-grid');

    // Dynamic table page sizing based on window height
    const { pageSize, pageSizeOptions } = useTablePageSize({
        reservedHeight: 300,
        minRows: 5,
        maxRows: 100,
    });

    // Update pagination when pageSize from hook changes
    useEffect(() => {
        setCertificatePaginationModel(prev => ({ ...prev, pageSize }));
    }, [pageSize]);

    // Ensure current page size is always in options to avoid MUI warning
    const safePageSizeOptions = useMemo(() => {
        const currentPageSize = certificatePaginationModel.pageSize;
        if (!pageSizeOptions.includes(currentPageSize)) {
            const combinedOptions = [...pageSizeOptions, currentPageSize];
            combinedOptions.sort((a, b) => a - b);
            return combinedOptions;
        }
        return pageSizeOptions;
    }, [pageSizeOptions, certificatePaginationModel.pageSize]);

    return {
        certificateFilter,
        setCertificateFilter,
        certificatePaginationModel,
        setCertificatePaginationModel,
        certificateSearchTerm,
        setCertificateSearchTerm,
        hiddenCertificatesColumns,
        setHiddenCertificatesColumns,
        resetCertificatesPreferences,
        getCertificatesColumnVisibilityModel,
        safePageSizeOptions,
    };
};
