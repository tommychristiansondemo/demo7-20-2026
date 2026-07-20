/**
 * Centralized API client with request/response interceptors.
 *
 * Provides:
 * - Automatic auth header injection from session token
 * - Token expiration handling (redirect to /signin on 401)
 * - Network error handling with retry logic (exponential backoff, max 3 retries)
 */

export interface ApiClientConfig {
  baseUrl: string;
  getSessionToken: () => string | null;
  onUnauthorized: () => void;
}

export interface RequestOptions extends Omit<RequestInit, "headers"> {
  headers?: Record<string, string>;
  /** Skip automatic auth header injection */
  skipAuth?: boolean;
  /** Number of retry attempts for network errors (default: 3) */
  maxRetries?: number;
  /** Timeout in milliseconds (default: 30000) */
  timeout?: number;
}

export interface ApiError {
  status: number;
  message: string;
  details?: unknown;
}

export class ApiRequestError extends Error {
  public readonly status: number;
  public readonly details?: unknown;

  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.details = details;
  }
}

export class NetworkError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NetworkError";
  }
}

const DEFAULT_BASE_URL = "/api";
const DEFAULT_MAX_RETRIES = 3;
const DEFAULT_TIMEOUT_MS = 30000;
const BASE_RETRY_DELAY_MS = 500;

let clientConfig: ApiClientConfig = {
  baseUrl: DEFAULT_BASE_URL,
  getSessionToken: () => null,
  onUnauthorized: () => {},
};

/**
 * Configure the API client with auth token provider and unauthorized handler.
 */
export function configureApiClient(config: Partial<ApiClientConfig>) {
  clientConfig = { ...clientConfig, ...config };
}

/**
 * Get the current API client configuration (useful for testing).
 */
export function getApiClientConfig(): ApiClientConfig {
  return { ...clientConfig };
}

function buildHeaders(options: RequestOptions): Record<string, string> {
  const headers: Record<string, string> = { ...options.headers };

  if (!options.skipAuth) {
    const token = clientConfig.getSessionToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  return headers;
}

async function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function getRetryDelay(attempt: number): number {
  // Exponential backoff: 500ms, 1000ms, 2000ms
  return BASE_RETRY_DELAY_MS * Math.pow(2, attempt);
}

function isRetryableError(error: unknown): boolean {
  // Network errors (fetch throws TypeError for network failures)
  if (error instanceof TypeError) return true;
  // AbortError from timeout should not be retried
  if (error instanceof DOMException && error.name === "AbortError") return false;
  return false;
}

function isRetryableStatus(status: number): boolean {
  // Retry on 502, 503, 504 (server temporarily unavailable)
  return status === 502 || status === 503 || status === 504;
}

/**
 * Make an API request with automatic auth injection, retry logic, and error handling.
 */
export async function apiRequest<T = unknown>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const maxRetries = options.maxRetries ?? DEFAULT_MAX_RETRIES;
  const timeout = options.timeout ?? DEFAULT_TIMEOUT_MS;
  const url = `${clientConfig.baseUrl}${path}`;

  // Extract custom options that shouldn't be passed to fetch
  const { skipAuth: _, maxRetries: _mr, timeout: _to, ...fetchOptions } = options;

  let lastError: unknown;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    // Merge signals: use caller's signal if provided
    const signal = options.signal
      ? combineSignals(options.signal, controller.signal)
      : controller.signal;

    try {
      const headers = buildHeaders(options);
      const response = await fetch(url, {
        ...fetchOptions,
        headers,
        signal,
      });

      clearTimeout(timeoutId);

      // Handle 401 - token expired
      if (response.status === 401) {
        clientConfig.onUnauthorized();
        throw new ApiRequestError(401, "Session expired. Please sign in again.");
      }

      // Handle retryable server errors
      if (isRetryableStatus(response.status) && attempt < maxRetries) {
        lastError = new ApiRequestError(
          response.status,
          `Server error (${response.status})`
        );
        await delay(getRetryDelay(attempt));
        continue;
      }

      // Handle other error responses
      if (!response.ok) {
        let errorBody: unknown;
        try {
          errorBody = await response.json();
        } catch {
          // Response body isn't JSON
        }
        const message =
          (errorBody as { message?: string })?.message ||
          (errorBody as { error?: string })?.error ||
          `Request failed with status ${response.status}`;
        throw new ApiRequestError(response.status, message, errorBody);
      }

      // Parse successful response
      const contentType = response.headers.get("content-type");
      if (contentType?.includes("application/json")) {
        return (await response.json()) as T;
      }

      // Return empty object for non-JSON responses (e.g., 204 No Content)
      return {} as T;
    } catch (error: unknown) {
      clearTimeout(timeoutId);

      // Don't retry if caller aborted
      if (options.signal?.aborted) {
        throw error;
      }

      // Don't retry API errors (already handled above)
      if (error instanceof ApiRequestError) {
        throw error;
      }

      // Retry on network errors
      if (isRetryableError(error) && attempt < maxRetries) {
        lastError = error;
        await delay(getRetryDelay(attempt));
        continue;
      }

      // Timeout
      if (
        error instanceof DOMException &&
        error.name === "AbortError"
      ) {
        throw new NetworkError(
          "Request timed out. Please check your connection and try again."
        );
      }

      // Non-retryable network error or exhausted retries
      throw new NetworkError(
        "Network error. Please check your connection and try again."
      );
    }
  }

  // Exhausted all retries
  if (lastError instanceof ApiRequestError) {
    throw lastError;
  }
  throw new NetworkError(
    "Request failed after multiple attempts. Please try again later."
  );
}

/**
 * Convenience methods for common HTTP verbs.
 */
export const api = {
  get<T = unknown>(path: string, options?: RequestOptions): Promise<T> {
    return apiRequest<T>(path, { ...options, method: "GET" });
  },

  post<T = unknown>(
    path: string,
    body?: unknown,
    options?: RequestOptions
  ): Promise<T> {
    return apiRequest<T>(path, {
      ...options,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  },

  put<T = unknown>(
    path: string,
    body?: unknown,
    options?: RequestOptions
  ): Promise<T> {
    return apiRequest<T>(path, {
      ...options,
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  },

  delete<T = unknown>(path: string, options?: RequestOptions): Promise<T> {
    return apiRequest<T>(path, { ...options, method: "DELETE" });
  },
};

/**
 * Combine two AbortSignals - aborts when either signal is aborted.
 */
function combineSignals(
  userSignal: AbortSignal,
  timeoutSignal: AbortSignal
): AbortSignal {
  const controller = new AbortController();

  const abort = () => controller.abort();

  if (userSignal.aborted || timeoutSignal.aborted) {
    controller.abort();
    return controller.signal;
  }

  userSignal.addEventListener("abort", abort, { once: true });
  timeoutSignal.addEventListener("abort", abort, { once: true });

  return controller.signal;
}
