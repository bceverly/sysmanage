/**
 * Secure cookie utilities for handling browser cookies safely
 */

interface CookieOptions {
  expires?: Date;
  maxAge?: number; // in seconds
  path?: string;
  domain?: string;
  secure?: boolean;
  sameSite?: 'strict' | 'lax' | 'none';
  httpOnly?: boolean;
}

/**
 * Set a secure cookie
 * @param name - Cookie name
 * @param value - Cookie value
 * @param options - Cookie options
 */
export const setSecureCookie = (
  name: string,
  value: string,
  options: CookieOptions = {}
): void => {
  const defaults: CookieOptions = {
    path: '/',
    secure: window.location.protocol === 'https:',
    sameSite: 'strict',
    maxAge: 30 * 24 * 60 * 60 // 30 days in seconds
  };

  const cookieOptions = { ...defaults, ...options };

  let cookieString = `${encodeURIComponent(name)}=${encodeURIComponent(value)}`;

  if (cookieOptions.expires) {
    cookieString += `; expires=${cookieOptions.expires.toUTCString()}`;
  }

  if (cookieOptions.maxAge) {
    cookieString += `; max-age=${cookieOptions.maxAge}`;
  }

  if (cookieOptions.path) {
    cookieString += `; path=${cookieOptions.path}`;
  }

  if (cookieOptions.domain) {
    cookieString += `; domain=${cookieOptions.domain}`;
  }

  if (cookieOptions.secure) {
    cookieString += '; secure';
  }

  if (cookieOptions.sameSite) {
    cookieString += `; samesite=${cookieOptions.sameSite}`;
  }

  if (cookieOptions.httpOnly) {
    cookieString += '; httponly';
  }

  document.cookie = cookieString;
};

/**
 * Get a cookie value by name
 * @param name - Cookie name
 * @returns Cookie value or null if not found
 */
export const getCookie = (name: string): string | null => {
  const encodedName = encodeURIComponent(name);
  const cookies = document.cookie.split(';');

  for (const cookie of cookies) {
    const [cookieName, cookieValue] = cookie.trim().split('=');
    if (cookieName === encodedName) {
      return cookieValue ? decodeURIComponent(cookieValue) : '';
    }
  }

  return null;
};

/**
 * Delete a cookie
 * @param name - Cookie name
 * @param options - Cookie options (path and domain should match the original cookie)
 */
export const deleteCookie = (
  name: string,
  options: Pick<CookieOptions, 'path' | 'domain'> = {}
): void => {
  const deleteOptions: CookieOptions = {
    ...options,
    expires: new Date(0),
    maxAge: 0
  };

  setSecureCookie(name, '', deleteOptions);
};

/**
 * Check if cookies are enabled in the browser
 * @returns True if cookies are enabled
 */
export const areCookiesEnabled = (): boolean => {
  try {
    const testCookie = '__cookie_test__';
    setSecureCookie(testCookie, 'test', { maxAge: 1 });
    const enabled = getCookie(testCookie) === 'test';
    deleteCookie(testCookie);
    return enabled;
  } catch {
    return false;
  }
};

// Constants for Remember Me functionality
export const REMEMBER_ME_COOKIE_NAME = 'sysmanage_remember_email';
export const REMEMBER_ME_EXPIRY_DAYS = 30;

/**
 * Save email for Remember Me functionality
 * @param email - User's email address
 */
export const saveRememberedEmail = (email: string): void => {
  if (!email || !areCookiesEnabled()) {
    return;
  }

  setSecureCookie(REMEMBER_ME_COOKIE_NAME, email, {
    maxAge: REMEMBER_ME_EXPIRY_DAYS * 24 * 60 * 60,
    secure: window.location.protocol === 'https:',
    sameSite: 'strict'
  });
};

/**
 * Get remembered email address
 * @returns Remembered email or null
 */
export const getRememberedEmail = (): string | null => {
  return getCookie(REMEMBER_ME_COOKIE_NAME);
};

/**
 * Clear remembered email
 */
export const clearRememberedEmail = (): void => {
  deleteCookie(REMEMBER_ME_COOKIE_NAME);
};