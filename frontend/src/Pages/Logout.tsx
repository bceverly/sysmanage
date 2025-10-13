import React, { useEffect } from 'react';
import { useNavigate } from "react-router-dom";
import { useTranslation } from 'react-i18next';
import { clearPermissionsCache } from '../Services/permissions';
import axiosInstance from '../Services/api';

const Logout = () => {

    const navigate = useNavigate();
    const { t } = useTranslation();

    useEffect(() => {
        const performLogout = async () => {
            try {
                // Call logout endpoint for audit logging
                await axiosInstance.post('/api/auth/logout');
            } catch (error) {
                // Ignore errors - proceed with logout anyway
                console.error('Logout endpoint error:', error);
            } finally {
                // Clear local storage and navigate to login
                localStorage.removeItem("userid");
                localStorage.removeItem("bearer_token");
                clearPermissionsCache();
                navigate("/login");
            }
        };

        performLogout();
    }, [navigate]);

    return (
        <div>{t('logout.loading', 'Logging out...')}</div>
    );
};

export default Logout;