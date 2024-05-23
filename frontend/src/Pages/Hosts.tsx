import { useNavigate } from "react-router-dom";
import React, { useEffect } from 'react';

const Hosts = () => {
    const navigate = useNavigate();

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
        }
    }, []);
    return <div>Hosts</div>;
}
 
export default Hosts;