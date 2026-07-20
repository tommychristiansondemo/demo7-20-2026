import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  configureApiClient,
  apiRequest,
  api,
  ApiRequestError,
  NetworkError,
} from "./client";

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

describe("API Client", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    configureApiClient({
      baseUrl: "/api",
      getSessionToken: () => "test-session-token",
      onUnauthorized: vi.fn(),
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("configureApiClient", () => {
    it("uses configured baseUrl in requests", async () => {
      configureApiClient({
        baseUrl: "/custom-api",
        getSessionToken: () => "token",
        onUnauthorized: () => {},
      });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ data: "test" }),
      });

      await apiRequest("/users");

      expect(mockFetch).toHaveBeenCalledWith(
        "/custom-api/users",
        expect.any(Object)
      );
    });
  });

  describe("auth header injection", () => {
    it("injects Authorization header from session token", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({}),
      });

      await apiRequest("/test");

      expect(mockFetch).toHaveBeenCalledWith(
        "/api/test",
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: "Bearer test-session-token",
          }),
        })
      );
    });

    it("skips auth header when skipAuth is true", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({}),
      });

      await apiRequest("/test", { skipAuth: true });

      const callHeaders = mockFetch.mock.calls[0][1].headers;
      expect(callHeaders.Authorization).toBeUndefined();
    });

    it("does not inject header when session token is null", async () => {
      configureApiClient({
        baseUrl: "/api",
        getSessionToken: () => null,
        onUnauthorized: () => {},
      });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({}),
      });

      await apiRequest("/test");

      const callHeaders = mockFetch.mock.calls[0][1].headers;
      expect(callHeaders.Authorization).toBeUndefined();
    });
  });

  describe("401 handling", () => {
    it("calls onUnauthorized and throws ApiRequestError on 401", async () => {
      const onUnauthorized = vi.fn();
      configureApiClient({
        baseUrl: "/api",
        getSessionToken: () => "expired-token",
        onUnauthorized,
      });

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ message: "Unauthorized" }),
      });

      await expect(apiRequest("/protected")).rejects.toThrow(ApiRequestError);
      expect(onUnauthorized).toHaveBeenCalledOnce();
    });

    it("throws with 'Session expired' message on 401", async () => {
      configureApiClient({
        baseUrl: "/api",
        getSessionToken: () => "token",
        onUnauthorized: () => {},
      });

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({}),
      });

      await expect(apiRequest("/test")).rejects.toThrow(
        "Session expired. Please sign in again."
      );
    });
  });

  describe("error handling", () => {
    it("throws ApiRequestError with message from response body", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ message: "Validation failed" }),
      });

      await expect(apiRequest("/test", { maxRetries: 0 })).rejects.toThrow(
        "Validation failed"
      );
    });

    it("throws ApiRequestError with error field from response body", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ error: "Not found" }),
      });

      await expect(apiRequest("/test", { maxRetries: 0 })).rejects.toThrow(
        "Not found"
      );
    });

    it("throws NetworkError on network failure", async () => {
      mockFetch.mockRejectedValue(new TypeError("Failed to fetch"));

      await expect(apiRequest("/test", { maxRetries: 0 })).rejects.toThrow(
        NetworkError
      );
    });

    it("throws NetworkError on timeout", async () => {
      vi.useFakeTimers();

      let rejectFetch: ((reason: unknown) => void) | null = null;

      mockFetch.mockImplementation(
        (_url: string, opts?: { signal?: AbortSignal }) =>
          new Promise((_, reject) => {
            rejectFetch = reject;
            if (opts?.signal?.aborted) {
              reject(new DOMException("Aborted", "AbortError"));
              return;
            }
            opts?.signal?.addEventListener("abort", () => {
              reject(new DOMException("Aborted", "AbortError"));
            });
          })
      );

      const promise = apiRequest("/test", { timeout: 1000, maxRetries: 0 });

      // Advance timers to trigger the abort
      vi.advanceTimersByTime(1100);

      await expect(promise).rejects.toThrow(/timed out/i);

      vi.useRealTimers();
    });
  });

  describe("retry logic", () => {
    it("retries on 503 status and succeeds on retry", async () => {
      vi.useFakeTimers();

      mockFetch
        .mockResolvedValueOnce({
          ok: false,
          status: 503,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ message: "Service unavailable" }),
        })
        .mockResolvedValueOnce({
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ result: "success" }),
        });

      const promise = apiRequest("/test", { maxRetries: 1 });

      // Advance past the first retry delay (500ms)
      await vi.advanceTimersByTimeAsync(600);

      const result = await promise;
      expect(result).toEqual({ result: "success" });
      expect(mockFetch).toHaveBeenCalledTimes(2);

      vi.useRealTimers();
    });

    it("retries on network errors with exponential backoff", async () => {
      vi.useFakeTimers();

      mockFetch
        .mockRejectedValueOnce(new TypeError("Network error"))
        .mockRejectedValueOnce(new TypeError("Network error"))
        .mockResolvedValueOnce({
          ok: true,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ data: "ok" }),
        });

      const promise = apiRequest("/test", { maxRetries: 2 });

      // First retry delay: 500ms
      await vi.advanceTimersByTimeAsync(600);
      // Second retry delay: 1000ms
      await vi.advanceTimersByTimeAsync(1100);

      const result = await promise;
      expect(result).toEqual({ data: "ok" });
      expect(mockFetch).toHaveBeenCalledTimes(3);

      vi.useRealTimers();
    });

    it("does not retry on 400 errors", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ message: "Bad request" }),
      });

      await expect(apiRequest("/test", { maxRetries: 3 })).rejects.toThrow(
        "Bad request"
      );
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    it("does not retry on 401 errors", async () => {
      configureApiClient({
        baseUrl: "/api",
        getSessionToken: () => "token",
        onUnauthorized: () => {},
      });

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({}),
      });

      await expect(apiRequest("/test", { maxRetries: 3 })).rejects.toThrow(
        ApiRequestError
      );
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });
  });

  describe("convenience methods", () => {
    it("api.get sends GET request", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ items: [] }),
      });

      const result = await api.get("/items");

      expect(mockFetch).toHaveBeenCalledWith(
        "/api/items",
        expect.objectContaining({ method: "GET" })
      );
      expect(result).toEqual({ items: [] });
    });

    it("api.post sends POST request with JSON body", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ id: "123" }),
      });

      const result = await api.post("/items", { name: "test" });

      expect(mockFetch).toHaveBeenCalledWith(
        "/api/items",
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({
            "Content-Type": "application/json",
          }),
          body: JSON.stringify({ name: "test" }),
        })
      );
      expect(result).toEqual({ id: "123" });
    });

    it("api.delete sends DELETE request", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({}),
      });

      await api.delete("/items/123");

      expect(mockFetch).toHaveBeenCalledWith(
        "/api/items/123",
        expect.objectContaining({ method: "DELETE" })
      );
    });
  });

  describe("response parsing", () => {
    it("parses JSON response when content-type is application/json", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json; charset=utf-8" }),
        json: async () => ({ data: "value" }),
      });

      const result = await apiRequest("/test");
      expect(result).toEqual({ data: "value" });
    });

    it("returns empty object for non-JSON responses", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "text/plain" }),
      });

      const result = await apiRequest("/test");
      expect(result).toEqual({});
    });
  });
});
