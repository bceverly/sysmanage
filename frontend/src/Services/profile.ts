/**
 * API service for user profile management
 */

import axiosInstance from './api';

export interface ProfileData {
    userid: string;
    first_name?: string;
    last_name?: string;
    active: boolean;
    password_requirements: string;
}

export interface ProfileUpdateData {
    first_name?: string;
    last_name?: string;
}

export interface PasswordChangeData {
    current_password: string;
    new_password: string;
    confirm_password: string;
}

export interface PasswordChangeResponse {
    message: string;
}

export const getProfile = async (): Promise<ProfileData> => {
    const response = await axiosInstance.get('/profile');
    return response.data;
};

export const updateProfile = async (profileData: ProfileUpdateData): Promise<ProfileData> => {
    const response = await axiosInstance.put('/profile', profileData);
    return response.data;
};

export const changePassword = async (passwordData: PasswordChangeData): Promise<PasswordChangeResponse> => {
    const response = await axiosInstance.put('/profile/password', passwordData);
    return response.data;
};