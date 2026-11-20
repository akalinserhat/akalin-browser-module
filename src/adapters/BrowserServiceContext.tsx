/**
 * @file BrowserServiceContext.tsx
 * @description @akalin/browser_module - Servis Adaptörü ve React Context Sağlayıcısı
 */

import React, { createContext, useContext, useMemo, useState, useEffect } from 'react';
import type {
  IBrowserServiceAdapter,
  VirtualBrowserSessionDTO,
  BrowserPoolDashboardDTO,
  BrowserActionRequestDTO,
  BrowserActionResultDTO,
} from '../types';

export class RestBrowserServiceAdapter implements IBrowserServiceAdapter {
  private baseUrl: string;

  constructor(baseUrl: string = '/api/browser') {
    this.baseUrl = baseUrl;
  }

  async getSessions(): Promise<VirtualBrowserSessionDTO[]> {
    const res = await fetch(`${this.baseUrl}/sessions`);
    if (!res.ok) throw new Error('Oturumlar alınamadı.');
    return res.json();
  }

  async getDashboard(): Promise<BrowserPoolDashboardDTO> {
    const res = await fetch(`${this.baseUrl}/dashboard`);
    if (!res.ok) throw new Error('Dashboard verileri alınamadı.');
    return res.json();
  }

  async executeAction(req: BrowserActionRequestDTO): Promise<BrowserActionResultDTO> {
    const res = await fetch(`${this.baseUrl}/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!res.ok) throw new Error('İşlem yürütülemedi.');
    return res.json();
  }

  async terminateSession(sessionId: string): Promise<boolean> {
    const res = await fetch(`${this.baseUrl}/sessions/${sessionId}`, {
      method: 'DELETE',
    });
    return res.ok;
  }

  async pruneIdleSessions(): Promise<number> {
    const res = await fetch(`${this.baseUrl}/sessions/prune`, {
      method: 'POST',
    });
    if (!res.ok) return 0;
    const data = await res.json();
    return Number(data.pruned_count || 0);
  }
}

export interface BrowserContextValue {
  adapter: IBrowserServiceAdapter;
  sessions: VirtualBrowserSessionDTO[];
  dashboard: BrowserPoolDashboardDTO | null;
  loading: boolean;
  refresh: () => Promise<void>;
  terminateSession: (sessionId: string) => Promise<void>;
  pruneIdleSessions: () => Promise<void>;
}

export const BrowserContext = createContext<BrowserContextValue | null>(null);

export interface BrowserProviderProps {
  adapter?: IBrowserServiceAdapter;
  children: React.ReactNode;
  onNotify?: (msg: string, type: 'success' | 'error' | 'info') => void;
}

export const BrowserProvider: React.FC<BrowserProviderProps> = ({
  adapter = new RestBrowserServiceAdapter(),
  children,
  onNotify,
}) => {
  const [sessions, setSessions] = useState<VirtualBrowserSessionDTO[]>([]);
  const [dashboard, setDashboard] = useState<BrowserPoolDashboardDTO | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const [sess, dash] = await Promise.all([
        adapter.getSessions().catch(() => []),
        adapter.getDashboard().catch(() => null),
      ]);
      setSessions(sess);
      setDashboard(dash);
    } catch (err: any) {
      if (onNotify) onNotify(err.message || 'Veriler yüklenirken hata oluştu.', 'error');
    } finally {
      setLoading(false);
    }
  };

  const terminateSession = async (sessionId: string) => {
    try {
      const ok = await adapter.terminateSession(sessionId);
      if (ok) {
        if (onNotify) onNotify('Oturum başarıyla sonlandırıldı.', 'success');
        await refresh();
      }
    } catch (err: any) {
      if (onNotify) onNotify(err.message || 'Oturum kapatılamadı.', 'error');
    }
  };

  const pruneIdleSessions = async () => {
    try {
      const count = await adapter.pruneIdleSessions();
      if (onNotify) onNotify(`${count} adet boşta oturum temizlendi.`, 'success');
      await refresh();
    } catch (err: any) {
      if (onNotify) onNotify(err.message || 'Temizleme başarısız.', 'error');
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const value = useMemo(
    () => ({
      adapter,
      sessions,
      dashboard,
      loading,
      refresh,
      terminateSession,
      pruneIdleSessions,
    }),
    [adapter, sessions, dashboard, loading]
  );

  return <BrowserContext.Provider value={value}>{children}</BrowserContext.Provider>;
};

export function useBrowserModule() {
  const ctx = useContext(BrowserContext);
  if (!ctx) {
    throw new Error('useBrowserModule must be used within a BrowserProvider');
  }
  return ctx;
}
