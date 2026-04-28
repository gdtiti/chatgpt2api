import axios, {AxiosError, type AxiosRequestConfig} from "axios";

import webConfig, { withAppBasePath, withoutAppBasePath } from "@/constants/common-env";
import {clearStoredAuthKey, getStoredAuthKey, getStoredAuthSession} from "@/store/auth";

type RequestConfig = AxiosRequestConfig & {
    redirectOnUnauthorized?: boolean;
};

const request = axios.create({
    baseURL: webConfig.apiUrl.replace(/\/$/, ""),
    timeout: 30000,
});

function isApiRequestUrl(url?: string) {
    return typeof url === "string" && (url.startsWith("/api/") || url === "/api");
}

request.interceptors.request.use(async (config) => {
    const nextConfig = {...config};
    const authKey = await getStoredAuthKey();
    const headers = {...(nextConfig.headers || {})} as Record<string, string>;
    if (authKey && !headers.Authorization) {
        headers.Authorization = `Bearer ${authKey}`;
    }
    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-expect-error
    nextConfig.headers = headers;
    return nextConfig;
});

request.interceptors.response.use(
    (response) => {
        const contentType = String(response.headers["content-type"] || "");
        if (isApiRequestUrl(response.config.url) && contentType.includes("text/html")) {
            return Promise.reject(new Error("API 请求返回了网页内容，请检查反代是否正确转发 /api 路径"));
        }
        return response;
    },
    async (error: AxiosError<{ detail?: { error?: string }; error?: string; message?: string }>) => {
        const status = error.response?.status;
        const shouldRedirect = (error.config as RequestConfig | undefined)?.redirectOnUnauthorized !== false;
        if (status === 401 && shouldRedirect && typeof window !== "undefined") {
            const session = await getStoredAuthSession();
            const pathname = withoutAppBasePath(window.location.pathname);
            const isClientConsole = session?.kind === "client";
            const adminOnlyPrefixes = ["/accounts", "/settings", "/docs"];
            const shouldFallbackToImage =
                isClientConsole &&
                (adminOnlyPrefixes.some((prefix) => pathname.startsWith(prefix)) || pathname.startsWith("/jobs"));
            // Avoid redirect loop — only redirect if not already on /login
            if (!window.location.pathname.startsWith("/login")) {
                if (shouldFallbackToImage) {
                    window.location.replace(withAppBasePath("/image"));
                } else {
                    await clearStoredAuthKey();
                    window.location.replace(withAppBasePath("/login"));
                }
                // Return a never-resolving promise to prevent further error handling
                // while the browser navigates away
                return new Promise(() => {});
            }
        }

        const payload = error.response?.data;
        const message =
            payload?.detail?.error ||
            payload?.error ||
            payload?.message ||
            (error.code === "ECONNABORTED" ? "请求超时，请检查反代到后端 API 的连接" : "") ||
            error.message ||
            `请求失败 (${status || 500})`;
        return Promise.reject(new Error(message));
    },
);

type RequestOptions = {
    method?: string;
    body?: unknown;
    headers?: Record<string, string>;
    redirectOnUnauthorized?: boolean;
};

export async function httpRequest<T>(path: string, options: RequestOptions = {}) {
    const {method = "GET", body, headers, redirectOnUnauthorized = true} = options;
    const config: RequestConfig = {
        url: path,
        method,
        data: body,
        headers,
        redirectOnUnauthorized,
    };
    const response = await request.request<T>(config);
    return response.data;
}
