/**
 * @file BrowserSessionsPage.tsx
 * @description @akalin/browser_module - Sanal Tarayıcı Oturumları ve Havuz Yönetim Sayfası
 */

import React, { useMemo } from 'react';
import {
  Globe,
  MonitorCheck,
  RefreshCw,
  Trash2,
  Zap,
  Activity,
  Cpu,
} from 'lucide-react';
import {
  BasePage,
  BaseSystemCard,
  DashboardStatCard,
  ActionMenu,
  useAlertDialog,
  type ActionMenuItem,
} from '@akalin/ui';
import { useBrowserModule } from '../adapters/BrowserServiceContext';
import { useBrowserTranslation } from '../i18n/browserTranslations';
import type { VirtualBrowserSessionDTO } from '../types';

export const BrowserSessionsPage: React.FC = () => {
  const { t } = useBrowserTranslation();
  const {
    sessions,
    dashboard,
    loading,
    refresh,
    terminateSession,
    pruneIdleSessions,
  } = useBrowserModule();
  const alertDialog = useAlertDialog();

  const metrics = dashboard?.metrics;
  const totalCount = metrics?.total_sessions ?? sessions.length;
  const busyCount = metrics?.active_busy_sessions ?? sessions.filter((s) => s.status === 'busy').length;
  const idleCount = metrics?.idle_sessions ?? sessions.filter((s) => s.status === 'idle').length;
  const httpCount = metrics?.http_mode_sessions ?? sessions.filter((s) => s.mode === 'http').length;
  const chromiumCount = metrics?.chromium_mode_sessions ?? sessions.filter((s) => s.mode === 'chromium').length;

  const handleConfirmTerminate = (session: VirtualBrowserSessionDTO) => {
    alertDialog.showAlert(
      'confirm',
      t('browser.terminate'),
      `${session.id} (${session.current_url || 'about:blank'}) ${t('browser.terminateConfirm')}`,
      async () => {
        await terminateSession(session.id);
      },
      t('browser.terminate'),
      'İptal',
      true
    );
  };

  const headerDropdownActions = useMemo<ActionMenuItem[]>(
    () => [
      {
        label: t('browser.pruneIdle'),
        icon: <Trash2 size={15} />,
        onClick: pruneIdleSessions,
      },
      {
        label: t('browser.refresh'),
        icon: <RefreshCw size={15} />,
        dividerAbove: true,
        onClick: refresh,
      },
    ],
    [refresh, pruneIdleSessions, t]
  );

  return (
    <BasePage
      title={t('browser.title')}
      subtitle={t('browser.subtitle')}
      icon={<Globe size={22} />}
      headerExtra={
        <ActionMenu
          triggerLabel="İşlemler"
          actions={headerDropdownActions}
        />
      }
    >
      {/* Üst Metrik Kartları */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3.5 mb-6">
        <DashboardStatCard
          icon={<MonitorCheck size={20} />}
          title={t('browser.totalSessions')}
          value={totalCount}
          variant="primary"
        />
        <DashboardStatCard
          icon={<Activity size={20} />}
          title={t('browser.busySessions')}
          value={busyCount}
          variant="warning"
        />
        <DashboardStatCard
          icon={<Zap size={20} />}
          title={t('browser.idleSessions')}
          value={idleCount}
          variant="success"
        />
        <DashboardStatCard
          icon={<Globe size={20} />}
          title={t('browser.httpMode')}
          value={httpCount}
          variant="default"
        />
        <DashboardStatCard
          icon={<Cpu size={20} />}
          title={t('browser.chromiumMode')}
          value={chromiumCount}
          variant="primary"
        />
      </div>

      {/* Oturum Kartları Listesi */}
      <div className="space-y-3">
        {loading && sessions.length === 0 ? (
          <div className="p-8 text-center text-muted text-sm">Yükleniyor...</div>
        ) : sessions.length === 0 ? (
          <div className="p-12 text-center text-muted border border-dashed rounded-xl">
            {t('browser.noSessions')}
          </div>
        ) : (
          sessions.map((s) => {
            const isChromium = s.mode === 'chromium';
            const isBusy = s.status === 'busy';

            return (
              <BaseSystemCard
                key={s.id}
                icon={isChromium ? <Cpu size={20} /> : <Globe size={20} />}
                iconBoxVariant={isBusy ? 'warning' : isChromium ? 'primary' : 'success'}
                borderHighlight={isBusy ? 'border-l-warning' : isChromium ? 'border-l-primary' : 'border-l-success'}
                title={s.current_url || 'about:blank'}
                subtitle={`${s.id} · Konuşma: ${s.conversation_id} ${s.proxy_endpoint ? `· Proxy: ${s.proxy_endpoint}` : ''}`}
                isDefault={true}
                defaultPillText={isChromium ? 'Chromium Docker' : 'Fast HTTP'}
                actions={[
                  {
                    label: t('browser.terminate'),
                    icon: <Trash2 size={15} />,
                    variant: 'danger',
                    onClick: () => handleConfirmTerminate(s),
                  },
                ]}
              >
                <div className="flex items-center gap-4 text-xs text-muted mt-2 pt-2 border-t border-border/50">
                  <span>İstekler: <strong className="text-foreground">{s.requests_served}</strong></span>
                  <span>Durum: <strong className={isBusy ? 'text-warning' : 'text-success'}>{s.status.toUpperCase()}</strong></span>
                  <span>TTL: <strong className="text-foreground">{s.ttl_sec}s</strong></span>
                </div>
              </BaseSystemCard>
            );
          })
        )}
      </div>
    </BasePage>
  );
};

export default BrowserSessionsPage;
