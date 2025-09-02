import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
    Avatar,
    Menu,
    MenuItem,
    ListItemIcon,
    ListItemText,
    Divider,
    Typography,
    Box
} from '@mui/material';
import {
    Person as PersonIcon,
    Logout as LogoutIcon
} from '@mui/icons-material';

const UserProfileDropdown: React.FC = () => {
    const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
    const open = Boolean(anchorEl);
    const navigate = useNavigate();
    const { t } = useTranslation();

    // Get user ID from localStorage
    const userid = localStorage.getItem('userid') || '';
    
    // Extract first initial from user ID (usually email format)
    const getFirstInitial = (email: string): string => {
        if (!email) return '?';
        const beforeAt = email.split('@')[0];
        return beforeAt.charAt(0).toUpperCase();
    };

    // Extract display name from user ID
    const getDisplayName = (email: string): string => {
        if (!email) return t('userProfile.unknownUser', 'Unknown User');
        return email;
    };

    const handleClick = (event: React.MouseEvent<HTMLElement>) => {
        setAnchorEl(event.currentTarget);
    };

    const handleClose = () => {
        setAnchorEl(null);
    };

    const handleProfile = () => {
        handleClose();
        navigate('/profile');
    };

    const handleLogout = () => {
        handleClose();
        navigate('/logout');
    };

    return (
        <>
            <Avatar
                onClick={handleClick}
                sx={{
                    width: 40,
                    height: 40,
                    bgcolor: 'primary.main',
                    cursor: 'pointer',
                    fontSize: '16px',
                    fontWeight: 'bold',
                    '&:hover': {
                        bgcolor: 'primary.dark',
                    }
                }}
                aria-label={t('userProfile.userMenu', 'User menu')}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        handleClick(e as React.KeyboardEvent<HTMLElement> & { currentTarget: HTMLElement });
                    }
                }}
            >
                {getFirstInitial(userid)}
            </Avatar>

            <Menu
                anchorEl={anchorEl}
                open={open}
                onClose={handleClose}
                onClick={handleClose}
                transformOrigin={{ horizontal: 'right', vertical: 'top' }}
                anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
                PaperProps={{
                    elevation: 3,
                    sx: {
                        mt: 1,
                        minWidth: 200,
                        '& .MuiMenuItem-root': {
                            px: 2,
                            py: 1,
                        }
                    }
                }}
            >
                {/* User name at top */}
                <Box sx={{ px: 2, py: 1 }}>
                    <Typography variant="subtitle1" sx={{ fontWeight: 'bold' }}>
                        {getDisplayName(userid)}
                    </Typography>
                </Box>
                
                <Divider />
                
                {/* Profile link */}
                <MenuItem onClick={handleProfile}>
                    <ListItemIcon>
                        <PersonIcon fontSize="small" />
                    </ListItemIcon>
                    <ListItemText primary={t('userProfile.profile', 'Profile')} />
                </MenuItem>
                
                <Divider />
                
                {/* Logout link */}
                <MenuItem onClick={handleLogout}>
                    <ListItemIcon>
                        <LogoutIcon fontSize="small" />
                    </ListItemIcon>
                    <ListItemText primary={t('nav.logout', 'Logout')} />
                </MenuItem>
            </Menu>
        </>
    );
};

export default UserProfileDropdown;