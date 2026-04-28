function detectReverseProxyBasePath() {
    if (typeof window === 'undefined') {
        return ''
    }
    const pathname = window.location.pathname.replace(/\/+$/, '') || '/'
    const routeRoots = ['/accounts', '/docs', '/gallery', '/image', '/jobs', '/login', '/settings', '/swagger', '/wall']
    for (const routeRoot of routeRoots) {
        if (pathname === routeRoot) {
            return ''
        }
        if (pathname.endsWith(routeRoot)) {
            return pathname.slice(0, -routeRoot.length).replace(/\/+$/, '')
        }
    }
    return ''
}

function resolveApiUrl(basePath: string) {
    const configuredApiUrl = (process.env.NEXT_PUBLIC_API_URL || '').replace(/\/$/, '')
    if (configuredApiUrl) {
        return configuredApiUrl
    }
    if (process.env.NODE_ENV === 'development') {
        return 'http://127.0.0.1:8000'
    }
    return basePath
}

const appBasePath = detectReverseProxyBasePath()

const webConfig = {
    apiUrl: resolveApiUrl(appBasePath),
    basePath: appBasePath,
    appVersion: process.env.NEXT_PUBLIC_APP_VERSION || '0.0.0',
}

export function withoutAppBasePath(pathname: string) {
    const basePath = webConfig.basePath
    if (!basePath) {
        return pathname || '/'
    }
    if (pathname === basePath) {
        return '/'
    }
    if (pathname.startsWith(`${basePath}/`)) {
        return pathname.slice(basePath.length) || '/'
    }
    return pathname || '/'
}

export function withAppBasePath(pathname: string) {
    const normalizedPath = pathname.startsWith('/') ? pathname : `/${pathname}`
    return `${webConfig.basePath}${normalizedPath}` || '/'
}

export default webConfig
