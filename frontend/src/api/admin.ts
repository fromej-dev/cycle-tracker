import { AxiosResponse } from "axios";
import { AdminStats } from "@/types.ts";
import apiClient from "@/api/index.ts";

class AdminApi {
    static getStats(): Promise<AxiosResponse<AdminStats>> {
        return apiClient.get('/admin/stats');
    }
}
export default AdminApi;
