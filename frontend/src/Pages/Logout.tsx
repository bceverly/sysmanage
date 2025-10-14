import React, { useEffect } from 'react';
import { useNavigate } from "react-router-dom";
import { useTranslation } from 'react-i18next';
import { clearPermissionsCache } from '../Services/permissions';
import axiosInstance from '../Services/api';

const Logout = () => {

    const navigate = useNavigate();
    const { t } = useTranslation();

    useEffect(() => {
        const performLogout = () => {
            // Clear local storage and navigate to login immediately
            // Don't wait for the audit log API call
            localStorage.removeItem("userid");
            localStorage.removeItem("bearer_token");
            clearPermissionsCache();
            navigate("/login");

            // Call logout endpoint for audit logging in background (fire and forget)
            // This doesn't block the user experience
            axiosInstance.post('/logout').catch((error) => {
                // Silently ignore errors - user is already logged out client-side
                console.debug('Logout audit log failed (non-critical):', error);
            });
        };

        performLogout();
    }, [navigate]);

    return (
        <div>{t('logout.loading', 'Logging out...')}</div>
    );
};

export default Logout;