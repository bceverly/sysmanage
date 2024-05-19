import React, { useEffect } from 'react';
import { useNavigate } from "react-router-dom";
import AuthProvider from "../classes/AuthProvider.tsx";

const LogOut = () => {
    const navigate = useNavigate();

    useEffect(() => {
        AuthProvider.doLogout();
        navigate("/login");
    }, []);

    return (
        <div
            style={{
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                height: '100vh'
            }}
        >
           <h1>Logout</h1> 
        </div>
    );
};

export default LogOut;