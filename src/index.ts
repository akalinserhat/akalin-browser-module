/**
 * @file index.ts
 * @description @akalin/browser_module - Bağımsız Sanal Tarayıcı ve AI Web Otomasyon Modülü Ana Giriş Noktası.
 * @akalin/module_core (`IModuleDefinition` / `ModuleRegistry`) ve @akalin/module_management ile %100 uyumludur.
 */

// 1. Sözleşme Tipleri
export * from './types';

// 2. Varsayılan Değerler
export {
  DEFAULT_BROWSER_SETTINGS,
  getBrowserSettingsDefaultValues,
  type BrowserSettingsFormState,
} from './defaults/browserDefaultValue';

// 3. Saf Doğrulayıcılar (Pure Validators)
export {
  validateBrowserSettingField,
  validateBrowserSettingsForm,
} from './validators/browserValidation';

// 4. Odaklanma Kancası ve i18n
export { useBrowserAutoFocus } from './hooks/useBrowserAutoFocus';
export {
  BROWSER_TRANSLATIONS,
  createBrowserTranslator,
  useBrowserTranslation,
  type SupportedBrowserLocale,
} from './i18n/browserTranslations';

// 5. Servis Adaptörleri ve Context
export {
  RestBrowserServiceAdapter,
  BrowserContext,
  BrowserProvider,
  useBrowserModule,
  type BrowserContextValue,
  type BrowserProviderProps,
} from './adapters/BrowserServiceContext';

// 6. Sayfalar ve Harici Düğüm Ayar Bileşenleri
export {
  BrowserSessionsPage,
} from './pages/BrowserSessionsPage';
export {
  BrowserSessionsPageSettingsForExternal,
  type BrowserExternalSettingsValue,
  type BrowserSessionsPageSettingsForExternalProps,
} from './pages/BrowserSessionsPageSettingsForExternal';

// 7. Modül Fabrikası
export {
  createBrowserModule,
  BrowserModule,
  default,
} from './createBrowserModule';
