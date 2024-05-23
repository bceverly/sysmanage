import React, { useEffect } from 'react';
import { useNavigate } from "react-router-dom";

const Logout = () => {
    
    const navigate = useNavigate();

    useEffect(() => {
        localStorage.removeItem("userid");
        localStorage.removeItem("bearer_token");
        navigate("/login");
        window.location.reload();
    });

    return (
        <div>Logout</div>
    );
};

export default Logout;