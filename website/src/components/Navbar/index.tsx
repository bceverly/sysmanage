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
    if (!localStorage.getItem('bearer_token')) {
        console.log("not logged in");
        return (
            <>
            <Nav>
                <NavLogo to="/">
                    SysManage
                </NavLogo>
            </Nav>
            </>
        );
    }
    console.log("logged in");
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
                <NavBtn>
                    <NavBtnLink to="/logout">Log Out</NavBtnLink>
                </NavBtn>
            </NavMenu>
           </Nav> 
        </>
    );
};
export default Navbar;