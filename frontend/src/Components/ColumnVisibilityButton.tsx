/* global HTMLButtonElement */
import React, { useState } from 'react';
import {
  IconButton,
  Popover,
  Box,
  Typography,
  FormControlLabel,
  Checkbox,
  Button,
  Stack,
  Divider,
} from '@mui/material';
import ViewColumnIcon from '@mui/icons-material/ViewColumn';
import { useTranslation } from 'react-i18next';

interface ColumnVisibilityButtonProps {
  columns: Array<{ field: string; headerName: string }>;
  hiddenColumns: string[];
  onColumnsChange: (hiddenColumns: string[]) => void;
  onReset?: () => void;
}

const ColumnVisibilityButton: React.FC<ColumnVisibilityButtonProps> = ({
  columns,
  hiddenColumns,
  onColumnsChange,
  onReset,
}) => {
  const { t } = useTranslation();
  const [anchorEl, setAnchorEl] = useState<HTMLButtonElement | null>(null);

  const handleClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  const handleToggleColumn = (field: string) => {
    const isHidden = hiddenColumns.includes(field);
    if (isHidden) {
      // Show the column
      onColumnsChange(hiddenColumns.filter((col) => col !== field));
    } else {
      // Hide the column
      onColumnsChange([...hiddenColumns, field]);
    }
  };

  const handleSelectAll = () => {
    onColumnsChange([]);
  };

  const handleDeselectAll = () => {
    onColumnsChange(columns.map((col) => col.field));
  };

  const handleReset = () => {
    if (onReset) {
      onReset();
    }
    handleClose();
  };

  const open = Boolean(anchorEl);
  const id = open ? 'column-visibility-popover' : undefined;

  return (
    <>
      <IconButton
        aria-describedby={id}
        onClick={handleClick}
        size="small"
        title={t('dataGrid.columnVisibility', 'Column Visibility')}
      >
        <ViewColumnIcon />
      </IconButton>
      <Popover
        id={id}
        open={open}
        anchorEl={anchorEl}
        onClose={handleClose}
        anchorOrigin={{
          vertical: 'bottom',
          horizontal: 'right',
        }}
        transformOrigin={{
          vertical: 'top',
          horizontal: 'right',
        }}
      >
        <Box sx={{ p: 2, minWidth: 250, maxWidth: 350 }}>
          <Typography variant="subtitle2" gutterBottom>
            {t('dataGrid.columnVisibility', 'Column Visibility')}
          </Typography>
          <Divider sx={{ my: 1 }} />

          <Box sx={{ maxHeight: 400, overflowY: 'auto', mb: 2 }}>
            {columns.map((column) => (
              <FormControlLabel
                key={column.field}
                control={
                  <Checkbox
                    checked={!hiddenColumns.includes(column.field)}
                    onChange={() => handleToggleColumn(column.field)}
                    size="small"
                  />
                }
                label={column.headerName}
                sx={{ display: 'block', mb: 0.5 }}
              />
            ))}
          </Box>

          <Divider sx={{ my: 1 }} />

          <Stack direction="row" spacing={1} justifyContent="space-between">
            <Button size="small" onClick={handleSelectAll}>
              {t('dataGrid.showAll', 'Show All')}
            </Button>
            <Button size="small" onClick={handleDeselectAll}>
              {t('dataGrid.hideAll', 'Hide All')}
            </Button>
            {onReset && (
              <Button size="small" onClick={handleReset} color="secondary">
                {t('dataGrid.reset', 'Reset')}
              </Button>
            )}
          </Stack>
        </Box>
      </Popover>
    </>
  );
};

export default ColumnVisibilityButton;
