/**
 * @file index.ts
 * @description @akalin/browser_module - Tip Tanımları ve Sözleşmeler
 */

import type { ReactNode } from 'react';

export type BrowserExecutionMode = 'http' | 'chromium';
export type BrowserSessionStatus = 'idle' | 'busy' | 'closed';

export interface VirtualBrowserSessionDTO {
  id: string;
  conversation_id: string;
  app_id?: string;
  agent_id?: string;
  current_url: string;
  mode: BrowserExecutionMode;
  status: BrowserSessionStatus;
  requests_served: number;
  proxy_endpoint?: string;
  is_dynamic?: boolean;
  ttl_sec: number;
  created_at: string;
  last_active_at: string;
}

export interface InteractiveElementDTO {
  ref: number;
  tag: string;
  text: string;
  role?: string;
  type?: string;
}

export interface BrowserActionResultDTO {
  session_id: string;
  conversation_id: string;
  mode: BrowserExecutionMode;
  url: string;
  title: string;
  snapshot_text: string;
  interactive_elements: InteractiveElementDTO[];
  latency_ms?: number;
  error?: string;
}

export interface BrowserActionRequestDTO {
  action: 'navigate' | 'snapshot' | 'click' | 'type' | 'scroll' | 'back' | 'close';
  conversation_id: string;
  app_id?: string;
  agent_id?: string;
  url?: string;
  ref?: number;
  text?: string;
  direction?: 'up' | 'down';
  use_proxy?: boolean;
  force_chromium?: boolean;
}

export interface BrowserPoolMetricsDTO {
  total_sessions: number;
  active_busy_sessions: number;
  idle_sessions: number;
  http_mode_sessions: number;
  chromium_mode_sessions: number;
  max_capacity: number;
  avg_render_ms: number;
}

export interface BrowserPoolDashboardDTO {
  metrics: BrowserPoolMetricsDTO;
  sessions: VirtualBrowserSessionDTO[];
  recent_events: {
    id: string;
    event_type: string;
    session_id: string;
    url?: string;
    detail: string;
    created_at: string;
  }[];
}

export interface IBrowserServiceAdapter {
  getSessions(): Promise<VirtualBrowserSessionDTO[]>;
  getDashboard(): Promise<BrowserPoolDashboardDTO>;
  executeAction(req: BrowserActionRequestDTO): Promise<BrowserActionResultDTO>;
  terminateSession(sessionId: string): Promise<boolean>;
  pruneIdleSessions(): Promise<number>;
}

export interface BrowserModuleOptions {
  id?: string;
  title?: string;
  baseRoute?: string;
  order?: number;
  icon?: ReactNode;
  adapter?: IBrowserServiceAdapter;
  onNotify?: (message: string, type: 'success' | 'error' | 'info') => void;
}
