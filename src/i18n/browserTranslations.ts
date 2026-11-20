/**
 * @file browserTranslations.ts
 * @description @akalin/browser_module - Çok Dilli Çeviri Sözlüğü ve Kancası (i18n)
 */

export const BROWSER_TRANSLATIONS = {
  tr: {
    'browser.title': 'Sanal Tarayıcı & Web Otomasyonu',
    'browser.subtitle': 'AI Ajanları için Hibrit (HTTP + Playwright) sanal tarayıcı oturum havuzu ve web etkileşimi.',
    'browser.sessions': 'Tarayıcı Oturumları',
    'browser.settings': 'Tarayıcı Ayarları',
    'browser.totalSessions': 'Toplam Oturum',
    'browser.busySessions': 'Meşgul (Sayfa Açık)',
    'browser.idleSessions': 'Boşta Bekleyen',
    'browser.httpMode': 'Hızlı HTTP Modu',
    'browser.chromiumMode': 'Docker Chromium',
    'browser.pruneIdle': 'Boşta Olanları Temizle',
    'browser.refresh': 'Yenile',
    'browser.sessionId': 'Oturum ID',
    'browser.conversationId': 'Konuşma ID',
    'browser.currentUrl': 'Mevcut URL',
    'browser.mode': 'Motor Modu',
    'browser.status': 'Durum',
    'browser.requestsServed': 'İstek Sayısı',
    'browser.proxy': 'Proxy',
    'browser.actions': 'İşlemler',
    'browser.terminate': 'Sonlandır',
    'browser.terminateConfirm': 'Bu tarayıcı oturumunu sonlandırmak istediğinize emin misiniz?',
    'browser.noSessions': 'Aktif tarayıcı oturumu bulunmuyor.',
    'browser.status.idle': 'Boşta',
    'browser.status.busy': 'Meşgul',
    'browser.status.closed': 'Kapatıldı',
    'browser.navigate': 'Sayfa Aç',
    'browser.urlPlaceholder': 'https://ornek-site.com...',
  },
  en: {
    'browser.title': 'Virtual Browser & Automation',
    'browser.subtitle': 'Hybrid (HTTP + Playwright) virtual browser pool and web automation for AI agents.',
    'browser.sessions': 'Browser Sessions',
    'browser.settings': 'Browser Settings',
    'browser.totalSessions': 'Total Sessions',
    'browser.busySessions': 'Busy (Page Open)',
    'browser.idleSessions': 'Idle',
    'browser.httpMode': 'Fast HTTP Mode',
    'browser.chromiumMode': 'Docker Chromium',
    'browser.pruneIdle': 'Prune Idle Sessions',
    'browser.refresh': 'Refresh',
    'browser.sessionId': 'Session ID',
    'browser.conversationId': 'Conversation ID',
    'browser.currentUrl': 'Current URL',
    'browser.mode': 'Engine Mode',
    'browser.status': 'Status',
    'browser.requestsServed': 'Requests Served',
    'browser.proxy': 'Proxy',
    'browser.actions': 'Actions',
    'browser.terminate': 'Terminate',
    'browser.terminateConfirm': 'Are you sure you want to terminate this browser session?',
    'browser.noSessions': 'No active browser sessions found.',
    'browser.status.idle': 'Idle',
    'browser.status.busy': 'Busy',
    'browser.status.closed': 'Closed',
    'browser.navigate': 'Navigate',
    'browser.urlPlaceholder': 'https://example.com...',
  },
};

export type SupportedBrowserLocale = 'tr' | 'en';

export function createBrowserTranslator(locale: SupportedBrowserLocale = 'tr') {
  const dict = BROWSER_TRANSLATIONS[locale] || BROWSER_TRANSLATIONS.tr;
  return (key: string, fallback?: string): string => {
    return (dict as Record<string, string>)[key] || fallback || key;
  };
}

export function useBrowserTranslation(locale: SupportedBrowserLocale = 'tr') {
  const t = createBrowserTranslator(locale);
  return { t, locale };
}
