import axiosInstance from './api';

export interface ColumnPreference {
  id: string;
  user_id: string;
  grid_identifier: string;
  hidden_columns: string[];
  created_at: string;
  updated_at: string;
}

export const getColumnPreferences = async (gridIdentifier: string): Promise<ColumnPreference | null> => {
  const response = await axiosInstance.get<ColumnPreference | null>(
    `/api/user-preferences/column-preferences/${gridIdentifier}`
  );
  return response.data;
};

export const updateColumnPreferences = async (
  gridIdentifier: string,
  hiddenColumns: string[]
): Promise<ColumnPreference> => {
  const response = await axiosInstance.put<ColumnPreference>(
    '/api/user-preferences/column-preferences',
    {
      grid_identifier: gridIdentifier,
      hidden_columns: hiddenColumns,
    }
  );
  return response.data;
};

export const deleteColumnPreferences = async (gridIdentifier: string): Promise<void> => {
  await axiosInstance.delete(`/api/user-preferences/column-preferences/${gridIdentifier}`);
};
