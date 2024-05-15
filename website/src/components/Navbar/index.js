import React from "react";

import {
    Nav,
    NavLogo,
    NavLink,
    Bars,
    NavMenu,
    NavBtn,
    NavBtnLink,
} from "./NavbarElements";

const Navbar = () => {
    return (
        <>
           <Nav>
            <NavLogo to="/">
                SysManage
            </NavLogo>
            <Bars />

            <NavMenu>
                <NavLink 
                  to="/"
                  activestyle={{ color:'black' }}
                >
                    Dashboard
                </NavLink>
                <NavLink 
                  to="/hosts"
                  activestyle={{ color: 'black' }}
                >
                    Hosts
                </NavLink>
                <NavLink 
                  to="/users" 
                  activestyle={{ color: 'black' }}
                >
                    Users
                </NavLink>
                <NavLink
                  to="/login"
                  activestyle={{ color: 'black' }}
                >
                    Log In
                </NavLink>
            </NavMenu>
           </Nav> 
        </>
    );
};
export default Navbar;