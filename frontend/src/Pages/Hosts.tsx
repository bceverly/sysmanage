import { useNavigate } from "react-router-dom";
import React, { useEffect } from 'react';

import { SysManageHost, doGetHosts } from '../Services/hosts'

const Hosts = () => {
    const navigate = useNavigate();

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
        }
        doGetHosts().then((response: SysManageHost[]) => {
            console.log('Num hosts returned: ' + response.length);
            console.log("typeof(response): " + typeof response);
            for (let i=0 ; i<response.length ; i++) {
                console.log(response[i]);
            }
        });
    });
    return <div>Hosts</div>;
}
 
export default Hosts;