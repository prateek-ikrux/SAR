const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function apiFetch<T>(
  path: string,
  options: { method?: string; body?: unknown; token?: string } = {},
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.token) headers.Authorization = `Bearer ${options.token}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method ?? "POST",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Could not reach the server. Check your connection and try again.");
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      // response body wasn't JSON — keep the generic message
    }
    throw new ApiError(response.status, detail);
  }

  return (await response.json()) as T;
}

export type MessageResponse = { message: string };

export type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
};

// FastAPI serializes with response_model_by_alias=True by default, so the
// wire format uses the Pydantic alias "_id", not the field name "id".
export type SearchResult = {
  _id: string;
  score: number;
  profile: Record<string, unknown>;
};

export type SearchResponse = {
  query: string;
  count: number;
  results: SearchResult[];
};

export function requestOtp(email: string): Promise<MessageResponse> {
  return apiFetch<MessageResponse>("/auth/request-otp", { body: { email } });
}

export function verifyOtp(email: string, otp: string): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/auth/verify-otp", { body: { email, otp } });
}

export function search(
  token: string,
  query: string,
  limit: number,
  numCandidates: number,
): Promise<SearchResponse> {
  return apiFetch<SearchResponse>("/search", {
    token,
    body: { query, limit, num_candidates: numCandidates },
  });
}
