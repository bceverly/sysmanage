import { useNavigate } from "react-router-dom";
import React, { useEffect } from 'react';
import api from "../Services/api"

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