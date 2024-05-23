import React, { useEffect } from 'react';
import { useNavigate } from "react-router-dom";

import { useAuth } from "../components/AuthContext";

const LogOut = () => {
    const { doLogout } = useAuth();
    
    const navigate = useNavigate();

    useEffect(() => {
        doLogout()
        .then (() => {
            console.log("Navigating to /login...")
            navigate("/login");
        });
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