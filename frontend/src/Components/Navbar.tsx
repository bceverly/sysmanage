import React, { useState } from "react";
import { NavLink } from "react-router-dom";
import { IoClose, IoMenu } from "react-icons/io5";
import { useTranslation } from 'react-i18next';
import "./css/Navbar.css";
import SysManageLogo from "../assets/sysmanage-logo.svg";
import LanguageSelector from "./LanguageSelector";

const Navbar = () => {
  const [showMenu, setShowMenu] = useState(false);
  const { t } = useTranslation();

  const toggleMenu = () => {
    setShowMenu(!showMenu);
  };

  const closeMenuOnMobile = () => {
    if (window.innerWidth <= 1150) {
      setShowMenu(false);
    }
  };

  const checkIfLoggedIn = () => {
    if (localStorage.getItem('bearer_token')) {
      return "visible";
    }

    return "hidden";
  };

  const menuVisible = checkIfLoggedIn();

  return (
    <header className="header">
      <nav className="nav container">
        <NavLink to="/" className="nav__logo">
          <img src={SysManageLogo} alt="SysManage" className="nav__logo-img" />
        </NavLink>

        {/* Language selector at toolbar level */}
        <div className="nav__language-toolbar" style={{visibility: menuVisible}}>
          <LanguageSelector />
        </div>

        <div
          className={`nav__menu ${showMenu ? "show-menu" : ""}`}
          id="nav-menu"
          style={{visibility: menuVisible}}
        >
          <ul className="nav__list">
            <li className="nav__item">
              <NavLink to="/" className="nav__link" onClick={closeMenuOnMobile}>
                {t('nav.dashboard')}
              </NavLink>
            </li>
            <li className="nav__item">
              <NavLink
                to="/hosts"
                className="nav__link"
                onClick={closeMenuOnMobile}
              >
                {t('nav.hosts')}
              </NavLink>
            </li>
            <li className="nav__item">
              <NavLink
                to="/users"
                className="nav__link"
                onClick={closeMenuOnMobile}
              >
                {t('nav.users')}
              </NavLink>
            </li>
            <li className="nav__item">
              <NavLink to="/logout" className="nav__link nav__cta">
                {t('nav.logout')}
              </NavLink>
            </li>
          </ul>
          <div className="nav__close" id="nav-close" onClick={toggleMenu}>
            {/* @ts-expect-error - IoClose component type issues */}
            <IoClose />
          </div>
        </div>

        <div className="nav__toggle" id="nav-toggle" onClick={toggleMenu}>
          {/* @ts-expect-error - IoMenu component type issues */}
          <IoMenu />
        </div>
      </nav>
    </header>
  );
};

export default Navbar;