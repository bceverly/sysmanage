import { useNavigate, useParams } from "react-router-dom";
import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import RefreshIcon from '@mui/icons-material/Refresh';
import CircularProgress from '@mui/material/CircularProgress';
import { Chip, Stack, Paper } from '@mui/material';
import { useTranslation } from 'react-i18next';

import { ComplianceScan, ComplianceRuleResult, getHostComplianceScan, runHostComplianceScan } from '../Services/license';
import { useTablePageSize } from '../hooks/useTablePageSize';
import { useColumnVisibility } from '../Hooks/useColumnVisibility';
import SearchBox from '../Components/SearchBox';
import ColumnVisibilityButton from '../Components/ColumnVisibilityButton';

const ComplianceHostDetail = () => {
    const { hostId } = useParams<{ hostId: string }>();
    const [scanData, setScanData] = useState<ComplianceScan | null>(null);
    const [filteredData, setFilteredData] = useState<ComplianceRuleResult[]>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [scanning, setScanning] = useState<boolean>(false);
    const [error, setError] = useState<string | null>(null);
    const [searchTerm, setSearchTerm] = useState<string>('');
    const [searchColumn, setSearchColumn] = useState<string>('rule_id');
    const navigate = useNavigate();
    const { t } = useTranslation();

    // Dynamic table page sizing based on window height
    const { pageSize, pageSizeOptions } = useTablePageSize({
        reservedHeight: 300,
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
    } = useColumnVisibility('compliance-detail-grid');

    // Get severity color
    const getSeverityColor = (severity: string): 'error' | 'warning' | 'info' | 'default' => {
        switch (severity?.toUpperCase()) {
            case 'CRITICAL':
                return 'error';
            case 'HIGH':
                return 'error';
            case 'MEDIUM':
                return 'warning';
            case 'LOW':
                return 'info';
            default:
                return 'default';
        }
    };

    // Get status color
    const getStatusColor = (status: string): 'success' | 'error' | 'warning' | 'default' => {
        switch (status?.toLowerCase()) {
            case 'pass':
                return 'success';
            case 'fail':
                return 'error';
            case 'error':
                return 'warning';
            case 'n/a':
            case 'not_applicable':
                return 'default';
            default:
                return 'default';
        }
    };

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

    // Memoize columns
    const columns: GridColDef[] = useMemo(() => [
        {
            field: 'rule_id',
            headerName: t('compliancePage.ruleId'),
            width: 160,
        },
        {
            field: 'rule_name',
            headerName: t('compliancePage.ruleName'),
            width: 250,
        },
        {
            field: 'category',
            headerName: t('compliancePage.category'),
            width: 150,
        },
        {
            field: 'benchmark',
            headerName: t('compliancePage.benchmark'),
            width: 120,
        },
        {
            field: 'severity',
            headerName: t('compliancePage.severity'),
            width: 120,
            align: 'center',
            headerAlign: 'center',
            renderCell: (params) => (
                <Chip
                    label={params.value}
                    size="small"
                    color={getSeverityColor(params.value)}
                />
            )
        },
        {
            field: 'status',
            headerName: t('compliancePage.status'),
            width: 100,
            align: 'center',
            headerAlign: 'center',
            renderCell: (params) => (
                <Chip
                    label={params.value}
                    size="small"
                    color={getStatusColor(params.value)}
                />
            )
        },
        {
            field: 'remediation',
            headerName: t('compliancePage.remediation'),
            flex: 1,
            minWidth: 300,
            renderCell: (params) => (
                <Box sx={{
                    whiteSpace: 'normal',
                    wordWrap: 'break-word',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    display: '-webkit-box',
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: 'vertical',
                }}>
                    {params.value || '-'}
                </Box>
            )
        }
    ], [t]);

    // Search columns configuration
    const searchColumns = [
        { field: 'rule_id', label: t('compliancePage.ruleId') },
        { field: 'rule_name', label: t('compliancePage.ruleName') },
        { field: 'category', label: t('compliancePage.category') },
        { field: 'status', label: t('compliancePage.status') }
    ];

    // Load data
    const loadData = useCallback(async () => {
        if (!hostId) return;

        try {
            setLoading(true);
            setError(null);
            const response = await getHostComplianceScan(hostId);
            setScanData(response);
        } catch (err) {
            console.error('Error loading compliance scan:', err);
            setError(t('compliancePage.loadError'));
        } finally {
            setLoading(false);
        }
    }, [hostId, t]);

    // Run new scan
    const handleRunScan = async () => {
        if (!hostId) return;

        try {
            setScanning(true);
            setError(null);
            await runHostComplianceScan(hostId);
            // Reload data after scan
            await loadData();
        } catch (err) {
            console.error('Error running compliance scan:', err);
            setError(t('compliancePage.scanError'));
        } finally {
            setScanning(false);
        }
    };

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
            return;
        }
        loadData();
    }, [navigate, loadData]);

    // Search functionality
    const performSearch = useCallback(() => {
        if (!scanData?.results) {
            setFilteredData([]);
            return;
        }

        let filtered = [...scanData.results];

        if (searchTerm.trim()) {
            filtered = filtered.filter(rule => {
                const fieldValue = rule[searchColumn as keyof ComplianceRuleResult];
                if (fieldValue === null || fieldValue === undefined) {
                    return false;
                }
                const stringValue = String(fieldValue);
                return stringValue.toLowerCase().includes(searchTerm.toLowerCase());
            });
        }

        setFilteredData(filtered);
    }, [scanData, searchTerm, searchColumn]);

    // Update filtered data when search criteria changes
    useEffect(() => {
        performSearch();
    }, [performSearch]);

    // Memoize column visibility model
    const columnVisibilityModel = useMemo(() => ({
        ...getColumnVisibilityModel(),
    }), [getColumnVisibilityModel]);

    return (
        <Box sx={{
            display: 'flex',
            flexDirection: 'column',
            height: 'calc(100vh - 120px)',
            gap: 2,
            p: 2
        }}>
            {/* Header with back button */}
            <Stack direction="row" spacing={2} alignItems="center">
                <Button
                    startIcon={<ArrowBackIcon />}
                    onClick={() => navigate('/compliance')}
                >
                    {t('compliancePage.backToList')}
                </Button>
                <Typography variant="h4" component="h1" sx={{ flexGrow: 1 }}>
                    {t('compliancePage.hostCompliance')}
                </Typography>
                <Button
                    variant="contained"
                    startIcon={scanning ? <CircularProgress size={20} color="inherit" /> : <RefreshIcon />}
                    onClick={handleRunScan}
                    disabled={scanning}
                >
                    {scanning ? t('compliancePage.scanning') : t('compliancePage.runScan')}
                </Button>
            </Stack>

            {/* Error display */}
            {error && (
                <Typography color="error">{error}</Typography>
            )}

            {/* Summary Cards */}
            {scanData && (
                <Paper sx={{ p: 2 }}>
                    <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
                        <Box>
                            <Typography variant="caption" color="text.secondary">
                                {t('compliancePage.lastScanned')}
                            </Typography>
                            <Typography>
                                {scanData.scanned_at
                                    ? new Date(scanData.scanned_at).toLocaleString()
                                    : t('compliancePage.notScanned')
                                }
                            </Typography>
                        </Box>
                        <Box>
                            <Typography variant="caption" color="text.secondary">
                                {t('compliancePage.complianceGrade')}
                            </Typography>
                            <Box>
                                <Chip
                                    label={scanData.compliance_grade || '-'}
                                    size="small"
                                    color={getGradeColor(scanData.compliance_grade || '')}
                                />
                            </Box>
                        </Box>
                        <Box>
                            <Typography variant="caption" color="text.secondary">
                                {t('compliancePage.complianceScore')}
                            </Typography>
                            <Typography>{scanData.compliance_score ?? '-'}</Typography>
                        </Box>
                        <Box>
                            <Typography variant="caption" color="text.secondary">
                                {t('compliancePage.critical')}
                            </Typography>
                            <Box>
                                <Chip label={scanData.critical_failures || 0} size="small" color={scanData.critical_failures ? 'error' : 'default'} />
                            </Box>
                        </Box>
                        <Box>
                            <Typography variant="caption" color="text.secondary">
                                {t('compliancePage.high')}
                            </Typography>
                            <Box>
                                <Chip label={scanData.high_failures || 0} size="small" color={scanData.high_failures ? 'error' : 'default'} />
                            </Box>
                        </Box>
                        <Box>
                            <Typography variant="caption" color="text.secondary">
                                {t('compliancePage.medium')}
                            </Typography>
                            <Box>
                                <Chip label={scanData.medium_failures || 0} size="small" color={scanData.medium_failures ? 'warning' : 'default'} />
                            </Box>
                        </Box>
                        <Box>
                            <Typography variant="caption" color="text.secondary">
                                {t('compliancePage.low')}
                            </Typography>
                            <Box>
                                <Chip label={scanData.low_failures || 0} size="small" color={scanData.low_failures ? 'info' : 'default'} />
                            </Box>
                        </Box>
                    </Stack>
                </Paper>
            )}

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
                        .map(col => ({ field: col.field, headerName: col.headerName || col.field }))}
                    hiddenColumns={hiddenColumns}
                    onColumnsChange={setHiddenColumns}
                    onReset={resetPreferences}
                />
            </Box>

            {/* DataGrid */}
            <Box sx={{ flexGrow: 1, minHeight: 0 }}>
                {filteredData.length === 0 && !loading ? (
                    <Box sx={{
                        display: 'flex',
                        justifyContent: 'center',
                        alignItems: 'center',
                        height: '100%',
                        bgcolor: 'background.paper',
                        borderRadius: 1
                    }}>
                        <Typography color="text.secondary">
                            {t('compliancePage.noRules')}
                        </Typography>
                    </Box>
                ) : (
                    <DataGrid
                        rows={filteredData || []}
                        columns={columns || []}
                        loading={loading}
                        getRowId={(row) => row.rule_id}
                        paginationModel={paginationModel || { page: 0, pageSize: 10 }}
                        onPaginationModelChange={setPaginationModel}
                        initialState={{
                            sorting: {
                                sortModel: [{ field: 'severity', sort: 'asc' }],
                            },
                        }}
                        columnVisibilityModel={columnVisibilityModel}
                        pageSizeOptions={safePageSizeOptions}
                        getRowHeight={() => 'auto'}
                        sx={{
                            '& .MuiDataGrid-cell': {
                                py: 1,
                            },
                        }}
                        localeText={{
                            MuiTablePagination: {
                                labelRowsPerPage: t('common.rowsPerPage'),
                                labelDisplayedRows: ({ from, to, count }: { from: number, to: number, count: number }) => {
                                    const countDisplay = count === -1 ? `${t('common.of')} ${to}` : count;
                                    return `${from}–${to} ${t('common.of')} ${countDisplay}`;
                                },
                            },
                            noRowsLabel: t('compliancePage.noRules'),
                            noResultsOverlayLabel: t('compliancePage.noRules'),
                        }}
                    />
                )}
            </Box>
        </Box>
    );
};

export default ComplianceHostDetail;
