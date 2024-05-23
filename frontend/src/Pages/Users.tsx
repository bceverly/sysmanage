import { useNavigate } from "react-router-dom";
import React, { useEffect } from 'react';

const Users = () => {
    const navigate = useNavigate();

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
        }
    }, []);
    return <div>Users</div>;
}
 
export default Users;