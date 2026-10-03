const API_BASE_URL = import.meta.env.VITE_API_URL
if (!API_BASE_URL) {
  throw new Error("VITE_API_URL is not configured");
}
class ApiClient {
  private currentLanguage: string = "en";
  private currentToken: string | null = null;

  constructor() {
    this.currentLanguage = localStorage.getItem("relay_language") || "en";
    this.currentToken = localStorage.getItem("relay_token") || null;
  }

  setLanguage(lang: string) {
    this.currentLanguage = lang;
  }

  setToken(token: string | null) {
    this.currentToken = token;
    if (token) {
      localStorage.setItem("relay_token", token);
    } else {
      localStorage.removeItem("relay_token");
    }
  }

  getToken(): string | null {
    return this.currentToken || localStorage.getItem("relay_token");
  }

  private getHeaders(): HeadersInit {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    const token = this.getToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    headers["Accept-Language"] = this.currentLanguage;
    return headers;
  }

  async get<T>(endpoint: string): Promise<T> {
    const url = endpoint.startsWith("http") ? endpoint : `${API_BASE_URL}${endpoint}`;
    const res = await fetch(url, {
      method: "GET",
      headers: this.getHeaders(),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail?.message || err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  }

  async post<T>(endpoint: string, body?: any): Promise<T> {
    const url = endpoint.startsWith("http") ? endpoint : `${API_BASE_URL}${endpoint}`;
    const res = await fetch(url, {
      method: "POST",
      headers: this.getHeaders(),
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail?.message || err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  }

  async put<T>(endpoint: string, body?: any): Promise<T> {
    const url = endpoint.startsWith("http") ? endpoint : `${API_BASE_URL}${endpoint}`;
    const res = await fetch(url, {
      method: "PUT",
      headers: this.getHeaders(),
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail?.message || err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  }

  async delete<T>(endpoint: string): Promise<T> {
    const url = endpoint.startsWith("http") ? endpoint : `${API_BASE_URL}${endpoint}`;
    const res = await fetch(url, {
      method: "DELETE",
      headers: this.getHeaders(),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail?.message || err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  }

  createEventSourceUrl(endpoint: string): string {
    const url = endpoint.startsWith("http") ? endpoint : `${API_BASE_URL}${endpoint}`;
    const token = this.getToken();
    if (token) {
      const separator = url.includes("?") ? "&" : "?";
      return `${url}${separator}token=${encodeURIComponent(token)}`;
    }
    return url;
  }
}

export const apiClient = new ApiClient();
export const api = apiClient;
export { API_BASE_URL };
