/**
 * @file BrowserSessionsPageSettingsForExternal.tsx
 * @description @akalin/browser_module - Flowchart Düğümleri ve Dış Modüller için Harici Ayar Sayfası (hasExternalSettings = true)
 */

import React, { useState, useMemo } from 'react';
import { Globe } from 'lucide-react';
import {
  BaseCardPage,
  BaseDropdownSecici,
  BaseSwitch,
  type DropdownOption,
} from '@akalin/ui';
import { useBrowserTranslation } from '../i18n/browserTranslations';

export interface BrowserExternalSettingsValue {
  defaultMode: 'http' | 'chromium';
  autoPruneOnOpen: boolean;
  useProxyByDefault: boolean;
}

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

  const [formState, setFormState] = useState<BrowserExternalSettingsValue>({
    defaultMode: value?.defaultMode || 'chromium',
    autoPruneOnOpen: Boolean(value?.autoPruneOnOpen ?? false),
    useProxyByDefault: Boolean(value?.useProxyByDefault ?? true),
  });

  const modeOptions = useMemo<DropdownOption[]>(
    () => [
      { id: 'chromium', value: 'chromium', label: 'Docker Headless Chromium (Tam Sanal Tarayıcı)' },
      { id: 'http', value: 'http', label: 'Hafif HTTP İstemcisi (Hızlı / JS-siz)' },
    ],
    []
  );

  const updateState = (patch: Partial<BrowserExternalSettingsValue>) => {
    const next = { ...formState, ...patch };
    setFormState(next);
    if (onChange) onChange(next);
  };

  return (
    <BaseCardPage
      title="Sanal Tarayıcı Düğüm Ayarları"
      subtitle="AI Ajanı ve Flowchart adımları için sanal tarayıcı varsayılanlarını belirleyin."
      icon={<Globe size={20} />}
      inModal={inModal}
      showBackButton={Boolean(onClose)}
      onClose={onClose}
      onSave={onSave ? () => onSave(formState) : undefined}
    >
      <div className="flex-col gap-16">
        <div className="form-group">
          <label>Varsayılan Yürütme Modu</label>
          <BaseDropdownSecici
            value={formState.defaultMode}
            options={modeOptions}
            clearable={false}
            onChange={(id) => updateState({ defaultMode: (id as 'http' | 'chromium') || 'chromium' })}
          />
        </div>

        <div className="form-group">
          <BaseSwitch
            checked={formState.useProxyByDefault}
            onChange={(e) => updateState({ useProxyByDefault: e.target.checked })}
            label="Varsayılan Olarak Proxy Servisi Üzerinden Çıkış Yap"
          />
        </div>

        <div className="form-group">
          <BaseSwitch
            checked={formState.autoPruneOnOpen}
            onChange={(e) => updateState({ autoPruneOnOpen: e.target.checked })}
            label="Sayfa Açıldığında Süresi Dolan Oturumları Otomatik Temizle"
          />
        </div>
      </div>
    </BaseCardPage>
  );
};

export default BrowserSessionsPageSettingsForExternal;
