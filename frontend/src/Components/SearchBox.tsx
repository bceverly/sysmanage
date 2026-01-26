import React from 'react';
import { 
  Box, 
  TextField, 
  FormControl, 
  InputLabel, 
  Select, 
  MenuItem, 
  InputAdornment 
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import { useTranslation } from 'react-i18next';

interface SearchColumn {
  field: string;
  label: string;
}

interface SearchBoxProps {
  searchTerm: string;
  setSearchTerm: (term: string) => void;
  searchColumn: string;
  setSearchColumn: (column: string) => void;
  columns: SearchColumn[];
  placeholder?: string;
  inline?: boolean;
}

const SearchBox: React.FC<SearchBoxProps> = ({
  searchTerm,
  setSearchTerm,
  searchColumn,
  setSearchColumn,
  columns,
  placeholder,
  inline = false
}) => {
  const { t } = useTranslation();

  const content = (
    <>
      <TextField
        size="small"
        label={placeholder || t('search.searchTerm', 'Search')}
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
        slotProps={{
          input: {
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
          },
        }}
        sx={{ minWidth: 250, flexGrow: 1 }}
      />
      
      <FormControl size="small" sx={{ minWidth: 150 }}>
        <InputLabel>{t('search.searchColumn', 'Search in')}</InputLabel>
        <Select
          value={searchColumn}
          label={t('search.searchColumn', 'Search in')}
          onChange={(e) => setSearchColumn(e.target.value)}
        >
          {columns.map((column) => (
            <MenuItem key={column.field} value={column.field}>
              {column.label}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
    </>
  );

  if (inline) {
    return content;
  }

  return (
    <Box sx={{ 
      display: 'flex', 
      alignItems: 'center', 
      gap: 2, 
      mb: 2,
      p: 2,
      bgcolor: 'background.paper',
      borderRadius: 1,
      boxShadow: 1
    }}>
      {content}
    </Box>
  );
};

export default SearchBox;