import { useNavigate } from "react-router-dom";
import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import VisibilityIcon from '@mui/icons-material/Visibility';
import { Chip, IconButton } from '@mui/material';
import { useTranslation } from 'react-i18next';

import { HostComplianceSummary, getComplianceHosts } from '../Services/license';
import { useTablePageSize } from '../hooks/useTablePageSize';
import { useColumnVisibility } from '../Hooks/useColumnVisibility';
import SearchBox from '../Components/SearchBox';
import ColumnVisibilityButton from '../Components/ColumnVisibilityButton';

const CompliancePage = () => {
    const [tableData, setTableData] = useState<HostComplianceSummary[]>([]);
    const [filteredData, setFilteredData] = useState<HostComplianceSummary[]>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [searchTerm, setSearchTerm] = useState<string>('');
    const [searchColumn, setSearchColumn] = useState<string>('hostname');
    const navigate = useNavigate();
    const { t } = useTranslation();

    // Dynamic table page sizing based on window height
    const { pageSize, pageSizeOptions } = useTablePageSize({
        reservedHeight: 200,
        minRows: 5,
        maxRows: 100,
    });

    // Controlled pagination state
    const [paginationModel, setPaginationModel] = useState({ page: 0, pageSize: 10 });

    // Update pagination when pageSize from hook changes
    useEffect(() => {
        setPaginationModel(prev => ({ ...prev, pageSize }));
    }, [pageSize]);

    // Ensure current page size is always in options
    const safePageSizeOptions = useMemo(() => {
        if (!pageSizeOptions || !Array.isArray(pageSizeOptions)) {
            return [5, 10, 25, 50];
        }

        const currentPageSize = paginationModel?.pageSize || 10;
        if (!pageSizeOptions.includes(currentPageSize)) {
            return [...pageSizeOptions, currentPageSize].sort((a, b) => a - b);
        }
        return pageSizeOptions;
    }, [pageSizeOptions, paginationModel?.pageSize]);

    // Column visibility preferences
    const {
        hiddenColumns,
        setHiddenColumns,
        resetPreferences,
        getColumnVisibilityModel,
    } = useColumnVisibility('compliance-grid');

    // Get compliance grade color
    const getGradeColor = (grade: string): 'error' | 'warning' | 'info' | 'success' | 'default' => {
        switch (grade?.toUpperCase()) {
            case 'A':
            case 'A+':
                return 'success';
            case 'B':
                return 'info';
            case 'C':
                return 'warning';
            case 'D':
            case 'F':
                return 'error';
            default:
                return 'default';
        }
    };

    // Get severity count color
    const getSeverityColor = (count: number, severity: string): 'error' | 'warning' | 'info' | 'default' => {
        if (count === 0) return 'default';
        switch (severity) {
            case 'critical':
                return 'error';
            case 'high':
                return 'error';
            case 'medium':
                return 'warning';
            case 'low':
                return 'info';
            default:
                return 'default';
        }
    };

    // Memoize columns
    const columns: GridColDef[] = useMemo(() => [
        {
            field: 'hostname',
            headerName: t('compliancePage.hostname'),
            width: 250,
            renderCell: (params) => {
                const row = params.row;
                return (
                    <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                        <span>{row.hostname}</span>
                        {row.fqdn && row.fqdn !== row.hostname && (
                            <Typography variant="caption" color="text.secondary">
                                {row.fqdn}
                            </Typography>
                        )}
                    </Box>
                );
            }
        },
        {
            field: 'compliance_score',
            headerName: t('compliancePage.complianceScore'),
            width: 120,
            align: 'center',
            headerAlign: 'center',
        },
        {
            field: 'compliance_grade',
            headerName: t('compliancePage.complianceGrade'),
            width: 100,
            align: 'center',
            headerAlign: 'center',
            renderCell: (params) => (
                <Chip
                    label={params.value}
                    size="small"
                    color={getGradeColor(params.value)}
                />
            )
        },
        {
            field: 'critical_failures',
            headerName: t('compliancePage.critical'),
            width: 100,
            align: 'center',
            headerAlign: 'center',
            renderCell: (params) => (
                <Chip
                    label={params.value}
                    size="small"
                    color={getSeverityColor(params.value, 'critical')}
                    variant={params.value > 0 ? 'filled' : 'outlined'}
                />
            )
        },
        {
            field: 'high_failures',
            headerName: t('compliancePage.high'),
            width: 100,
            align: 'center',
            headerAlign: 'center',
            renderCell: (params) => (
                <Chip
                    label={params.value}
                    size="small"
                    color={getSeverityColor(params.value, 'high')}
                    variant={params.value > 0 ? 'filled' : 'outlined'}
                />
            )
        },
        {
            field: 'last_scanned_at',
            headerName: t('compliancePage.lastScanned'),
            width: 180,
            renderCell: (params) => {
                if (!params.value) {
                    return <Typography variant="body2" color="text.secondary">{t('compliancePage.notScanned')}</Typography>;
                }
                const date = new Date(params.value);
                return (
                    <Box>
                        <Typography variant="body2">{date.toLocaleDateString()}</Typography>
                        <Typography variant="caption" color="text.secondary">{date.toLocaleTimeString()}</Typography>
                    </Box>
                );
            }
        },
        {
            field: 'actions',
            headerName: t('common.actions'),
            width: 100,
            sortable: false,
            filterable: false,
            renderCell: (params) => (
                <IconButton
                    color="primary"
                    size="small"
                    onClick={() => navigate(`/compliance/${params.row.host_id}`)}
                    title={t('common.view')}
                >
                    <VisibilityIcon />
                </IconButton>
            )
        }
    ], [t, navigate]);

    // Search columns configuration
    const searchColumns = [
        { field: 'hostname', label: t('compliancePage.hostname') },
        { field: 'fqdn', label: 'FQDN' },
        { field: 'compliance_grade', label: t('compliancePage.complianceGrade') }
    ];

    // Load data
    const loadData = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);
            const response = await getComplianceHosts();
            setTableData(response.hosts);
        } catch (err) {
            console.error('Error loading compliance hosts:', err);
            setError(t('compliancePage.loadError'));
        } finally {
            setLoading(false);
        }
    }, [t]);

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
            return;
        }
        loadData();
    }, [navigate, loadData]);

    // Search functionality
    const performSearch = useCallback(() => {
        let filtered = [...tableData];

        if (searchTerm.trim()) {
            filtered = filtered.filter(host => {
                const fieldValue = host[searchColumn as keyof HostComplianceSummary];
                if (fieldValue === null || fieldValue === undefined) {
                    return false;
                }
                const stringValue = String(fieldValue);
                return stringValue.toLowerCase().includes(searchTerm.toLowerCase());
            });
        }

        setFilteredData(filtered);
    }, [tableData, searchTerm, searchColumn]);

    // Update filtered data when search criteria changes
    useEffect(() => {
        performSearch();
    }, [performSearch]);

    // Memoize column visibility model
    const columnVisibilityModel = useMemo(() => ({
        ...getColumnVisibilityModel(),
    }), [getColumnVisibilityModel]);

    if (error) {
        return (
            <Box sx={{ p: 3 }}>
                <Typography color="error">{error}</Typography>
            </Box>
        );
    }

    return (
        <Box sx={{
            display: 'flex',
            flexDirection: 'column',
            height: 'calc(100vh - 120px)',
            gap: 2,
            p: 2
        }}>
            {/* Title */}
            <Typography variant="h4" component="h1">
                {t('compliancePage.title')}
            </Typography>

            {/* Search Controls */}
            <Box sx={{
                p: 2,
                bgcolor: 'background.paper',
                borderRadius: 1,
                boxShadow: 1,
                display: 'flex',
                alignItems: 'center',
                gap: 3,
                flexWrap: 'wrap',
                flexShrink: 0
            }}>
                <SearchBox
                    searchTerm={searchTerm}
                    setSearchTerm={setSearchTerm}
                    searchColumn={searchColumn}
                    setSearchColumn={setSearchColumn}
                    columns={searchColumns}
                    placeholder={t('compliancePage.searchPlaceholder')}
                    inline={true}
                />

                <Box sx={{ flexGrow: 1 }} />

                <ColumnVisibilityButton
                    columns={columns
                        .filter(col => col.field !== 'actions')
                        .map(col => ({ field: col.field, headerName: col.headerName || col.field }))}
                    hiddenColumns={hiddenColumns}
                    onColumnsChange={setHiddenColumns}
                    onReset={resetPreferences}
                />
            </Box>

            {/* DataGrid */}
            <Box sx={{ flexGrow: 1, minHeight: 0 }}>
                <DataGrid
                    rows={filteredData || []}
                    columns={columns || []}
                    loading={loading}
                    getRowId={(row) => row.host_id}
                    paginationModel={paginationModel || { page: 0, pageSize: 10 }}
                    onPaginationModelChange={setPaginationModel}
                    initialState={{
                        sorting: {
                            sortModel: [{ field: 'compliance_score', sort: 'asc' }],
                        },
                    }}
                    columnVisibilityModel={columnVisibilityModel}
                    pageSizeOptions={safePageSizeOptions}
                    localeText={{
                        MuiTablePagination: {
                            labelRowsPerPage: t('common.rowsPerPage'),
                            labelDisplayedRows: ({ from, to, count }: { from: number, to: number, count: number }) => {
                                const countDisplay = count === -1 ? `${t('common.of')} ${to}` : count;
                                return `${from}–${to} ${t('common.of')} ${countDisplay}`;
                            },
                        },
                        noRowsLabel: t('compliancePage.noHosts'),
                        noResultsOverlayLabel: t('compliancePage.noHosts'),
                    }}
                />
            </Box>
        </Box>
    );
};

export default CompliancePage;
