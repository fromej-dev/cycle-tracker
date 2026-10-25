// --- API Schemas ---

export interface Period {
    id: number;
    user_id: number;
    start_date: string; // ISO date format
    end_date: string | null; // Nullable for ongoing periods
    duration: number | null; // Nullable if end_date is missing
    created_at: string; // ISO date-time
}

export interface PeriodCreate {
    start_date: string;
}

export interface PeriodUpdate {
    end_date: string;
}

export interface PeriodStats {
    average_duration: number | null;
    max_duration: number | null;
    min_duration: number | null;
    count: number;
}

export interface CycleStats {
    average_length: number | null;
    max_length: number | null;
    min_length: number | null;
    count: number;
}

export interface PredictedPeriod {
    predicted_start: string;
}

export interface OvulationWindow {
    ovulation_date: string;
    fertile_window_start: string;
    fertile_window_end: string;
}

export interface CycleContext {
    status: 'period' | 'waiting';
    current_period_id: number;
    days_running?: number;
    cycle_day?: number;
    cycle_length?: number;
    progress_percent?: number;
    predicted_start?: string;
    days_until_next_period?: number;
    ovulation_date?: string;
    fertile_window: {
        start?: string;
        end?: string;
    };
    is_today_ovulation: boolean;
    is_in_fertile_window: boolean;
}


export interface ForecastInterval { start: string; end: string }
export interface ForecastDay { date: string; p_start: number; p_bleeding: number; p_fertile: number }
export type ForecastConfidence = 'learning' | 'regular' | 'variable' | 'irregular' | 'overdue';
export interface Forecast {
    most_likely_start: string | null;
    interval_50: ForecastInterval | null;
    interval_80: ForecastInterval | null;
    probability_next_3_days: number | null;
    confidence: ForecastConfidence;
    predictive_sd_days: number | null;
    cycles_used: number;
    days: ForecastDay[] | null;
    fertile_window: { start: string; end: string; ovulation_date: string | null; ovulation_interval_80?: ForecastInterval | null } | null;
    is_late: boolean;
}

// --- Auth & User ---

export interface Login {
    login: string; // Could be email or username depending on backend
    password: string;
}

export interface UserRegistration {
    username: string;
    email: string;
    password: string;
    confirm_password: string;
}

export interface PasswordChange {
    current_password: string;
    new_password: string;
}

export interface User {
    id: number;
    username: string;
    email: string;
    created_at: string;
}

export interface TokenPair {
    access_token: string;
    refresh_token: string;
}

export interface AccessToken {
    access_token: string;
}

// --- Error Handling ---

export interface HTTPError {
    message: string;
    detail: any; // Flexible shape; use specific structure if needed
}

export interface ValidationError {
    message: string;
    detail: Record<string, string | string[] | Record<string, string[]>>;
}

// --- Pinia Store Types ---

// Auth
export interface AuthState {
    token: string | null;
    refreshToken: string | null; // Add refreshToken
    user: User | null; // Assuming User type is defined
    loading: boolean;
    error: string | string[] | null; // Allow string array for multiple errors
}

export interface AuthGetters {
    isAuthenticated: (state: AuthState) => boolean;
}

export interface AuthActions {
    clearError: () => void;
    setError: (message: string) => void;
    changePassword: (data: PasswordChange) => Promise<any>; // Or specific response type
    deleteAccount: () => Promise<any>; // Or specific response type
    login: (credentials: Login) => Promise<void>;
    register: (userData: UserRegistration) => Promise<void>;
    fetchUser: () => Promise<void>;
    logout: () => void;
    initializeAuth: () => void;
    refreshTokenAction: () => Promise<string | null>; // Add this, returns new access token or null
}

// Periods Store
export interface PeriodsState {
    periods: Period[];
    loading: boolean;
    error: string | null;
    pagination: {
        page: number;
        per_page: number;
        total: number;
    };
}

export interface PeriodsGetters {}

export interface PeriodsActions {
    setError(message: string): void;
    clearError(): void;
    fetchPeriods(page?: number, per_page?: number): Promise<void>;
    startPeriodToday(): Promise<void>;
    createPeriod(startDate: string): Promise<void>;
    updatePeriod(periodId: number, endDate: string): Promise<void>;
    deletePeriod(periodId: number): Promise<void>;
    refreshStats(): Promise<void>;
}

// Reports Store (new!)
export interface ReportsState {
    periodStats: PeriodStats | null;
    cycleStats: CycleStats | null;
    cycleContext: CycleContext | null;
    forecast: Forecast | null;
    predictedNextPeriod: PredictedPeriod | null;
    ovulationWindow: OvulationWindow | null;
    loading: boolean;
    error: string | null;
}

export interface ReportsGetters {}

export interface ReportsActions {
    fetchPeriodStats(): Promise<void>;
    fetchCycleStats(): Promise<void>;
    fetchPredictedNextPeriod(): Promise<void>;
    fetchOvulationWindow(): Promise<void>;
    fetchCycleContext(): Promise<void>;
    fetchForecast(): Promise<void>;
}
