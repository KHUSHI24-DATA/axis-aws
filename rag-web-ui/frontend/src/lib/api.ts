interface FetchOptions extends Omit<RequestInit, 'body' | 'headers'> {
  data?: any;
  headers?: Record<string, string>;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

function parseApiErrorBody(errorData: unknown, status: number): string {
  if (!errorData || typeof errorData !== 'object') {
    return `Request failed (${status})`;
  }

  const data = errorData as Record<string, unknown>;

  if (typeof data.detail === 'string' && data.detail.trim()) {
    return data.detail;
  }

  if (Array.isArray(data.detail)) {
    const messages = data.detail
      .map((item) => {
        if (!item || typeof item !== 'object') {
          return String(item);
        }
        const entry = item as Record<string, unknown>;
        if (typeof entry.msg === 'string') {
          return entry.msg;
        }
        if (typeof entry.message === 'string') {
          return entry.message;
        }
        return JSON.stringify(entry);
      })
      .filter(Boolean);
    if (messages.length > 0) {
      return messages.join('; ');
    }
  }

  if (typeof data.message === 'string' && data.message.trim()) {
    return data.message;
  }

  if (typeof data.error === 'string' && data.error.trim()) {
    return data.error;
  }

  return `Request failed (${status})`;
}

async function readErrorMessage(response: Response): Promise<string> {
  const contentType = response.headers.get('content-type') || '';

  if (contentType.includes('application/json')) {
    try {
      const errorData = await response.json();
      return parseApiErrorBody(errorData, response.status);
    } catch {
      return `Request failed (${response.status})`;
    }
  }

  try {
    const text = (await response.text()).trim();
    if (!text) {
      if (response.status >= 500) {
        return `Server error (${response.status}). The backend may be unavailable or still starting.`;
      }
      return `Request failed (${response.status})`;
    }

    if (text.startsWith('{') || text.startsWith('[')) {
      try {
        return parseApiErrorBody(JSON.parse(text), response.status);
      } catch {
        // Fall through to plain-text handling.
      }
    }

    return text.length > 500 ? `${text.slice(0, 500)}...` : text;
  } catch {
    return `Request failed (${response.status})`;
  }
}

export async function fetchApi(fullUrl: string, options: FetchOptions = {}) {
  const { data, headers: customHeaders = {}, ...restOptions } = options;

  const headers: Record<string, string> = {
    ...customHeaders,
  };

  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('token');
    if (token && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  }

  // Auto set JSON content type
  if (!headers['Content-Type'] && data && !(data instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const config: RequestInit = {
    ...restOptions,
    headers,
  };

  // Handle body
  if (data) {
    if (data instanceof FormData) {
      config.body = data;
    } else if (headers['Content-Type'] === 'application/json') {
      config.body = JSON.stringify(data);
    } else if (headers['Content-Type'] === 'application/x-www-form-urlencoded') {
      config.body =
        typeof data === 'string'
          ? data
          : new URLSearchParams(data).toString();
    } else {
      config.body = data;
    }
  }

  try {
    const response = await fetch(fullUrl, config);

    if (response.status === 401) {
      console.error('Unauthorized request');
      throw new ApiError(401, 'Unauthorized');
    }

    if (!response.ok) {
      const message = await readErrorMessage(response);
      throw new ApiError(response.status, message);
    }

    if (response.status === 204) {
      return null;
    }

    const responseType = response.headers.get('content-type') || '';
    if (responseType.includes('application/json')) {
      return await response.json();
    }

    return await response.text();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      500,
      'Network error or server is unreachable. Check that the backend is running.'
    );
  }
}

// Helper methods for common HTTP methods
export const api = {
  get: (url: string, options?: Omit<FetchOptions, 'method'>) =>
    fetchApi(url, { ...options, method: 'GET' }),

  post: (url: string, data?: any, options?: Omit<FetchOptions, 'method'>) =>
    fetchApi(url, { ...options, method: 'POST', data }),

  put: (url: string, data?: any, options?: Omit<FetchOptions, 'method'>) =>
    fetchApi(url, { ...options, method: 'PUT', data }),

  delete: (url: string, options?: Omit<FetchOptions, 'method'>) =>
    fetchApi(url, { ...options, method: 'DELETE' }),

  patch: (url: string, data?: any, options?: Omit<FetchOptions, 'method'>) =>
    fetchApi(url, { ...options, method: 'PATCH', data }),
};
