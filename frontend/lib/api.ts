// The only module that talks to the backend. Every number on screen arrives through here.
export const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
export const TOKEN_KEY = 'drishti.token';
export const NO_DATA = 'Not present in current dataset';

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (typeof window === 'undefined') return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', 'Bearer ' + token);
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const response = await fetch(API_BASE + '/api' + path, { ...init, headers });
  if (response.status === 401) {
    setToken(null);
    if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
      window.location.href = '/login';
    }
    throw new ApiError(401, 'Your session has expired. Please sign in again.');
  }
  if (!response.ok) {
    let detail = 'The request could not be completed.';
    try {
      const body = await response.json();
      if (body && typeof body.detail === 'string') detail = body.detail;
    } catch {
      /* keep the default message */
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: body === undefined ? undefined : JSON.stringify(body) }),
  upload: <T,>(path: string, form: FormData) => request<T>(path, { method: 'POST', body: form }),
};

export function formatCurrency(value?: number | null) {
  if (value === null || value === undefined) return NO_DATA;
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(value);
}

export function formatNumber(value?: number | null, digits = 0) {
  if (value === null || value === undefined) return NO_DATA;
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: digits }).format(value);
}

export function formatDate(value?: string | null) {
  if (!value) return NO_DATA;
  return new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(value));
}

export function formatDateTime(value?: string | null) {
  if (!value) return NO_DATA;
  return new Intl.DateTimeFormat('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value));
}
