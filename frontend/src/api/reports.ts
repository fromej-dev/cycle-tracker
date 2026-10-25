import apiClient from './index';
import { AxiosResponse } from 'axios';
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
        return apiClient.get(`${BASE_URL}/predicted-next-period`);
    }

    static fetchOvulationWindow(): Promise<AxiosResponse<OvulationWindow>> {
        return apiClient.get(`${BASE_URL}/ovulation-window`);
    }

    static fetchForecast(): Promise<AxiosResponse<Forecast>> {
        return apiClient.get(`${BASE_URL}/forecast`);
    }

    static fetchCycleContext(): Promise<AxiosResponse<CycleContext>> {
        return apiClient.get(`${BASE_URL}/cycle-context`);
    }
}

export default ReportApi;
