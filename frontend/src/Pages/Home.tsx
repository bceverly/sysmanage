import { useNavigate } from "react-router-dom";
import React, { useEffect } from 'react';
//import axios from "axios";

const Dashboard = () => {
    const navigate = useNavigate();

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
        }
    });
    return <div>Dashboard</div>;
}
 
export default Dashboard;