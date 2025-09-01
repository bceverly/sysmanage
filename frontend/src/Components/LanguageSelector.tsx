import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MenuItem, Select, FormControl, SelectChangeEvent } from '@mui/material';

const LanguageSelector: React.FC = () => {
  const { i18n } = useTranslation();
  const [currentLanguage, setCurrentLanguage] = useState('');

  const handleLanguageChange = (event: SelectChangeEvent<string>) => {
    const language = event.target.value;
    i18n.changeLanguage(language);
    setCurrentLanguage(language);
  };

  // Map browser language codes to our supported languages
  const mapBrowserLanguage = (browserLang: string): string => {
    const langMap: { [key: string]: string } = {
      'en': 'en',
      'en-US': 'en',
      'en-GB': 'en',
      'es': 'es',
      'es-ES': 'es',
      'es-MX': 'es',
      'fr': 'fr',
      'fr-FR': 'fr',
      'fr-CA': 'fr',
      'de': 'de',
      'de-DE': 'de',
      'it': 'it',
      'it-IT': 'it',
      'pt': 'pt',
      'pt-BR': 'pt',
      'pt-PT': 'pt',
      'nl': 'nl',
      'nl-NL': 'nl',
      'ja': 'ja',
      'ja-JP': 'ja',
      'zh': 'zh_CN',
      'zh-CN': 'zh_CN',
      'zh-Hans': 'zh_CN',
      'zh-TW': 'zh_TW',
      'zh-Hant': 'zh_TW',
      'ko': 'ko',
      'ko-KR': 'ko',
      'ru': 'ru',
      'ru-RU': 'ru',
      'ar': 'ar',
      'ar-SA': 'ar',
      'ar-AE': 'ar',
      'ar-EG': 'ar',
      'hi': 'hi',
      'hi-IN': 'hi'
    };
    
    return langMap[browserLang] || 'en';
  };

  useEffect(() => {
    // Initialize language based on i18n detection
    const initializeLanguage = () => {
      let detectedLang = i18n.language;
      
      // If no language detected yet or it's a generic code, try to detect from browser
      if (!detectedLang || detectedLang === 'en' || detectedLang.length === 0) {
        const browserLangs = window.navigator.languages || [window.navigator.language];
        for (const browserLang of browserLangs) {
          const mappedLang = mapBrowserLanguage(browserLang);
          if (mappedLang && mappedLang !== 'en') {
            detectedLang = mappedLang;
            break;
          }
        }
      }
      
      // Ensure the detected language is supported
      const supportedLangs = ['en', 'es', 'fr', 'de', 'it', 'pt', 'nl', 'ja', 'zh_CN', 'zh_TW', 'ko', 'ru', 'ar', 'hi'];
      const finalLang = supportedLangs.includes(detectedLang) ? detectedLang : 'en';
      
      setCurrentLanguage(finalLang);
      
      // Only change language if it's different from current
      if (i18n.language !== finalLang) {
        i18n.changeLanguage(finalLang);
      }
    };

    // Wait a bit for i18n to initialize if needed
    if (i18n.isInitialized) {
      initializeLanguage();
    } else {
      i18n.on('initialized', initializeLanguage);
      return () => i18n.off('initialized', initializeLanguage);
    }
  }, [i18n]);

  // Update local state when language changes externally
  useEffect(() => {
    const handleLanguageChanged = (lng: string) => {
      setCurrentLanguage(lng);
    };
    
    i18n.on('languageChanged', handleLanguageChanged);
    return () => i18n.off('languageChanged', handleLanguageChanged);
  }, [i18n]);

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
    { code: 'zh_TW', name: '繁體中文' },
    { code: 'ko', name: '한국어' },
    { code: 'ru', name: 'Русский' },
    { code: 'ar', name: 'العربية' },
    { code: 'hi', name: 'हिन्दी' }
  ];

  return (
    <FormControl size="small" sx={{ minWidth: 120 }}>
      <Select
        value={currentLanguage}
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