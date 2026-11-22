/**
 * @file BrowserSessionsPageSettingsForExternal.tsx
 * @description @akalin/browser_module - Sanal Tarayıcı & Web Otomasyonu Sistem ve Düğüm Ayar Sayfası (hasExternalSettings = true)
 *
 * Başlıca Özellikler:
 * - BaseCardPage mimarisi ile tek, temiz sayfa başlığı sunar (hasOwnLayout = true ile BaseSystemPage çift başlık üretmez).
 * - Sıfır alt düğme kuralı: Tüm eylemler (Kaydet, Profiller, Sıfırla) üst ActionMenu üzerinden yönetilir.
 * - PolicySettingCard ile MD3 standartlarına uygun ayar kartları listeler.
 * - Değişiklikleri localStorage ve opsiyonel Gateway API ile kalıcı tutar.
 */

import React, { useState, useMemo, useCallback } from 'react';
import {
  Globe,
  Monitor,
  Shield,
  Clock,
  Zap,
  RefreshCw,
  Save,
  RotateCcw,
} from 'lucide-react';
import { toast } from 'react-hot-toast';
import {
  ActionMenu,
  type ActionMenuItem,
  BaseCardPage,
  BaseDropdownSecici,
  BaseSwitch,
  PolicySettingCard,
  TamsayiInput,
  type DropdownOption,
} from '@akalin/ui';
import { useBrowserTranslation } from '../i18n/browserTranslations';

export interface BrowserExternalSettingsValue {
  defaultMode: 'http' | 'chromium';
  useProxyByDefault: boolean;
  maxConcurrentBrowsers: number;
  keepAliveTtlSec: number;
  enableStealth: boolean;
  autoPruneOnOpen: boolean;
}

export const DEFAULT_BROWSER_SETTINGS: BrowserExternalSettingsValue = {
  defaultMode: 'chromium',
  useProxyByDefault: true,
  maxConcurrentBrowsers: 16,
  keepAliveTtlSec: 300,
  enableStealth: true,
  autoPruneOnOpen: true,
};

const STORAGE_KEY = 'thinkport_browser_settings_v1';

export interface BrowserSessionsPageSettingsForExternalProps {
  value?: Partial<BrowserExternalSettingsValue>;
  onChange?: (next: BrowserExternalSettingsValue) => void;
  onSave?: (next: BrowserExternalSettingsValue) => void;
  onClose?: () => void;
  inModal?: boolean;
}

export const BrowserSessionsPageSettingsForExternal: React.FC<
  BrowserSessionsPageSettingsForExternalProps
