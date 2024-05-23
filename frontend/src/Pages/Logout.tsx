import React, { useEffect } from 'react';
import { useNavigate } from "react-router-dom";
import { doLogout } from "../Services/AuthHelper";

const Logout = () => {
//    const { doLogout } = useAuth();
    
    const navigate = useNavigate();

    useEffect(() => {
        console.log('Removing local storage...');
        localStorage.removeItem("userid");
        localStorage.removeItem("bearer_token");
        console.log("local storage removed");
        navigate("/login");
        window.location.reload();

    }, []);

    return (
        <div>Logout</div>
    );
};

export default Logout;