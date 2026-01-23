import { defineStore } from 'pinia';
import PeriodApi from '@/api/periods';
import { PeriodsState, PeriodsActions, PeriodCreate, PeriodUpdate } from '@/types';
import {useReportsStore} from "@/stores/reports.ts";
import {formatISO} from "date-fns";

export const usePeriodsStore = defineStore<'periods', PeriodsState, {}, PeriodsActions>('periods', {
    state: () => ({
        periods: [],
        loading: false,
        error: null,
        pagination: {
            page: 1,
            per_page: 10,
            total: 0
        }
    }),

    actions: {
        setError(message: string) {
            this.error = message;
        },
        clearError() {
            this.error = null;
        },
        async fetchPeriods(page = this.pagination.page, per_page = this.pagination.per_page) {
            this.loading = true;
            this.error = null;
            try {
                const response = await PeriodApi.fetchPeriods(page, per_page);
                this.periods = response.data;
                // Pagination logic could go here if the API supports it
            } catch (error: any) {
                this.error = error.response?.data?.message || 'Failed to fetch periods';
                console.error('Fetch periods error:', error);
            } finally {
                this.loading = false;
            }
        },

        async startPeriodToday() {
            const today = formatISO(new Date(), { representation: 'date' });
            return this.createPeriod(today)
        },

        async createPeriod(startDate: string) {
            this.error = null;
            try {
                const periodData: PeriodCreate = { start_date: startDate };
                const response = await PeriodApi.createPeriod(periodData);
                this.periods.unshift(response.data);
                await this.refreshStats()
                return this.periods[0]
            } catch (error: any) {
                this.error = error.response?.data?.message || 'Failed to create period';
                console.error('Create period error:', error);
            }
        },

        async updatePeriod(periodId: number, endDate: string) {
            this.loading = true;
            this.error = null;
            try {
                const periodData: PeriodUpdate = { end_date: endDate };
                const response = await PeriodApi.updatePeriod(periodId, periodData);
                const index = this.periods.findIndex(p => p.id === periodId);
                if (index !== -1) this.periods[index] = response.data;
                await this.refreshStats()
                return response.data
            } catch (error: any) {
                this.error = error.response?.data?.message || 'Failed to update period';
                console.error('Update period error:', error);
            } finally {
                this.loading = false;
            }
        },

        async deletePeriod(periodId: number) {
            this.loading = true;
            this.error = null;
            try {
                await PeriodApi.deletePeriod(periodId);
                this.periods = this.periods.filter(p => p.id !== periodId);
            } catch (error: any) {
                this.error = error.response?.data?.message || 'Failed to delete period';
                console.error('Delete period error:', error);
            } finally {
                await this.refreshStats()
                this.loading = false;
            }
        },

        async refreshStats() {
            const reportStore = useReportsStore()
            await reportStore.fetchPeriodStats()
            await reportStore.fetchCycleContext()
        }
    }
});
