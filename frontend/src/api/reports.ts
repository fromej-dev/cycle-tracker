import apiClient from './index';
import { AxiosResponse } from 'axios';
import { formatISO } from 'date-fns';
const todayParam = () => ({ today: formatISO(new Date(), { representation: 'date' }) });
import {
    PeriodStats,
    CycleStats,
    PredictedPeriod,
    OvulationWindow, CycleContext, Forecast
} from '@/types';

const BASE_URL = '/reports';

class ReportApi {
    static fetchPeriodStats(): Promise<AxiosResponse<PeriodStats>> {
        return apiClient.get(`${BASE_URL}/period-stats`);
    }

    static fetchCycleStats(): Promise<AxiosResponse<CycleStats>> {
        return apiClient.get(`${BASE_URL}/cycle-stats`);
    }

    static fetchPredictedNextPeriod(): Promise<AxiosResponse<PredictedPeriod>> {
        return apiClient.get(`${BASE_URL}/predicted-next-period`, { params: todayParam() });
    }

    static fetchOvulationWindow(): Promise<AxiosResponse<OvulationWindow>> {
        return apiClient.get(`${BASE_URL}/ovulation-window`, { params: todayParam() });
    }

    static fetchForecast(): Promise<AxiosResponse<Forecast>> {
        return apiClient.get(`${BASE_URL}/forecast`, { params: todayParam() });
    }

    static fetchCycleContext(): Promise<AxiosResponse<CycleContext>> {
        return apiClient.get(`${BASE_URL}/cycle-context`, { params: todayParam() });
    }
}

export default ReportApi;
