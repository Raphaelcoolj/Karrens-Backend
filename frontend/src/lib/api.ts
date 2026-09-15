import type {
  Instrument,
  Quote,
  MarketSnapshot,
  AnalyzeRequest,
  AnalyzeResponse,
  StrategyDocument,
  AnalysisResult,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Request failed: ${res.status}`);
  }
  return res.json();
}

export async function searchPairs(query: string): Promise<Instrument[]> {
  if (!query || query.length < 1) return [];
  return request<Instrument[]>(
    `${API_BASE}/api/markets/search?q=${encodeURIComponent(query)}`
  );
}

export async function getMarketQuote(symbol: string): Promise<Quote> {
  return request<Quote>(`${API_BASE}/api/markets/${encodeURIComponent(symbol)}`);
}

export async function getMarketData(
  symbol: string,
  interval: string = "4h",
  limit: number = 200
): Promise<MarketSnapshot> {
  return request<MarketSnapshot>(
    `${API_BASE}/api/markets/${encodeURIComponent(symbol)}/data?interval=${interval}&limit=${limit}`
  );
}

export async function analyze(payload: AnalyzeRequest): Promise<AnalyzeResponse> {
  return request<AnalyzeResponse>(`${API_BASE}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function listStrategies(): Promise<StrategyDocument[]> {
  return request<StrategyDocument[]>(`${API_BASE}/api/strategies`);
}

export async function getStrategy(strategyId: string): Promise<StrategyDocument> {
  return request<StrategyDocument>(
    `${API_BASE}/api/strategies/${encodeURIComponent(strategyId)}`
  );
}

export async function uploadStrategy(
  file: File,
  name: string
): Promise<{ id: string; name: string; status: string; metadata: Record<string, unknown> }> {
  const form = new FormData();
  form.append("file", file);
  return request(
    `${API_BASE}/api/strategies/upload?name=${encodeURIComponent(name)}`,
    { method: "POST", body: form }
  );
}

export async function createStrategyFromText(
  name: string,
  text: string
): Promise<{ id: string; name: string; status: string; metadata: Record<string, unknown> }> {
  return request(
    `${API_BASE}/api/strategies/text?name=${encodeURIComponent(name)}&text=${encodeURIComponent(text)}`,
    { method: "POST" }
  );
}

export async function listAnalyses(params?: {
  pair?: string;
  timeframe?: string;
  limit?: number;
  skip?: number;
}): Promise<AnalysisResult[]> {
  const query = new URLSearchParams();
  if (params?.pair) query.set("pair", params.pair);
  if (params?.timeframe) query.set("timeframe", params.timeframe);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.skip) query.set("skip", String(params.skip));
  const qs = query.toString();
  return request<AnalysisResult[]>(
    `${API_BASE}/api/analyses${qs ? `?${qs}` : ""}`
  );
}

export async function getAnalysis(id: string): Promise<AnalysisResult> {
  return request<AnalysisResult>(
    `${API_BASE}/api/analyses/${encodeURIComponent(id)}`
  );
}

export async function checkHealth(): Promise<{ status: string }> {
  return request<{ status: string }>(`${API_BASE}/health`);
}
