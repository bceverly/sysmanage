import { useNavigate } from "react-router-dom";
import React, { useEffect } from 'react';
import axios from "axios";

const Dashboard = () => {
    const navigate = useNavigate();

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
        }
        console.log('Passing token in Dashboard:' + localStorage.getItem('bearer_token'));

        axios.post('https://api.sysmanage.org:8443/validate', {}, {
            headers: {
                'Content-Type': "application/json",
                'Authorization': "Bearer " + localStorage.getItem('bearer_token'),
            }
        })
        .then((response) => {
            console.log("validate call successful");
            localStorage.setItem('bearer_token', response.headers.reauthorization);
        })
        .catch((error) => {
            localStorage.removeItem("userid");
            localStorage.removeItem("bearer_token");
            navigate("/login");
        });
    });
    return <div>Dashboard</div>;
}
 
export default Dashboard;