> = ({ value, onChange, onSave, onClose, inModal = false }) => {
  const { t } = useBrowserTranslation();

  const [formState, setFormState] = useState<BrowserExternalSettingsValue>(() => {
    let saved: Partial<BrowserExternalSettingsValue> = {};
    try {
      if (typeof window !== 'undefined') {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (raw) saved = JSON.parse(raw);
      }
    } catch {
      // Fallback
    }
    return {
      ...DEFAULT_BROWSER_SETTINGS,
      ...saved,
      ...(value || {}),
    };
  });

  const [isSaving, setIsSaving] = useState(false);

  const modeOptions = useMemo<DropdownOption[]>(
    () => [
      { id: 'chromium', value: 'chromium', label: 'Docker Headless Chromium (Tam Sanal Tarayıcı / JS & DOM)' },
      { id: 'http', value: 'http', label: 'Hafif HTTP İstemcisi (Yüksek Hız / Statik HTML)' },
    ],
    []
  );

  const updateState = useCallback(
    (patch: Partial<BrowserExternalSettingsValue>) => {
      setFormState((prev) => {
        const next = { ...prev, ...patch };
        if (onChange) onChange(next);
        return next;
      });
    },
    [onChange]
  );

  const handleSave = useCallback(async () => {
    setIsSaving(true);
    try {
      if (typeof window !== 'undefined') {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(formState));
      }

      if (onSave) {
        await onSave(formState);
      }

      try {
        await fetch('/admin/settings', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            max_concurrent_browsers: formState.maxConcurrentBrowsers,
            keep_alive_interval_sec: formState.keepAliveTtlSec,
            enable_stealth: formState.enableStealth,
            auto_rotate_proxy_on_403: formState.useProxyByDefault,
          }),
        });
      } catch {
        // Standart modül ortamında sessiz devam et
      }

      toast.success('Sanal tarayıcı ayarları başarıyla kaydedildi.');
    } catch {
      toast.error('Ayarlar kaydedilirken hata oluştu.');
    } finally {
      setIsSaving(false);
    }
  }, [formState, onSave]);

  const handleApplyChromiumProfile = useCallback(() => {
    updateState({
      defaultMode: 'chromium',
      useProxyByDefault: true,
      maxConcurrentBrowsers: 16,
      keepAliveTtlSec: 300,
      enableStealth: true,
      autoPruneOnOpen: true,
    });
    toast.success('Chromium tam donanımlı profil uygulandı.');
  }, [updateState]);

  const handleApplyHttpProfile = useCallback(() => {
    updateState({
      defaultMode: 'http',
      useProxyByDefault: true,
      maxConcurrentBrowsers: 32,
      keepAliveTtlSec: 60,
      enableStealth: false,
      autoPruneOnOpen: true,
    });
    toast.success('Hafif HTTP yüksek hız profili uygulandı.');
  }, [updateState]);

  const handleResetDefaults = useCallback(() => {
    updateState(DEFAULT_BROWSER_SETTINGS);
    toast.success('Ayarlar varsayılan değerlere sıfırlandı.');
  }, [updateState]);

  const actionMenuItems = useMemo<ActionMenuItem[]>(
    () => [
      {
        label: isSaving ? 'Kaydediliyor...' : 'Değişiklikleri Kaydet',
        icon: <Save size={15} />,
        isDefault: true,
        variant: 'primary',
        disabled: isSaving,
        onClick: handleSave,
      },
      {
        label: 'Hızlı Profil: Docker Headless Chromium (Tam Donanımlı)',
        icon: <Zap size={15} />,
        disabled: isSaving,
        onClick: handleApplyChromiumProfile,
      },
      {
        label: 'Hızlı Profil: Hafif HTTP İstemcisi (Yüksek Hız)',
        icon: <Zap size={15} />,
        disabled: isSaving,
        onClick: handleApplyHttpProfile,
      },
      {
        label: 'Varsayılan Ayarlara Sıfırla',
        icon: <RotateCcw size={15} />,
        danger: true,
        disabled: isSaving,
        dividerAbove: true,
        onClick: handleResetDefaults,
      },
    ],
    [isSaving, handleSave, handleApplyChromiumProfile, handleApplyHttpProfile, handleResetDefaults]
  );

  return (
    <BaseCardPage
      id="browser-settings-form"
      title="Sanal Tarayıcı & Web Ayarları"
      subtitle="AI Ajanlarının web gezinme yetenekleri, Playwright Docker eşzamanlılık sınırı ve proxy parametrelerini yapılandırın."
      icon={<Globe size={22} />}
      inModal={inModal}
      showBackButton={Boolean(onClose)}
      onClose={onClose}
      isSaving={isSaving}
      customActionMenu={
        <ActionMenu
          showDefaultActionAsButton={true}
          actions={actionMenuItems}
          dropdownHeader="Tarayıcı İşlemleri"
        />
      }
    >
      <div className="flex-col gap-16">
        <PolicySettingCard
          icon={<Globe size={20} />}
          iconActive={true}
          title="Varsayılan Yürütme Motoru"
          description="AI Ajanları canlı web gezintisi veya veri çekme araçlarını çağırdığında başlatılacak varsayılan motoru belirler."
          action={
            <div className="w-280">
              <BaseDropdownSecici
                value={formState.defaultMode}
                options={modeOptions}
                clearable={false}
                onChange={(id) => updateState({ defaultMode: (id as 'http' | 'chromium') || 'chromium' })}
              />
            </div>
          }
        />

        <PolicySettingCard
          icon={<Shield size={20} />}
          iconActive={formState.useProxyByDefault}
          title="Proxy Havuzu Üzerinden Tünelleme"
          description="Tüm web isteklerini @akalin/proxy_module üzerinden dönen proxy IP'leri ile tünelleyerek hedef sitelerin IP bazlı bot korumalarını aşar."
          action={
            <BaseSwitch
              checked={formState.useProxyByDefault}
              onChange={(e) => updateState({ useProxyByDefault: e.target.checked })}
              label={formState.useProxyByDefault ? 'Aktif' : 'Devre Dışı'}
            />
          }
        />

        <PolicySettingCard
          icon={<Monitor size={20} />}
          iconActive={true}
          title="Maksimum Eşzamanlı Sanal Tarayıcı"
          description="Docker konteyneri üzerinde aynı anda paralel çalışabilecek maksimum Chromium / Playwright tarayıcı oturumu kapasitesi."
          action={
            <div className="w-160">
              <TamsayiInput
                value={formState.maxConcurrentBrowsers}
                onChange={(e) =>
                  updateState({ maxConcurrentBrowsers: Number(e.target.value) || 16 })
                }
              />
            </div>
          }
        />

        <PolicySettingCard
          icon={<Clock size={20} />}
          iconActive={true}
          title="Oturum Boşta Kalma Süresi (TTL)"
          description="Herhangi bir yeni eylem yürütmeyen sanal tarayıcı oturumunun RAM tasarrufu için otomatik olarak kapatılacağı bekleme süresi."
          action={
            <div className="w-160">
              <TamsayiInput
                value={formState.keepAliveTtlSec}
                suffix="sn"
                onChange={(e) =>
                  updateState({ keepAliveTtlSec: Number(e.target.value) || 300 })
                }
              />
            </div>
          }
        />

        <PolicySettingCard
          icon={<Zap size={20} />}
          iconActive={formState.enableStealth}
          title="Stealth & Parmak İzi Gizleme"
          description="Headless Chromium bayraklarını (navigator.webdriver, user-agent) maskeleyerek Cloudflare ve anti-bot koruma sistemlerini atlatır."
          action={
            <BaseSwitch
              checked={formState.enableStealth}
              onChange={(e) => updateState({ enableStealth: e.target.checked })}
              label={formState.enableStealth ? 'Aktif' : 'Devre Dışı'}
            />
          }
        />

        <PolicySettingCard
          icon={<RefreshCw size={20} />}
          iconActive={formState.autoPruneOnOpen}
          title="Otomatik Zombi Oturum Temizliği (Auto-Prune)"
          description="Sanal Tarayıcı açıldığında ve arka planda periyodik olarak süresi dolmuş veya askıda kalmış oturumları otomatik temizler."
          action={
            <BaseSwitch
              checked={formState.autoPruneOnOpen}
              onChange={(e) => updateState({ autoPruneOnOpen: e.target.checked })}
              label={formState.autoPruneOnOpen ? 'Aktif' : 'Devre Dışı'}
            />
          }
        />
      </div>
    </BaseCardPage>
  );
};

export default BrowserSessionsPageSettingsForExternal;
