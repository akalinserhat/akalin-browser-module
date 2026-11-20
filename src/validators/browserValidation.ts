/**
 * @file browserValidation.ts
 * @description @akalin/browser_module - Saf Doğrulayıcılar (Zero Inline Validation Policy)
 */

import type { BrowserSettingsFormState } from '../defaults/browserDefaultValue';

export function validateBrowserSettingField(
  field: keyof BrowserSettingsFormState,
  value: any
): string | null {
  switch (field) {
    case 'max_concurrent_browsers': {
      const num = Number(value);
      if (isNaN(num) || num < 1 || num > 64) {
        return 'Maksimum eşzamanlı oturum sayısı 1 ile 64 arasında olmalıdır.';
      }
      return null;
    }
    case 'session_ttl_sec': {
      const num = Number(value);
      if (isNaN(num) || num < 30 || num > 3600) {
        return 'Oturum TTL süresi 30 ile 3600 saniye arasında olmalıdır.';
      }
      return null;
    }
    case 'snapshot_max_chars': {
      const num = Number(value);
      if (isNaN(num) || num < 500 || num > 50000) {
        return 'Snapshot karakter bütçesi 500 ile 50.000 arasında olmalıdır.';
      }
      return null;
    }
    case 'proxy_service_url': {
      const str = String(value || '').trim();
      if (str && !str.startsWith('http://') && !str.startsWith('https://')) {
        return 'Proxy servis URL adresi http:// veya https:// ile başlamalıdır.';
      }
      return null;
    }
    default:
      return null;
  }
}

export function validateBrowserSettingsForm(
  data: BrowserSettingsFormState
): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const key of Object.keys(data) as (keyof BrowserSettingsFormState)[]) {
    const err = validateBrowserSettingField(key, data[key]);
    if (err) errors[key] = err;
  }
  return errors;
}
