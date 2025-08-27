import React from 'react';
import { useTranslation } from 'react-i18next';
import { MenuItem, Select, FormControl, SelectChangeEvent } from '@mui/material';

const LanguageSelector: React.FC = () => {
  const { i18n } = useTranslation();

  const handleLanguageChange = (event: SelectChangeEvent<string>) => {
    const language = event.target.value;
    i18n.changeLanguage(language);
  };

  const languages = [
    { code: 'en', name: 'English' },
    { code: 'es', name: 'Español' },
    { code: 'fr', name: 'Français' },
    { code: 'de', name: 'Deutsch' },
    { code: 'it', name: 'Italiano' },
    { code: 'pt', name: 'Português' },
    { code: 'nl', name: 'Nederlands' },
    { code: 'ja', name: '日本語' },
    { code: 'zh_CN', name: '简体中文' },
    { code: 'ko', name: '한국어' },
    { code: 'ru', name: 'Русский' }
  ];

  return (
    <FormControl size="small" sx={{ minWidth: 120 }}>
      <Select
        value={i18n.language}
        onChange={handleLanguageChange}
        displayEmpty
        sx={{ 
          color: 'white',
          '.MuiSelect-icon': { color: 'white' },
          '.MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255, 255, 255, 0.3)' },
          '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255, 255, 255, 0.5)' },
          '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: '#2196f3' }
        }}
      >
        {languages.map((lang) => (
          <MenuItem key={lang.code} value={lang.code}>
            {lang.name}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
};

export default LanguageSelector;