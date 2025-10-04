import React, { useEffect } from 'react';
import { useNavigate } from "react-router-dom";
import { useTranslation } from 'react-i18next';
import { clearPermissionsCache } from '../Services/permissions';

const Logout = () => {

    const navigate = useNavigate();
    const { t } = useTranslation();

    useEffect(() => {
        localStorage.removeItem("userid");
        localStorage.removeItem("bearer_token");
        clearPermissionsCache();
        navigate("/login");
    });

    return (
        <div>{t('logout.loading', 'Logging out...')}</div>
    );
};

export default Logout;