import { afterEach, beforeEach, vi } from "vitest";
import { ApiError, NetworkError, TOKEN_KEY, isNotBuilt, request } from "@/lib/api";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

let assign: ReturnType<typeof vi.fn>;

beforeEach(() => {
  window.localStorage.clear();
  assign = vi.fn();
  Object.defineProperty(window, "location", { value: { assign }, writable: true });
});
afterEach(() => vi.unstubAllGlobals());

describe("request", () => {
  it("sends the bearer token", async () => {
    window.localStorage.setItem(TOKEN_KEY, "abc");
    const fetchMock = vi.fn().mockResolvedValue(json(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    await request("/api/v1/tickets");
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer abc");
  });

  it("401 clears the token and redirects to /login?reason=expired", async () => {
    window.localStorage.setItem(TOKEN_KEY, "old");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(401, { detail: "Invalid token" })));
    await expect(request("/api/v1/tickets")).rejects.toBeInstanceOf(ApiError);
    expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(assign).toHaveBeenCalledWith("/login?reason=expired");
  });

  it("a 401 on login (auth:false) does not redirect", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(401, { detail: "Bad" })));
    await expect(request("/api/v1/auth/demo-login", { method: "POST", auth: false })).rejects.toMatchObject({
      status: 401,
    });
    expect(assign).not.toHaveBeenCalled();
  });

  it("retries a GET after a network error, then succeeds", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("fail"))
      .mockResolvedValueOnce(json(200, { n: 1 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(request("/x", { retryDelayMs: 1 })).resolves.toEqual({ n: 1 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("gives up with NetworkError after the retries", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("down"));
    vi.stubGlobal("fetch", fetchMock);
    await expect(request("/x", { retries: 2, retryDelayMs: 1 })).rejects.toBeInstanceOf(NetworkError);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("never retries a POST (it could act twice)", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("down"));
    vi.stubGlobal("fetch", fetchMock);
    await expect(request("/x", { method: "POST", body: {}, retryDelayMs: 1 })).rejects.toBeInstanceOf(NetworkError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("surfaces the backend detail and detects unbuilt routes", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(404, { detail: "Not Found" })));
    const err = await request("/api/v1/dashboard/summary").catch((e) => e);
    expect(isNotBuilt(err)).toBe(true);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(404, { detail: "Ticket not found" })));
    const err2 = await request("/api/v1/tickets/x").catch((e) => e);
    expect(isNotBuilt(err2)).toBe(false);
    expect((err2 as ApiError).detail).toBe("Ticket not found");
  });
});
