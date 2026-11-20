/**
 * @file browserDefaultValue.ts
 * @description @akalin/browser_module - Varsayılan Form ve Ayar Değerleri
 */

export interface BrowserSettingsFormState {
  max_concurrent_browsers: number;
  session_ttl_sec: number;
  snapshot_max_chars: number;
  use_proxy_by_default: boolean;
  proxy_service_url: string;
  allow_private_networks: boolean;
  user_agent: string;
}

export const DEFAULT_BROWSER_SETTINGS: BrowserSettingsFormState = {
  max_concurrent_browsers: 16,
  session_ttl_sec: 300,
  snapshot_max_chars: 8000,
  use_proxy_by_default: true,
  proxy_service_url: 'http://localhost:8001',
  allow_private_networks: false,
  user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 AkalinBrowser/1.0',
};

export function getBrowserSettingsDefaultValues(overrides?: Partial<BrowserSettingsFormState>): BrowserSettingsFormState {
  return {
    ...DEFAULT_BROWSER_SETTINGS,
    ...(overrides || {}),
  };
}
