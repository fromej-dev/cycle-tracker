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
