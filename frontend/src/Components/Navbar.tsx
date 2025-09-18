import React, { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { IoClose, IoMenu, IoSettingsOutline } from "react-icons/io5";
import { useTranslation } from 'react-i18next';
import { IconButton } from '@mui/material';
import "./css/Navbar.css";
import SysManageLogo from "../assets/sysmanage-logo.svg";
import LanguageSelector from "./LanguageSelector";
import ConnectionStatusIndicator from "./ConnectionStatusIndicator";
import UserProfileDropdown from "./UserProfileDropdown";
import NotificationBell from "./NotificationBell";

const Navbar = () => {
  const [showMenu, setShowMenu] = useState(false);
  const { t } = useTranslation();
  const navigate = useNavigate();

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

  const handleSettingsClick = () => {
    navigate('/settings');
  };

  return (
    <header className="header">
      <nav className="nav container">
        <NavLink to="/" className="nav__logo">
          <img src={SysManageLogo} alt={t('nav.logoAlt', 'SysManage')} className="nav__logo-img" />
        </NavLink>

        <div
          className={`nav__menu ${showMenu ? "show-menu" : ""}`}
          id="nav-menu"
          style={{visibility: menuVisible}}
        >
          <ul className="nav__list">
            <li className="nav__item">
              <NavLink 
                to="/" 
                className="nav__link" 
                onClick={closeMenuOnMobile}
                end
              >
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
              <NavLink
                to="/updates"
                className="nav__link"
                onClick={closeMenuOnMobile}
              >
                {t('nav.updates')}
              </NavLink>
            </li>
            <li className="nav__item">
              <NavLink
                to="/scripts"
                className="nav__link"
                onClick={closeMenuOnMobile}
              >
                {t('nav.scripts')}
              </NavLink>
            </li>
            <li className="nav__item">
              <NavLink
                to="/reports"
                className="nav__link"
                onClick={closeMenuOnMobile}
              >
                {t('nav.reports')}
              </NavLink>
            </li>
          </ul>
          <div className="nav__close" id="nav-close" onClick={toggleMenu}>
              <IoClose />
          </div>
        </div>

        {/* Language selector, connection status, and notifications at toolbar level */}
        <div className="nav__language-toolbar" style={{visibility: menuVisible}}>
          <ConnectionStatusIndicator />
          <NotificationBell />
          <IconButton 
            onClick={handleSettingsClick}
            size="small"
            title={t('nav.settings', 'Settings')}
            sx={{ color: 'inherit', mr: 1 }}
          >
            <IoSettingsOutline />
          </IconButton>
          <UserProfileDropdown />
          <LanguageSelector />
        </div>

        <div className="nav__toggle" id="nav-toggle" onClick={toggleMenu}>
          <IoMenu />
        </div>
      </nav>
    </header>
  );
};

export default Navbar;