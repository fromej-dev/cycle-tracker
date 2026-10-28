// src/stores/auth.ts
import { defineStore } from 'pinia';
import AuthApi from '@/api/auth';
import router from '@/router'; // Ensure your router is correctly imported
import {
    AuthState,
    AuthGetters,
    AuthActions,
    Login,
    UserRegistration,
    PasswordChange
} from '@/types';
import { useReportsStore } from "@/stores/reports"; // Assuming this store exists
import { useSymptomsStore } from '@/stores/symptoms';
import UsersApi from "@/api/users";

export const useAuthStore = defineStore<'auth', AuthState, AuthGetters, AuthActions>('auth', {
    state: (): AuthState => ({
        token: localStorage.getItem('token') || null,
        refreshToken: localStorage.getItem('refreshToken') || null, // Add refreshToken
        user: null,
        loading: false,
        error: null
    }),
    getters: {
        isAuthenticated: (state: AuthState): boolean => !!state.token
    } as AuthGetters,

    actions: {
        clearError() {
            this.error = null;
        },
        setError(message: string) {
            this.error = message;
        },
        async changePassword(data: PasswordChange) {
            return await UsersApi.changeOwnPassword(data);
        },
        async deleteAccount() {
            return await UsersApi.deleteOwnUser();
        },
        async login(credentials: Login): Promise<void> {
            this.loading = true;
            this.error = null;
            try {
                const response = await AuthApi.loginUser(credentials);
                const accessToken = response.data.access_token;
                const refreshTokenVal = response.data.refresh_token;

                this.token = accessToken;
                this.refreshToken = refreshTokenVal;

                localStorage.setItem('token', accessToken);
                localStorage.setItem('refreshToken', refreshTokenVal);

                await this.fetchUser();
                router.push({ name: 'dashboard' });
            } catch (error: any) {
                this.token = null;
                this.refreshToken = null;
                localStorage.removeItem('token');
                localStorage.removeItem('refreshToken');
                this.error = error.response?.data?.message || error.response?.data?.error || 'Login failed';
                console.error('Login error:', error.response?.data || error);
            } finally {
                this.loading = false;
            }
        },
        async register(userData: UserRegistration): Promise<void> {
            this.loading = true;
            this.error = null;
            try {
                await AuthApi.registerUser(userData);
                router.push({ name: 'login' });
            } catch (error: any) {
                this.error = error.response?.data?.message || 'Registration failed';
                if (error.response?.data?.detail) {
                    this.error = Object.values(error.response.data.detail)
                        .flat()
                        .filter((item): item is string => typeof item === 'string')
                        .join(', ');
                }
                console.error('Registration error:', error.response?.data || error);
            } finally {
                this.loading = false;
            }
        },
        async fetchUser(): Promise<void> {
            if (!this.token) return;
            try {
                const response = await UsersApi.getOwnUser();
                this.user = response.data;
            } catch (error: any) {
                console.error('Fetch user error:', error.response?.data || error);
            }
        },
        logout(): void {
            this.token = null;
            this.refreshToken = null;
            this.user = null;
            this.error = null;

            const reportStore = useReportsStore();
            reportStore.$reset();
            useSymptomsStore().reset();

            localStorage.removeItem('token');
            localStorage.removeItem('refreshToken');
            router.push({ name: 'login' });
        },
        async initializeAuth(): Promise<void> {
            const token = localStorage.getItem("token");
            const refreshTokenVal = localStorage.getItem("refreshToken");

            if (token && refreshTokenVal) {
                this.token = token;
                this.refreshToken = refreshTokenVal;
                // Stay on the current route (the router guard sends guests-only pages to the dashboard)
                await this.fetchUser();
            } else {
                // If one is missing, clear both for consistency
                this.token = null;
                this.refreshToken = null;
                localStorage.removeItem('token');
                localStorage.removeItem('refreshToken');
            }
        },

        async refreshTokenAction(): Promise<string | null> {
            if (!this.refreshToken) {
                this.logout(); // No refresh token, so log out
                return null;
            }
            this.loading = true;
            try {
                const response = await AuthApi.refreshToken();

                const newAccessToken = response.data.access_token;
                this.token = newAccessToken;
                localStorage.setItem('token', newAccessToken);
                this.error = null;
                return newAccessToken;
            } catch (error: any) {
                console.error('Refresh token error:', error.response?.data || error);
                this.logout();
                this.error = error.response?.data?.message || error.response?.data?.error || 'Session expired. Please login again.';
                return null;
            } finally {
                this.loading = false;
            }
        }
    } as AuthActions
});