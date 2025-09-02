import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
    Container,
    Typography,
    Card,
    CardContent,
    TextField,
    Button,
    Alert,
    Box,
    Divider,
    CircularProgress
} from '@mui/material';
import { getProfile, updateProfile, ProfileData, ProfileUpdateData } from '../Services/profile';

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

    useEffect(() => {
        const loadProfile = async () => {
            try {
                setLoading(true);
                const data = await getProfile();
                setProfileData(data);
                setFirstName(data.first_name || '');
                setLastName(data.last_name || '');
                setError(null);
            } catch {
                setError(t('userProfile.loadError', 'Failed to load profile data'));
            } finally {
                setLoading(false);
            }
        };

        loadProfile();
    }, [t]);

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

    return (
        <Container maxWidth="md" sx={{ mt: 4, mb: 4 }}>
            <Typography variant="h4" component="h1" gutterBottom>
                {t('userProfile.profile', 'Profile')}
            </Typography>

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

            <Card>
                <CardContent>
                    <Typography variant="h6" gutterBottom>
                        {t('userProfile.accountInfo', 'Account Information')}
                    </Typography>
                    
                    <Box sx={{ mb: 3 }}>
                        <Typography variant="body2" color="text.secondary" gutterBottom>
                            {t('userProfile.email', 'Email')}
                        </Typography>
                        <Typography variant="body1">
                            {profileData?.userid || ''}
                        </Typography>
                    </Box>

                    <Divider sx={{ my: 3 }} />

                    <Typography variant="h6" gutterBottom>
                        {t('userProfile.personalInfo', 'Personal Information')}
                    </Typography>

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
                </CardContent>
            </Card>
        </Container>
    );
};

export default Profile;