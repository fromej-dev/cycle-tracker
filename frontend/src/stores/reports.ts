import { defineStore } from 'pinia';
import ReportApi from '@/api/reports';
import {ReportsState, ReportsActions} from '@/types';

export const useReportsStore = defineStore<'reports', ReportsState, {}, ReportsActions>('reports', {
    state: () => ({
        periodStats: {},
        cycleStats: null,
        cycleContext: {},
        forecast: null,
        predictedNextPeriod: null,
        ovulationWindow: null,
        loading: false,
        error: null
    }),

    actions: {
        async fetchPeriodStats() {
            this.loading = true;
            this.error = null;
            try {
                const response = await ReportApi.fetchPeriodStats();
                Object.assign(this.periodStats,response.data)
            } catch (error: any) {
                this.error = error.response?.data?.message || 'Failed to fetch period stats';
                console.error('Fetch period stats error:', error);
            } finally {
                this.loading = false;
            }
        },

        async fetchCycleStats() {
            this.loading = true;
            this.error = null;
            try {
                const response = await ReportApi.fetchCycleStats();
                this.cycleStats = response.data;
            } catch (error: any) {
                this.error = error.response?.data?.message || 'Failed to fetch cycle stats';
                console.error('Fetch cycle stats error:', error);
            } finally {
                this.loading = false;
            }
        },

        async fetchPredictedNextPeriod() {
            this.loading = true;
            this.error = null;
            try {
                const response = await ReportApi.fetchPredictedNextPeriod();
                this.predictedNextPeriod = response.data;
            } catch (error: any) {
                this.error = error.response?.data?.message || 'Failed to predict next period';
                console.error('Fetch predicted period error:', error);
            } finally {
                this.loading = false;
            }
        },

        async fetchOvulationWindow() {
            this.loading = true;
            this.error = null;
            try {
                const response = await ReportApi.fetchOvulationWindow();
                this.ovulationWindow = response.data;
            } catch (error: any) {
                this.error = error.response?.data?.message || 'Failed to calculate ovulation window';
                console.error('Fetch ovulation window error:', error);
            } finally {
                this.loading = false;
            }
        },

        async fetchForecast() {
            // A failed forecast must never take the dashboard down: the ring degrades to "still learning".
            try {
                const response = await ReportApi.fetchForecast();
                this.forecast = response.data;
            } catch (error: any) {
                this.forecast = null;
                console.error('Fetch forecast error:', error);
            }
        },

        async fetchCycleContext() {
            this.error = null;
            try {
                const response = await ReportApi.fetchCycleContext();
                this.cycleContext = response.data // replace, never merge: stale fields would linger after a period ends
                return this.cycleContext
            } catch (error: any) {
                this.error = error.response?.data?.message || 'Failed to fetch cycle context';
                console.error('Fetch cycle context error:', error);
            }
        }
    },
});
