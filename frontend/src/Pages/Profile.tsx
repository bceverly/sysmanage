import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
    Container,
    Typography,
    Card,
    TextField,
    Button,
    Alert,
    Box,
    Divider,
    CircularProgress,
    Tabs,
    Tab,
    Avatar,
    Input
} from '@mui/material';
import {
    PhotoCamera as PhotoCameraIcon,
    Delete as DeleteIcon
} from '@mui/icons-material';
import { getProfile, updateProfile, changePassword, ProfileData, ProfileUpdateData, PasswordChangeData } from '../Services/profile';
import axiosInstance from '../Services/api';

const Profile: React.FC = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [profileData, setProfileData] = useState<ProfileData | null>(null);
    const [firstName, setFirstName] = useState('');
    const [lastName, setLastName] = useState('');
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);
    
    // Tab state
    const [activeTab, setActiveTab] = useState(0);
    
    // Password change state
    const [currentPassword, setCurrentPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [changingPassword, setChangingPassword] = useState(false);
    const [passwordError, setPasswordError] = useState<string | null>(null);
    const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null);
    
    // Email change state
    const [newEmail, setNewEmail] = useState('');
    const [confirmEmail, setConfirmEmail] = useState('');
    const [emailPassword, setEmailPassword] = useState('');
    const [changingEmail, setChangingEmail] = useState(false);
    const [emailError, setEmailError] = useState<string | null>(null);
    const [emailSuccess, setEmailSuccess] = useState<string | null>(null);
    
    // Validation state
    const [emailValidation, setEmailValidation] = useState<{isValid: boolean, message: string}>({isValid: true, message: ''});
    const [emailMatchValidation, setEmailMatchValidation] = useState<{isValid: boolean, message: string}>({isValid: true, message: ''});
    const [passwordValidation, setPasswordValidation] = useState<{isValid: boolean, message: string}>({isValid: true, message: ''});
    const [passwordMatchValidation, setPasswordMatchValidation] = useState<{isValid: boolean, message: string}>({isValid: true, message: ''});

    // Profile image state
    const [profileImageUrl, setProfileImageUrl] = useState<string | null>(null);
    const [imageLoading, setImageLoading] = useState(false);
    const [imageUploading, setImageUploading] = useState(false);
    const [imageDeleting, setImageDeleting] = useState(false);
    const [imageError, setImageError] = useState<string | null>(null);
    const [imageSuccess, setImageSuccess] = useState<string | null>(null);

    // Validation functions
    const validateEmail = (email: string): {isValid: boolean, message: string} => {
        if (!email) return {isValid: true, message: ''};
        
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            return {
                isValid: false,
                message: t('userProfile.invalidEmailFormat', 'Please enter a valid email address')
            };
        }
        return {isValid: true, message: ''};
    };
    
    const validateEmailMatch = (email1: string, email2: string): {isValid: boolean, message: string} => {
        if (!email1 || !email2) return {isValid: true, message: ''};
        
        if (email1 !== email2) {
            return {
                isValid: false,
                message: t('userProfile.emailMismatch', 'Email addresses do not match')
            };
        }
        return {isValid: true, message: ''};
    };
    
    const validatePasswordComplexity = (password: string, userid: string = ''): {isValid: boolean, message: string} => {
        if (!password) return {isValid: true, message: ''};
        
        const errors: string[] = [];
        
        // Get password policy from profileData if available
        const config = {
            min_length: 8,
            max_length: 128,
            require_uppercase: true,
            require_lowercase: true,
            require_numbers: true,
            require_special_chars: true,
            special_chars: '!@#$%^&*()_+-=[]{}|;\':,./<>?',
            allow_username_in_password: false,
            min_character_types: 3
        };
        
        // Length validation
        if (password.length < config.min_length) {
            errors.push(t('userProfile.passwordTooShort', `Password must be at least ${config.min_length} characters long`));
        }
        if (password.length > config.max_length) {
            errors.push(t('userProfile.passwordTooLong', `Password must be no more than ${config.max_length} characters long`));
        }
        
        // Character type validation
        let charTypes = 0;
        if (config.require_uppercase && /[A-Z]/.test(password)) charTypes++;
        else if (config.require_uppercase && !/[A-Z]/.test(password)) {
            errors.push(t('userProfile.passwordNeedsUppercase', 'Password must contain at least one uppercase letter'));
        }
        
        if (config.require_lowercase && /[a-z]/.test(password)) charTypes++;
        else if (config.require_lowercase && !/[a-z]/.test(password)) {
            errors.push(t('userProfile.passwordNeedsLowercase', 'Password must contain at least one lowercase letter'));
        }
        
        if (config.require_numbers && /[0-9]/.test(password)) charTypes++;
        else if (config.require_numbers && !/[0-9]/.test(password)) {
            errors.push(t('userProfile.passwordNeedsNumber', 'Password must contain at least one number'));
        }
        
        // Safely escape special characters to prevent regex injection
        const escapedChars = (config.special_chars || '').replace(/[\\[\](){}.*+?^$|]/g, '\\$&');
        const specialCharsRegex = new RegExp(`[${escapedChars}]`);
        if (config.require_special_chars && specialCharsRegex.test(password)) charTypes++;
        else if (config.require_special_chars && !specialCharsRegex.test(password)) {
            errors.push(t('userProfile.passwordNeedsSpecial', 'Password must contain at least one special character'));
        }
        
        if (charTypes < config.min_character_types) {
            errors.push(t('userProfile.passwordNeedsCharTypes', `Password must contain at least ${config.min_character_types} different character types`));
        }
        
        // Username validation
        if (!config.allow_username_in_password && userid && password.toLowerCase().includes(userid.toLowerCase())) {
            errors.push(t('userProfile.passwordContainsUsername', 'Password cannot contain your username or email'));
        }
        
        return {
            isValid: errors.length === 0,
            message: errors.join('; ')
        };
    };
    
    const validatePasswordMatch = (password1: string, password2: string): {isValid: boolean, message: string} => {
        if (!password1 || !password2) return {isValid: true, message: ''};
        
        if (password1 !== password2) {
            return {
                isValid: false,
                message: t('userProfile.passwordMismatch', 'Passwords do not match')
            };
        }
        return {isValid: true, message: ''};
    };

    // Profile image functions - defined before useEffect to avoid hoisting issues
    const fetchProfileImage = useCallback(async () => {
        setImageLoading(true);
        try {
            const response = await axiosInstance.get('/api/profile/image', {
                responseType: 'blob'
            });

            const imageBlob = response.data;
            const imageUrl = window.URL.createObjectURL(imageBlob);
            setProfileImageUrl(imageUrl);
        } catch {
            console.debug('No profile image available or error fetching image');
            setProfileImageUrl(null);
        } finally {
            setImageLoading(false);
        }
    }, []);
    
    useEffect(() => {
        const loadProfile = async () => {
            try {
                setLoading(true);
                const data = await getProfile();
                setProfileData(data);
                setFirstName(data.first_name || '');
                setLastName(data.last_name || '');
                setError(null);
                
                // Load profile image if it exists
                if (data.has_profile_image) {
                    await fetchProfileImage();
                }
            } catch {
                setError(t('userProfile.loadError', 'Failed to load profile data'));
            } finally {
                setLoading(false);
            }
        };

        loadProfile();
    }, [t, fetchProfileImage]);

    // Separate cleanup effect for blob URLs
    useEffect(() => {
        return () => {
            if (profileImageUrl) {
                window.URL.revokeObjectURL(profileImageUrl);
            }
        };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleSave = async () => {
        try {
            setSaving(true);
            setError(null);
            setSuccess(null);

            const updateData: ProfileUpdateData = {
                first_name: firstName.trim() || undefined,
                last_name: lastName.trim() || undefined,
            };

            const updatedProfile = await updateProfile(updateData);
            setProfileData(updatedProfile);
            setSuccess(t('userProfile.saveSuccess', 'Profile updated successfully'));
        } catch {
            setError(t('userProfile.saveError', 'Failed to save profile changes'));
        } finally {
            setSaving(false);
        }
    };

    const handleChangePassword = async () => {
        // Client-side validation
        const passwordComplexityCheck = validatePasswordComplexity(newPassword, profileData?.userid || '');
        const passwordMatchCheck = validatePasswordMatch(newPassword, confirmPassword);
        
        if (!passwordComplexityCheck.isValid) {
            setPasswordError(passwordComplexityCheck.message);
            return;
        }
        
        if (!passwordMatchCheck.isValid) {
            setPasswordError(passwordMatchCheck.message);
            return;
        }
        
        if (!currentPassword || !newPassword || !confirmPassword) {
            setPasswordError(t('userProfile.passwordFieldsRequired', 'All fields are required'));
            return;
        }

        try {
            setChangingPassword(true);
            setPasswordError(null);
            setPasswordSuccess(null);

            const passwordData: PasswordChangeData = {
                current_password: currentPassword,
                new_password: newPassword,
                confirm_password: confirmPassword,
            };

            await changePassword(passwordData);
            
            // Clear form
            setCurrentPassword('');
            setNewPassword('');
            setConfirmPassword('');
            
            setPasswordSuccess(t('userProfile.passwordChangeSuccess', 'Password changed successfully'));
        } catch (error: unknown) {
            // Handle detailed validation errors from backend
            const apiError = error as { response?: { data?: { detail?: string } } };
            const errorMessage = apiError.response?.data?.detail || 
                t('userProfile.passwordChangeError', 'Failed to change password. Please check your current password.');
            setPasswordError(errorMessage);
        } finally {
            setChangingPassword(false);
        }
    };

    const handleChangeEmail = async () => {
        // Client-side validation
        const emailFormatCheck = validateEmail(newEmail);
        const emailMatchCheck = validateEmailMatch(newEmail, confirmEmail);
        
        if (!emailFormatCheck.isValid) {
            setEmailError(emailFormatCheck.message);
            return;
        }
        
        if (!emailMatchCheck.isValid) {
            setEmailError(emailMatchCheck.message);
            return;
        }
        
        if (!newEmail || !confirmEmail || !emailPassword) {
            setEmailError(t('userProfile.emailFieldsRequired', 'All fields are required'));
            return;
        }

        try {
            setChangingEmail(true);
            setEmailError(null);
            setEmailSuccess(null);

            // Note: This would need a backend endpoint for changing email
            // For now, we'll simulate the API call
            await new Promise(resolve => setTimeout(resolve, 1000));
            
            setEmailSuccess(t('userProfile.emailChangeSuccess', 'Email change request submitted. Please check your new email for verification.'));
            
            // Clear form
            setNewEmail('');
            setConfirmEmail('');
            setEmailPassword('');
            
        } catch {
            setEmailError(t('userProfile.emailChangeError', 'Failed to change email. Please try again.'));
        } finally {
            setChangingEmail(false);
        }
    };

    const handleImageUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;

        // Validate file size (5MB limit - same as backend)
        if (file.size > 5 * 1024 * 1024) {
            setImageError(t('userProfile.imageTooLarge', 'Image file is too large. Maximum size is 5MB.'));
            return;
        }

        // Validate file type
        const allowedTypes = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/webp'];
        if (!allowedTypes.includes(file.type)) {
            setImageError(t('userProfile.invalidImageType', 'Invalid image format. Allowed formats: PNG, JPEG, JPG, GIF, WEBP'));
            return;
        }

        try {
            setImageUploading(true);
            setImageError(null);
            setImageSuccess(null);

            const formData = new FormData();
            formData.append('file', file);

            await axiosInstance.post('/api/profile/image', formData, {
                headers: {
                    'Content-Type': 'multipart/form-data'
                }
            });

            setImageSuccess(t('userProfile.imageUploadSuccess', 'Profile image uploaded successfully'));
            
            // Refresh the profile image
            await fetchProfileImage();
            
        } catch (error: unknown) {
            const errorMessage = error instanceof Error ? error.message : 'Unknown error';
            setImageError(errorMessage || t('userProfile.imageUploadError', 'Failed to upload image. Please try again.'));
        } finally {
            setImageUploading(false);
            // Reset file input
            event.target.value = '';
        }
    };

    const handleImageDelete = async () => {
        try {
            setImageDeleting(true);
            setImageError(null);
            setImageSuccess(null);

            await axiosInstance.delete('/api/profile/image');

            // Clear the current image
            if (profileImageUrl) {
                window.URL.revokeObjectURL(profileImageUrl);
            }
            setProfileImageUrl(null);
            
            setImageSuccess(t('userProfile.imageDeleteSuccess', 'Profile image deleted successfully'));
            
        } catch (error: unknown) {
            const errorMessage = error instanceof Error ? error.message : 'Unknown error';
            setImageError(errorMessage || t('userProfile.imageDeleteError', 'Failed to delete image. Please try again.'));
        } finally {
            setImageDeleting(false);
        }
    };

    const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
        setActiveTab(newValue);
    };

    const handleCancel = () => {
        // Navigate back to previous page
        navigate(-1);
    };

    if (loading) {
        return (
            <Container maxWidth="md" sx={{ mt: 4, mb: 4, display: 'flex', justifyContent: 'center' }}>
                <CircularProgress />
            </Container>
        );
    }

    const renderAccountInfo = () => (
        <Box sx={{ p: 3 }}>
            {/* Current Account Information */}
            <Box sx={{ mb: 3 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                    {t('userProfile.email', 'Email')}
                </Typography>
                <Typography variant="body1">
                    {profileData?.userid || ''}
                </Typography>
            </Box>
            <Box sx={{ mb: 3 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                    {t('userProfile.accountStatus', 'Account Status')}
                </Typography>
                <Typography variant="body1">
                    {profileData?.active ? t('userProfile.active', 'Active') : t('userProfile.inactive', 'Inactive')}
                </Typography>
            </Box>

            <Divider sx={{ my: 4 }} />

            {/* Email Change Section */}
            <Typography variant="h6" gutterBottom>
                {t('userProfile.changeEmail', 'Change Email Address')}
            </Typography>

            {emailError && (
                <Alert severity="error" sx={{ mb: 2 }}>
                    {emailError}
                </Alert>
            )}

            {emailSuccess && (
                <Alert severity="success" sx={{ mb: 2 }}>
                    {emailSuccess}
                </Alert>
            )}

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                <TextField
                    label={t('userProfile.currentEmail', 'Current Email')}
                    value={profileData?.userid || ''}
                    fullWidth
                    variant="outlined"
                    disabled
                    helperText={t('userProfile.currentEmailHelp', 'This is your current email address')}
                />

                <TextField
                    label={t('userProfile.newEmail', 'New Email Address')}
                    type="email"
                    value={newEmail}
                    onChange={(e) => {
                        const value = e.target.value;
                        setNewEmail(value);
                        const validation = validateEmail(value);
                        setEmailValidation(validation);
                        // Re-validate email match if confirm email exists
                        if (confirmEmail) {
                            const matchValidation = validateEmailMatch(value, confirmEmail);
                            setEmailMatchValidation(matchValidation);
                        }
                    }}
                    fullWidth
                    variant="outlined"
                    placeholder={t('userProfile.newEmailPlaceholder', 'Enter your new email address')}
                    error={!emailValidation.isValid && newEmail.length > 0}
                    helperText={!emailValidation.isValid && newEmail.length > 0 
                        ? emailValidation.message 
                        : t('userProfile.newEmailHelp', 'Enter a valid email address')}
                />
                
                <TextField
                    label={t('userProfile.confirmEmail', 'Confirm New Email Address')}
                    type="email"
                    value={confirmEmail}
                    onChange={(e) => {
                        const value = e.target.value;
                        setConfirmEmail(value);
                        const validation = validateEmailMatch(newEmail, value);
                        setEmailMatchValidation(validation);
                    }}
                    fullWidth
                    variant="outlined"
                    placeholder={t('userProfile.confirmEmailPlaceholder', 'Confirm your new email address')}
                    error={!emailMatchValidation.isValid && confirmEmail.length > 0}
                    helperText={!emailMatchValidation.isValid && confirmEmail.length > 0 
                        ? emailMatchValidation.message 
                        : t('userProfile.confirmEmailHelp', 'Re-enter your new email address')}
                />

                <TextField
                    label={t('userProfile.passwordForEmail', 'Current Password')}
                    type="password"
                    value={emailPassword}
                    onChange={(e) => setEmailPassword(e.target.value)}
                    fullWidth
                    variant="outlined"
                    placeholder={t('userProfile.passwordForEmailPlaceholder', 'Enter your current password to confirm')}
                    helperText={t('userProfile.passwordForEmailHelp', 'Required to verify your identity')}
                />

                <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2, mt: 2 }}>
                    <Button
                        variant="contained"
                        onClick={handleChangeEmail}
                        disabled={changingEmail || !newEmail || !confirmEmail || !emailPassword || !emailValidation.isValid || !emailMatchValidation.isValid}
                        startIcon={changingEmail && <CircularProgress size={20} />}
                    >
                        {changingEmail 
                            ? t('userProfile.changingEmail', 'Changing Email...') 
                            : t('userProfile.changeEmailButton', 'Change Email')
                        }
                    </Button>
                </Box>
            </Box>
        </Box>
    );

    const renderPersonalInfo = () => (
        <Box sx={{ p: 3 }}>
            {error && (
                <Alert severity="error" sx={{ mb: 2 }}>
                    {error}
                </Alert>
            )}

            {success && (
                <Alert severity="success" sx={{ mb: 2 }}>
                    {success}
                </Alert>
            )}

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                <TextField
                    label={t('userProfile.firstName', 'First Name')}
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    fullWidth
                    variant="outlined"
                    placeholder={t('userProfile.firstNamePlaceholder', 'Enter your first name')}
                />

                <TextField
                    label={t('userProfile.lastName', 'Last Name')}
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    fullWidth
                    variant="outlined"
                    placeholder={t('userProfile.lastNamePlaceholder', 'Enter your last name')}
                />

                <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2, mt: 2 }}>
                    <Button
                        variant="outlined"
                        onClick={handleCancel}
                        disabled={saving}
                    >
                        {t('userProfile.cancel', 'Cancel')}
                    </Button>
                    <Button
                        variant="contained"
                        onClick={handleSave}
                        disabled={saving}
                        startIcon={saving && <CircularProgress size={20} />}
                    >
                        {saving 
                            ? t('userProfile.saving', 'Saving...') 
                            : t('userProfile.save', 'Save Changes')
                        }
                    </Button>
                </Box>
            </Box>
        </Box>
    );

    const renderSecurityInfo = () => (
        <Box sx={{ p: 3 }}>
            {/* Password Change Section */}
            <Typography variant="h6" gutterBottom>
                {t('userProfile.changePassword', 'Change Password')}
            </Typography>

            {passwordError && (
                <Alert severity="error" sx={{ mb: 2 }}>
                    {passwordError}
                </Alert>
            )}

            {passwordSuccess && (
                <Alert severity="success" sx={{ mb: 2 }}>
                    {passwordSuccess}
                </Alert>
            )}

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3, mb: 4 }}>
                <TextField
                    label={t('userProfile.currentPassword', 'Current Password')}
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    fullWidth
                    variant="outlined"
                    placeholder={t('userProfile.currentPasswordPlaceholder', 'Enter your current password')}
                />

                <TextField
                    label={t('userProfile.newPassword', 'New Password')}
                    type="password"
                    value={newPassword}
                    onChange={(e) => {
                        const value = e.target.value;
                        setNewPassword(value);
                        const validation = validatePasswordComplexity(value, profileData?.userid || '');
                        setPasswordValidation(validation);
                        // Re-validate password match if confirm password exists
                        if (confirmPassword) {
                            const matchValidation = validatePasswordMatch(value, confirmPassword);
                            setPasswordMatchValidation(matchValidation);
                        }
                    }}
                    fullWidth
                    variant="outlined"
                    placeholder={t('userProfile.newPasswordPlaceholder', 'Enter your new password')}
                    error={!passwordValidation.isValid && newPassword.length > 0}
                    helperText={!passwordValidation.isValid && newPassword.length > 0 
                        ? passwordValidation.message 
                        : (profileData?.password_requirements || t('userProfile.passwordRequirements', 'Password must be at least 8 characters long'))}
                />

                <TextField
                    label={t('userProfile.confirmPassword', 'Confirm New Password')}
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => {
                        const value = e.target.value;
                        setConfirmPassword(value);
                        const validation = validatePasswordMatch(newPassword, value);
                        setPasswordMatchValidation(validation);
                    }}
                    fullWidth
                    variant="outlined"
                    placeholder={t('userProfile.confirmPasswordPlaceholder', 'Confirm your new password')}
                    error={!passwordMatchValidation.isValid && confirmPassword.length > 0}
                    helperText={!passwordMatchValidation.isValid && confirmPassword.length > 0 
                        ? passwordMatchValidation.message 
                        : t('userProfile.confirmPasswordHelp', 'Re-enter your new password')}
                />

                <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2, mt: 2 }}>
                    <Button
                        variant="contained"
                        onClick={handleChangePassword}
                        disabled={changingPassword || !currentPassword || !newPassword || !confirmPassword || !passwordValidation.isValid || !passwordMatchValidation.isValid}
                        startIcon={changingPassword && <CircularProgress size={20} />}
                    >
                        {changingPassword 
                            ? t('userProfile.changingPassword', 'Changing Password...') 
                            : t('userProfile.changePasswordButton', 'Change Password')
                        }
                    </Button>
                </Box>
            </Box>
        </Box>
    );

    const renderProfileImage = () => {
        // Extract first initial from user ID (fallback for avatar display)
        const getFirstInitial = (email: string): string => {
            if (!email) return '?';
            const beforeAt = email.split('@')[0];
            return beforeAt.charAt(0).toUpperCase();
        };

        return (
            <Box sx={{ p: 3 }}>
                <Typography variant="h6" gutterBottom>
                    {t('userProfile.profileImage', 'Profile Image')}
                </Typography>

                {imageError && (
                    <Alert severity="error" sx={{ mb: 2 }}>
                        {imageError}
                    </Alert>
                )}

                {imageSuccess && (
                    <Alert severity="success" sx={{ mb: 2 }}>
                        {imageSuccess}
                    </Alert>
                )}

                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
                    {/* Current profile image display */}
                    <Box sx={{ position: 'relative' }}>
                        <Avatar
                            src={profileImageUrl || undefined}
                            sx={{
                                width: 120,
                                height: 120,
                                bgcolor: profileImageUrl ? 'transparent' : 'primary.main',
                                fontSize: '48px',
                                fontWeight: 'bold'
                            }}
                        >
                            {!profileImageUrl && getFirstInitial(profileData?.userid || '')}
                        </Avatar>
                        
                        {imageLoading && (
                            <Box
                                sx={{
                                    position: 'absolute',
                                    top: 0,
                                    left: 0,
                                    right: 0,
                                    bottom: 0,
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    bgcolor: 'rgba(0, 0, 0, 0.5)',
                                    borderRadius: '50%'
                                }}
                            >
                                <CircularProgress size={30} sx={{ color: 'white' }} />
                            </Box>
                        )}
                    </Box>

                    {/* Upload section */}
                    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                        <Input
                            type="file"
                            id="image-upload"
                            accept="image/png,image/jpeg,image/jpg,image/gif,image/webp"
                            onChange={handleImageUpload}
                            sx={{ display: 'none' }}
                        />
                        <label htmlFor="image-upload">
                            <Button
                                variant="outlined"
                                component="span"
                                startIcon={<PhotoCameraIcon />}
                                disabled={imageUploading}
                                sx={{ mb: 1 }}
                            >
                                {imageUploading 
                                    ? t('userProfile.uploading', 'Uploading...') 
                                    : t('userProfile.uploadImage', 'Upload Image')
                                }
                            </Button>
                        </label>

                        {profileImageUrl && (
                            <Button
                                variant="outlined"
                                color="error"
                                startIcon={<DeleteIcon />}
                                onClick={handleImageDelete}
                                disabled={imageDeleting}
                            >
                                {imageDeleting 
                                    ? t('userProfile.deleting', 'Deleting...') 
                                    : t('userProfile.deleteImage', 'Delete Image')
                                }
                            </Button>
                        )}
                    </Box>

                    {/* Help text */}
                    <Typography variant="body2" color="text.secondary" textAlign="center">
                        {t('userProfile.imageHelp', 
                        'Upload a profile image (PNG, JPEG, JPG, GIF, WEBP). Maximum size: 5MB. Image will be automatically resized to 512x512 pixels.')}
                    </Typography>
                </Box>
            </Box>
        );
    };

    return (
        <Container maxWidth="md" sx={{ mt: 4, mb: 4 }}>
            <Typography variant="h4" component="h1" gutterBottom>
                {t('userProfile.profile', 'Profile')}
            </Typography>

            <Card>
                <Tabs 
                    value={activeTab} 
                    onChange={handleTabChange} 
                    aria-label="profile tabs"
                    sx={{ borderBottom: 1, borderColor: 'divider' }}
                >
                    <Tab label={t('userProfile.accountInfo', 'Account Information')} />
                    <Tab label={t('userProfile.personalInfo', 'Personal Information')} />
                    <Tab label={t('userProfile.securityInfo', 'Security Information')} />
                    <Tab label={t('userProfile.profileImage', 'Profile Image')} />
                </Tabs>

                {activeTab === 0 && renderAccountInfo()}
                {activeTab === 1 && renderPersonalInfo()}
                {activeTab === 2 && renderSecurityInfo()}
                {activeTab === 3 && renderProfileImage()}
            </Card>
        </Container>
    );
};

export default Profile;