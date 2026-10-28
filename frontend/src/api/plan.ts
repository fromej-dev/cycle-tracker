import apiClient from './index';
import { formatISO } from 'date-fns';

/** The client's local date: the server must never guess "today" from its own clock. */
export const localToday = () => formatISO(new Date(), { representation: 'date' });

export type CheckStatus = 'ok' | 'learning' | 'overdue' | 'no_data';

export interface DateCheck {
  start: string;
  end: string;
  status: CheckStatus;
  confidence: string | null;
  probability_any: number | null;
  most_likely_days: any;
  horizon_note: string | null;
  includes_past_dates: boolean;
  reason: string | null;
  days: { date: string; p_bleeding: number }[];
  cycles_used: number;
  cycles_needed: number;
}

export interface PlanEvent {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
  probability_any: number | null;
  most_likely_days: any;
  status: CheckStatus;
  is_past: boolean;
  confidence: string | null;
  horizon_note: string | null;
  reason: string | null;
}

export interface CalendarFeed {
  enabled: boolean;
  label: string;
  include_fertile: boolean;
  fertile_label: string | null;
  mark_estimates: boolean;
  timezone: string | null;
}

/** Turn the API's 422 shape {message, detail:{json|query:{field:[msgs]}}} into one friendly line. */
export function apiMessage(e: any, fallback: string): string {
  const d = e?.response?.data;
  const detail = d?.detail?.json ?? d?.detail?.query;
  if (detail && typeof detail === 'object') {
    const first = Object.values(detail).flat()[0];
    if (typeof first === 'string') return first;
  }
  return d?.message || fallback;
}

export const dateCheckApi = {
  check: (start: string, end: string) =>
    apiClient.get<DateCheck>('/reports/date-check', { params: { start, end, today: localToday() } }),
};

export const eventsApi = {
  list: () => apiClient.get<PlanEvent[]>('/events', { params: { today: localToday() } }),
  create: (b: { name: string; start_date: string; end_date: string }) => apiClient.post<PlanEvent>('/events', b, { params: { today: localToday() } }),
  update: (id: number, b: { name: string; start_date: string; end_date: string }) => apiClient.put<PlanEvent>(`/events/${id}`, b, { params: { today: localToday() } }),
  remove: (id: number) => apiClient.delete(`/events/${id}`),
};

export const feedApi = {
  get: () => apiClient.get<CalendarFeed>('/users/me/calendar-feed'),
  create: (timezone?: string) => apiClient.post<{ path: string; url: string | null }>('/users/me/calendar-feed', { timezone }),
  update: (b: Partial<CalendarFeed>) => apiClient.patch<CalendarFeed>('/users/me/calendar-feed', b),
  revoke: () => apiClient.delete('/users/me/calendar-feed'),
};

export interface PartnerShare { enabled: boolean; name: string; scope: { fertile: boolean; window_days: number; show_current: boolean } }
export interface HomeAssistant { enabled: boolean; include_fertile: boolean }
export interface Webhook { id: number; url: string; events: string[]; active: boolean; last_status: number | null; last_attempt_at: string | null; failures: number; secret?: string }
export const WEBHOOK_EVENTS = ['period_started', 'period_ended', 'period_expected_soon', 'fertile_window_starting'] as const;
type Created = { path: string; url: string | null };

export const partnerApi = {
  get: () => apiClient.get<PartnerShare>('/users/me/partner-share'),
  create: (b: { name: string; scope: { fertile: boolean; window_days: number; show_current: boolean } }) => apiClient.post<Created>('/users/me/partner-share', b),
  update: (b: Partial<{ name: string; scope: { fertile: boolean; window_days: number; show_current: boolean } }>) => apiClient.patch<PartnerShare>('/users/me/partner-share', b),
  revoke: () => apiClient.delete('/users/me/partner-share'),
};

export const haApi = {
  get: () => apiClient.get<HomeAssistant>('/users/me/home-assistant'),
  create: (include_fertile: boolean) => apiClient.post<Created>('/users/me/home-assistant', { include_fertile }),
  update: (include_fertile: boolean) => apiClient.patch<HomeAssistant>('/users/me/home-assistant', { include_fertile }),
  revoke: () => apiClient.delete('/users/me/home-assistant'),
};

export const webhookApi = {
  list: () => apiClient.get<Webhook[]>('/users/me/webhooks'),
  create: (b: { url: string; events: string[] }) => apiClient.post<Webhook>('/users/me/webhooks', b),
  update: (id: number, b: Partial<Pick<Webhook, 'url' | 'events' | 'active'>>) => apiClient.patch<Webhook>(`/users/me/webhooks/${id}`, b),
  remove: (id: number) => apiClient.delete(`/users/me/webhooks/${id}`),
  test: (id: number) => apiClient.post<{ delivered: boolean; status: number; error: string | null }>(`/users/me/webhooks/${id}/test`),
  rotate: (id: number) => apiClient.post<Webhook>(`/users/me/webhooks/${id}/rotate-secret`),
};

export const doctorApi = {
  html: (months: number) => apiClient.get<string>('/reports/doctor', { params: { months, today: localToday() }, responseType: 'text', transformResponse: (d) => d }),
};
