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
                    Home
                </NavLink>
                <NavLink 
                  to="/about"
                  activestyle={{ color: 'black' }}
                >
                    About
                </NavLink>
                <NavLink 
                  to="/contact" 
                  activestyle={{ color: 'black' }}
                >
                    Contact
                </NavLink>
                <NavLink
                  to="/login"
                  activestyle={{ color: 'black' }}
                >
                    Log In
                </NavLink>
                <NavBtn>
                    <NavBtnLink to="/sign-up">Sign Up</NavBtnLink>
                </NavBtn>
            </NavMenu>
           </Nav> 
        </>
    );
};
export default Navbar;