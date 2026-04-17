/**
 * Analytics API client (INT-019 · Sprint-16).
 *
 * Wraps ``/api/v1/analytics/automation-rate`` — a daily time-series of
 * the tenant's automation rate plus per-stage error counts for the
 * stacked area breakdown on the Automation page.
 */
import { apiGet } from './authInterceptor';

export interface AutomationRatePoint {
  date: string; // YYYY-MM-DD
  rate_percent: number;
  intake_errors: number;
  fusion_errors: number;
  compliance_errors: number;
  total_items: number;
}

export interface AutomationRateSummary {
  current_rate: number;
  average_rate: number;
  best_day: AutomationRatePoint | null;
  worst_day: AutomationRatePoint | null;
  target_low: number; // typically 60
  target_high: number; // typically 85
  trend_pct: number;
  top_error_stage: 'intake' | 'fusion' | 'compliance' | 'none';
}

export interface AutomationRateResponse {
  period_days: number;
  points: AutomationRatePoint[];
  summary: AutomationRateSummary;
}

export function getAutomationRate(
  period: string = '30d',
): Promise<AutomationRateResponse> {
  return apiGet<AutomationRateResponse>(
    `/analytics/automation-rate?period=${encodeURIComponent(period)}`,
  );
}
