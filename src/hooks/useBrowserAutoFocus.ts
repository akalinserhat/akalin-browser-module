/**
 * @file useBrowserAutoFocus.ts
 * @description @akalin/browser_module - Form ve Arama Odaklanma Kancası (AutoFocus Architecture)
 */

import { useEffect, useRef } from 'react';

export function useBrowserAutoFocus(enabled: boolean = true) {
  const targetRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!enabled) return;
    const timer = setTimeout(() => {
      if (targetRef.current) {
        targetRef.current.focus();
      }
    }, 100);
    return () => clearTimeout(timer);
  }, [enabled]);

  return targetRef;
}
