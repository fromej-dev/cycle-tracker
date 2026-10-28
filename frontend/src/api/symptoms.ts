import apiClient from './index';
import { localToday } from './plan';

export interface SymptomDay { date: string; symptoms: string[]; custom: string[] }
export interface SymptomSuggestions { frequent: string[]; recent_custom: string[] }

export const symptomsApi = {
  range: (start: string, end: string) => apiClient.get<SymptomDay[]>('/symptoms', { params: { start, end } }),
  save: (date: string, b: { symptoms: string[]; custom: string[] }) =>
    apiClient.put<SymptomDay>(`/symptoms/${date}`, b, { params: { today: localToday() } }),
  suggestions: () => apiClient.get<SymptomSuggestions>('/symptoms/suggestions', { params: { today: localToday() } }),
};
