/**
 * React-Query hook for the Automation Rate time-series (INT-019 · Sprint-16).
 */
import { useQuery } from '@tanstack/react-query';

import { getAutomationRate, type AutomationRateResponse } from '@/api/analytics';

export function useAutomationRate(period: string = '30d') {
  return useQuery<AutomationRateResponse>({
    queryKey: ['analytics', 'automation-rate', period],
    queryFn: () => getAutomationRate(period),
    // Per-day data — refresh every 5m is plenty.
    refetchInterval: 5 * 60 * 1000,
  });
}
