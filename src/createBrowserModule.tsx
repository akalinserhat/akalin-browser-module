/**
 * @file createBrowserModule.tsx
 * @description @akalin/browser_module - Modül Fabrikası.
 * @akalin/module_core (`IModuleDefinition` & `ModuleRegistry`) ve @akalin/module_management ile %100 uyumludur.
 */

import React, { lazy, Suspense } from 'react';
import { Globe, MonitorCheck, Settings } from 'lucide-react';
import type { IModuleDefinition } from '@akalin/module_core';
import type { BrowserModuleOptions } from './types';
import {
  BrowserProvider,
  RestBrowserServiceAdapter,
} from './adapters/BrowserServiceContext';
import { BrowserSessionsPage } from './pages/BrowserSessionsPage';
import { BrowserSessionsPageSettingsForExternal } from './pages/BrowserSessionsPageSettingsForExternal';

const LazyBrowserSessionsPage = lazy(() => import('./pages/BrowserSessionsPage'));
const LazyBrowserSessionsPageSettingsForExternal = lazy(
  () => import('./pages/BrowserSessionsPageSettingsForExternal')
);

export function createBrowserModule(
  options?: BrowserModuleOptions
): IModuleDefinition {
  const id = options?.id || 'browser-module';
  const baseRoute = (options?.baseRoute || '/browser').replace(/\/$/, '');
  const adapter = options?.adapter || new RestBrowserServiceAdapter();

  const withProvider = (Component: React.ComponentType<any>, props: any = {}) => {
    return (
      <BrowserProvider adapter={adapter} onNotify={options?.onNotify}>
        <Suspense fallback={<div className="p-16 text-muted">Yükleniyor...</div>}>
          <Component {...props} />
        </Suspense>
      </BrowserProvider>
    );
  };

  return {
    id,
    aliases: ['browser', 'virtual_browser', 'sanal_tarayici', 'playwright_browser', 'browser_module'],
    title: options?.title || 'Sanal Tarayıcı & Web Otomasyonu',
    name: options?.title || 'Sanal Tarayıcı & Web Otomasyonu',
    description:
      'AI Ajanları için Playwright & HTTP hibrit sanal tarayıcı, oturum havuzu ve web otomasyon modülü.',
    version: '1.0.0',
    permissionPrefix: 'browser',
    icon: <Globe size={20} />,
    iconName: 'Globe',
    order: options?.order ?? 55,
    isCore: true,
    defaultActive: true,

    routes: [
      {
        path: `${baseRoute}/sessions`,
        element: withProvider(LazyBrowserSessionsPage),
        title: 'Sanal Tarayıcı — Oturumlar',
        requiredPermissions: ['browser.sessions.view'],
      },
      {
        path: `${baseRoute}/settings`,
        element: withProvider(LazyBrowserSessionsPageSettingsForExternal),
        title: 'Sanal Tarayıcı — Ayarlar',
        requiredPermissions: ['browser.settings.manage'],
      },
    ],

    menuItems: [
      {
        id: 'browser-module-root',
        label: 'Sanal Tarayıcı',
        icon: <Globe size={20} />,
        order: options?.order ?? 55,
        isDropdown: true,
        children: [
          {
            id: 'browser-menu-sessions',
            label: 'Oturumlar',
            path: `${baseRoute}/sessions`,
            icon: <MonitorCheck size={18} />,
            requiredPermissions: ['browser.sessions.view'],
          },
          {
            id: 'browser-menu-settings',
            label: 'Tarayıcı Ayarları',
            path: `${baseRoute}/settings`,
            icon: <Settings size={18} />,
            requiredPermissions: ['browser.settings.manage'],
          },
        ],
      },
    ],

    settingsModules: [
      {
        id: 'browser-settings',
        name: 'Sanal Tarayıcı & Web Ayarları',
        desc: 'AI Ajanlarının web gezinme yetenekleri, Playwright Docker eşzamanlılık sınırı ve proxy ayarları.',
        icon: <Globe size={22} />,
        order: 55,
        component: withProvider(LazyBrowserSessionsPageSettingsForExternal),
      },
    ],

    components: {
      BrowserSessionsPage: LazyBrowserSessionsPage,
      BrowserSessionsPageSettingsForExternal: LazyBrowserSessionsPageSettingsForExternal,
      BrowserSessionsView: LazyBrowserSessionsPage,
    },

    lists: [
      {
        id: 'browser_sessions',
        category: 'liste',
        titleKey: 'browser.sessions',
        title: 'Tarayıcı Oturumları',
        route: `${baseRoute}/sessions`,
        icon: <MonitorCheck size={18} />,
        iconName: 'MonitorCheck',
        hasExternalSettings: true,
        externalSettingsComponent: BrowserSessionsPageSettingsForExternal,
        externalSettingsRoute: `${baseRoute}/settings`,
        useStandardCrud: false,
      },
    ],

    permissions: [
      {
        key: 'browser.sessions.view',
        name: 'Tarayıcı Oturumlarını Görüntüleme',
        description: 'Aktif sanal tarayıcı oturumlarını ve metriklerini izleyebilir.',
        group: 'Sanal Tarayıcı',
      },
      {
        key: 'browser.sessions.manage',
        name: 'Tarayıcı Oturumlarını Yönetme',
        description: 'Tarayıcı oturumlarını başlatabilir ve sonlandırabilir.',
        group: 'Sanal Tarayıcı',
      },
      {
        key: 'browser.settings.manage',
        name: 'Tarayıcı Ayarlarını Düzenleme',
        description: 'Sanal tarayıcı ve Docker havuz ayarlarını değiştirebilir.',
        group: 'Sanal Tarayıcı',
      },
      {
        key: 'browser.execute',
        name: 'Tarayıcı Eylemlerini Yürütme',
        description: 'AI ajanları veya API üzerinden web sayfalarında gezinebilir, form doldurabilir.',
        group: 'Sanal Tarayıcı',
      },
    ],
  };
}

export const BrowserModule = createBrowserModule();
export default BrowserModule;
