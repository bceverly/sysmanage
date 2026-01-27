import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

// Initialize i18n for tests
i18n
  .use(initReactI18next)
  .init({
    lng: 'en',
    fallbackLng: 'en',
    debug: false,
    interpolation: {
      escapeValue: false,
    },
    resources: {
      en: {
        translation: {
          nav: {
            dashboard: 'Dashboard',
            hosts: 'Hosts',
            users: 'Users',
            logout: 'Logout'
          },
          login: {
            title: 'Login to SysManage',
            username: 'Email Address',
            password: 'Password', // NOSONAR - i18n translation key for UI label, not a password
            submit: 'Login',
            error: 'Invalid username or password'
          },
          dashboard: {
            title: 'Dashboard',
            welcome: 'Welcome to SysManage',
            hosts: 'Hosts',
            totalUsers: 'Total Users',
            systemHealth: 'System Health'
          },
          hosts: {
            fqdn: 'FQDN',
            ipv4: 'IPv4 Address',
            ipv6: 'IPv6 Address'
          },
          users: {
            email: 'Email'
          },
          common: {
            delete: 'Delete',
            selected: 'Selected',
            rowsPerPage: 'Rows per page',
            of: 'of',
            page: 'Page',
            goToPage: 'Go to page',
            firstPage: 'First page',
            lastPage: 'Last page',
            nextPage: 'Next page',
            previousPage: 'Previous page'
          },
          app: {
            title: 'SysManage'
          }
        }
      }
    }
  });

export default i18n;