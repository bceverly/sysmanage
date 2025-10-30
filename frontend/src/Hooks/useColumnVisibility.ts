import { useState, useEffect, useCallback } from 'react';
import {
  getColumnPreferences,
  updateColumnPreferences,
  deleteColumnPreferences,
} from '../Services/columnPreferencesService';

export const useColumnVisibility = (gridIdentifier: string) => {
  const [hiddenColumns, setHiddenColumns] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  // Load preferences on mount
  useEffect(() => {
    const loadPreferences = async () => {
      try {
        const preferences = await getColumnPreferences(gridIdentifier);
        if (preferences && preferences.hidden_columns) {
          setHiddenColumns(preferences.hidden_columns);
        }
      } catch (error) {
        console.error('Error loading column preferences:', error);
        // If there's an error (like 401), just use default (no hidden columns)
      } finally {
        setLoading(false);
      }
    };

    loadPreferences();
  }, [gridIdentifier]);

  // Save preferences when they change
  const savePreferences = useCallback(
    async (newHiddenColumns: string[]) => {
      // Update state immediately for responsive UI
      setHiddenColumns(newHiddenColumns);

      try {
        await updateColumnPreferences(gridIdentifier, newHiddenColumns);
      } catch (error) {
        console.error('Error saving column preferences:', error);
        // Don't revert on error - keep the UI change
      }
    },
    [gridIdentifier]
  );

  // Reset to defaults
  const resetPreferences = useCallback(async () => {
    try {
      await deleteColumnPreferences(gridIdentifier);
      setHiddenColumns([]);
    } catch (error) {
      console.error('Error resetting column preferences:', error);
    }
  }, [gridIdentifier]);

  // Get column visibility model for MUI DataGrid
  const getColumnVisibilityModel = useCallback(() => {
    const model: { [key: string]: boolean } = {};
    hiddenColumns.forEach((field) => {
      // Safely set property to prevent prototype pollution
      if (typeof field === 'string' && field !== '__proto__' && field !== 'constructor' && field !== 'prototype') {
        // eslint-disable-next-line security/detect-object-injection
        model[field] = false; // nosemgrep: detect-object-injection
      }
    });
    return model;
  }, [hiddenColumns]);

  return {
    hiddenColumns,
    setHiddenColumns: savePreferences,
    resetPreferences,
    getColumnVisibilityModel,
    loading,
  };
};
