/**
 * Expose shared dependencies on the window object for plugins.
 *
 * This module must be imported early in the application lifecycle
 * (before any plugin bundles load) so that plugins can access
 * React, MUI, and application-specific utilities from the host app.
 */

import * as React from 'react';
import * as ReactRouterDOM from 'react-router-dom';
import * as ReactI18next from 'react-i18next';

// MUI Material components used by plugins
import {
    Accordion,
    AccordionDetails,
    AccordionSummary,
    Alert,
    Box,
    Button,
    Card,
    CardContent,
    Checkbox,
    Chip,
    CircularProgress,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Divider,
    FormControl,
    FormControlLabel,
    Grid,
    IconButton,
    InputAdornment,
    InputLabel,
    LinearProgress,
    List,
    ListItem,
    ListItemIcon,
    ListItemText,
    MenuItem,
    Paper,
    Select,
    Stack,
    Switch,
    Tab,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Tabs,
    TextField,
    Tooltip,
    Typography,
} from '@mui/material';

// MUI X DataGrid
import { DataGrid } from '@mui/x-data-grid';

// MUI Icons used by plugins
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import BugReportIcon from '@mui/icons-material/BugReport';
import BusinessIcon from '@mui/icons-material/Business';
import CalendarTodayIcon from '@mui/icons-material/CalendarToday';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ComputerIcon from '@mui/icons-material/Computer';
import DeleteIcon from '@mui/icons-material/Delete';
import ErrorIcon from '@mui/icons-material/Error';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExtensionIcon from '@mui/icons-material/Extension';
import HealthAndSafetyIcon from '@mui/icons-material/HealthAndSafety';
import HistoryIcon from '@mui/icons-material/History';
import InfoIcon from '@mui/icons-material/Info';
import KeyIcon from '@mui/icons-material/Key';
import LightbulbIcon from '@mui/icons-material/Lightbulb';
import RefreshIcon from '@mui/icons-material/Refresh';
import SaveIcon from '@mui/icons-material/Save';
import ScheduleIcon from '@mui/icons-material/Schedule';
import SecurityIcon from '@mui/icons-material/Security';
import StarIcon from '@mui/icons-material/Star';
import StorageIcon from '@mui/icons-material/Storage';
import VerifiedUserIcon from '@mui/icons-material/VerifiedUser';
import VisibilityIcon from '@mui/icons-material/Visibility';
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff';
import ViewInArIcon from '@mui/icons-material/ViewInAr';
import VpnKeyIcon from '@mui/icons-material/VpnKey';
import WarningIcon from '@mui/icons-material/Warning';
import AssessmentIcon from '@mui/icons-material/Assessment';

// Application-specific shared utilities
import axiosInstance from '../Services/api';
import { useTablePageSize } from '../hooks/useTablePageSize';
import { useColumnVisibility } from '../hooks/useColumnVisibility';
import SearchBox from '../Components/SearchBox';
import ColumnVisibilityButton from '../Components/ColumnVisibilityButton';
import { getLicenseInfo } from '../Services/license';
import i18n from '../i18n/i18n';
import { pluginManager } from './PluginManager';

// Expose shared dependencies on globalThis for plugin consumption
(globalThis as unknown as { __SYSMANAGE_SHARED__: unknown }).__SYSMANAGE_SHARED__ = {
    React,
    ReactRouterDOM,
    ReactI18next,
    MuiMaterial: {
        Accordion,
        AccordionDetails,
        AccordionSummary,
        Alert,
        Box,
        Button,
        Card,
        CardContent,
        Checkbox,
        Chip,
        CircularProgress,
        Dialog,
        DialogActions,
        DialogContent,
        DialogTitle,
        Divider,
        FormControl,
        FormControlLabel,
        Grid,
        IconButton,
        InputAdornment,
        InputLabel,
        LinearProgress,
        List,
        ListItem,
        ListItemIcon,
        ListItemText,
        MenuItem,
        Paper,
        Select,
        Stack,
        Switch,
        Tab,
        Table,
        TableBody,
        TableCell,
        TableContainer,
        TableHead,
        TableRow,
        Tabs,
        TextField,
        Tooltip,
        Typography,
    },
    MuiXDataGrid: {
        DataGrid,
    },
    MuiIcons: {
        ArrowBackIcon,
        BugReportIcon,
        BusinessIcon,
        CalendarTodayIcon,
        CheckCircleIcon,
        ComputerIcon,
        DeleteIcon,
        ErrorIcon,
        ExpandMoreIcon,
        ExtensionIcon,
        HealthAndSafetyIcon,
        HistoryIcon,
        InfoIcon,
        KeyIcon,
        LightbulbIcon,
        RefreshIcon,
        SaveIcon,
        ScheduleIcon,
        SecurityIcon,
        StarIcon,
        StorageIcon,
        VerifiedUserIcon,
        ViewInArIcon,
        VisibilityIcon,
        VisibilityOffIcon,
        VpnKeyIcon,
        WarningIcon,
        AssessmentIcon,
    },
    axiosInstance,
    hooks: {
        useTablePageSize,
        useColumnVisibility,
    },
    components: {
        SearchBox,
        ColumnVisibilityButton,
    },
    services: {
        getLicenseInfo,
    },
    i18n,
    registerPlugin: pluginManager.registerPlugin,
};
