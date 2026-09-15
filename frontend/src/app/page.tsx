"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type { NavSection, AnalyzeResponse, StrategyDocument, TechnicalAnalysis, MarketCard, Candle } from "@/types";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { MobileNav } from "@/components/layout/MobileNav";
import { MarketOverview } from "@/components/dashboard/MarketOverview";
import { PriceChart } from "@/components/dashboard/PriceChart";
import { SignalPanel } from "@/components/dashboard/SignalPanel";
import { MarketAnalysis } from "@/components/dashboard/MarketAnalysis";
import { StrategyContext } from "@/components/dashboard/StrategyContext";
import { AnalysisHistory } from "@/components/dashboard/AnalysisHistory";
import { AnalyzeModal } from "@/components/dashboard/AnalyzeModal";
import { LoadingState, EmptyState, ErrorState, NoSignalState } from "@/components/dashboard/States";
import { analyze, listStrategies, listAnalyses, getMarketData, getMarketQuote, uploadStrategy } from "@/lib/api";
import { computeTA } from "@/lib/computeTA";
import type { AnalysisResult } from "@/types";

const WATCHLIST: Array<{ symbol: string; displayName: string }> = [
  { symbol: "BTCUSD", displayName: "BTC/USD" },
  { symbol: "ETHUSD", displayName: "ETH/USD" },
  { symbol: "EURUSD", displayName: "EUR/USD" },
  { symbol: "GBPUSD", displayName: "GBP/USD" },
  { symbol: "XAUUSD", displayName: "GOLD" },
  { symbol: "SOLUSD", displayName: "SOL/USD" },
];

export default function Dashboard() {
  const [nav, setNav] = useState<NavSection>("overview");
  const [selectedSymbol, setSelectedSymbol] = useState("BTCUSD");
  const [selectedDisplayName, setSelectedDisplayName] = useState("BTC/USD");
  const [timeframe, setTimeframe] = useState("4H");
  const [showAnalyzeModal, setShowAnalyzeModal] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [signal, setSignal] = useState<AnalyzeResponse | null>(null);
  const [strategies, setStrategies] = useState<StrategyDocument[]>([]);
  const [analyses, setAnalyses] = useState<AnalysisResult[]>([]);
  const [technicalAnalysis, setTechnicalAnalysis] = useState<TechnicalAnalysis | null>(null);
  const [markets, setMarkets] = useState<MarketCard[]>([]);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [activeStrategy, setActiveStrategy] = useState<StrategyDocument | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const stepTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    listStrategies()
      .then((s) => {
        setStrategies(s);
        if (s.length > 0) setActiveStrategy(s[0]);
      })
      .catch(() => {});
    listAnalyses({ limit: 10 })
      .then((a) => { if (a.length > 0) setAnalyses(a); })
      .catch(() => {});

    (async () => {
      const results: MarketCard[] = [];
      for (const item of WATCHLIST) {
        try {
          const q = await getMarketQuote(item.symbol);
          const price = q.bid ?? q.ask ?? 0;
          results.push({ symbol: item.symbol, displayName: item.displayName, price, change: 0, changePct: 0 });
        } catch {
          results.push({ symbol: item.symbol, displayName: item.displayName, price: 0, change: 0, changePct: 0 });
        }
      }
      setMarkets(results);

      try {
        const snap = await getMarketData("BTCUSD", "4h");
        setCandles(snap.candles);
        const ta = computeTA(snap.candles);
        if (ta) setTechnicalAnalysis(ta);
        const price = snap.quote?.bid ?? snap.quote?.ask ?? (snap.candles.length > 0 ? snap.candles[snap.candles.length - 1].close : 0);
        setMarkets((prev) => prev.map((m) => m.symbol === "BTCUSD" ? { ...m, price } : m));
      } catch {
        // Backend may not be running
      }
    })();
  }, []);

  const loadMarketData = useCallback(async (symbol: string, interval: string) => {
    try {
      const snap = await getMarketData(symbol, interval);
      setCandles(snap.candles);
      const ta = computeTA(snap.candles);
      if (ta) setTechnicalAnalysis(ta);
      const price = snap.quote?.bid ?? snap.quote?.ask ?? (snap.candles.length > 0 ? snap.candles[snap.candles.length - 1].close : 0);
      setMarkets((prev) => {
        const idx = prev.findIndex((m) => m.symbol === symbol);
        if (idx >= 0) {
          const updated = [...prev];
          const old = updated[idx];
          const change = price - old.price;
          const changePct = old.price > 0 ? (change / old.price) * 100 : 0;
          updated[idx] = { ...old, price, change, changePct };
          return updated;
        }
        return [...prev, { symbol, displayName: symbol, price, change: 0, changePct: 0 }];
      });
    } catch {
      // Backend may not be running
    }
  }, []);

  const handlePairSelect = useCallback((symbol: string, displayName: string) => {
    setSelectedSymbol(symbol);
    setSelectedDisplayName(displayName);
    setError(null);
    setSignal(null);
    setTechnicalAnalysis(null);
    setCandles([]);
    loadMarketData(symbol, timeframe.toLowerCase());
  }, [timeframe, loadMarketData]);

  const handleTimeframeChange = useCallback((tf: string) => {
    setTimeframe(tf);
    setSignal(null);
    loadMarketData(selectedSymbol, tf.toLowerCase());
  }, [selectedSymbol, loadMarketData]);

  const handleAnalyze = useCallback(async (pair: string, tf: string) => {
    setShowAnalyzeModal(false);
    setLoading(true);
    setError(null);
    setSignal(null);
    setLoadingStep(0);

    stepTimer.current = setInterval(() => {
      setLoadingStep((prev) => Math.min(prev + 1, 3));
    }, 1500);

    try {
      const res = await analyze({ pair, timeframe: tf.toLowerCase() });
      setSignal(res);

      const newEntry: AnalysisResult = {
        id: `local-${Date.now()}`,
        pair: res.pair,
        timeframe: res.timeframe,
        strategy_id: null,
        market_data_snapshot: {},
        technical_analysis: {},
        strategy_context: null,
        ai_reasoning: res.reasoning,
        signal: {
          pair: res.pair,
          timeframe: res.timeframe,
          direction: res.direction,
          entry: res.entry,
          stop_loss: res.stop_loss,
          take_profit: res.take_profit,
          risk_reward: res.risk_reward,
          confidence: res.confidence,
          reasoning: res.reasoning,
          triggered_conditions: res.triggered_conditions,
          invalidating_conditions: res.invalidating_conditions,
          strategy_alignment: res.strategy_alignment,
          market_context: res.market_context,
        },
        timestamp: new Date().toISOString(),
        model_provider: res.model_provider,
        model_name: null,
        processing_time_ms: res.processing_time_ms,
      };
      setAnalyses((prev) => [newEntry, ...prev].slice(0, 20));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Analysis failed. Is the backend running?";
      setError(msg);
    } finally {
      if (stepTimer.current) clearInterval(stepTimer.current);
      setLoading(false);
      setLoadingStep(0);
    }
  }, []);

  const handleUpload = useCallback(async (file: File, name: string) => {
    setUploading(true);
    setUploadError(null);
    try {
      await uploadStrategy(file, name);
      const s = await listStrategies();
      setStrategies(s);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }, []);

  const market = markets.find((m) => m.symbol === selectedSymbol) ?? { symbol: selectedSymbol, displayName: selectedDisplayName, price: 0, change: 0, changePct: 0 };

  return (
    <div className="app-layout">
      <Sidebar activeSection={nav} onNavigate={setNav} />

      <div className="main-workspace">
        <Header onPairSelect={handlePairSelect} />

        <div className="main-content">
          {nav === "overview" && (
            <>
              <MarketOverview markets={markets} selectedSymbol={selectedSymbol} onSelect={handlePairSelect} />

              <PriceChart
                pair={selectedSymbol}
                displayName={selectedDisplayName}
                price={market.price}
                change={market.change}
                changePct={market.changePct}
                timeframe={timeframe}
                candles={candles}
                onTimeframeChange={handleTimeframeChange}
              />

              <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
                <button className="btn btn-primary btn-lg" onClick={() => setShowAnalyzeModal(true)} disabled={loading}>
                  {loading ? "Analyzing..." : `Analyze ${selectedDisplayName}`}
                </button>
              </div>

              {loading && <LoadingState currentStep={loadingStep} />}
              {error && <ErrorState message={error} onRetry={() => { setError(null); setShowAnalyzeModal(true); }} />}
              {!loading && !error && signal && signal.direction === "NO SIGNAL" && <NoSignalState />}
              {!loading && !error && signal && signal.direction !== "NO SIGNAL" && <SignalPanel signal={signal} />}

              {technicalAnalysis && <MarketAnalysis ta={technicalAnalysis} />}

              <AnalysisHistory analyses={analyses} />
            </>
          )}

          {nav === "markets" && (
            <>
              <MarketOverview markets={markets} selectedSymbol={selectedSymbol} onSelect={handlePairSelect} />

              <PriceChart
                pair={selectedSymbol}
                displayName={selectedDisplayName}
                price={market.price}
                change={market.change}
                changePct={market.changePct}
                timeframe={timeframe}
                candles={candles}
                onTimeframeChange={handleTimeframeChange}
              />

              <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
                <button className="btn btn-primary" onClick={() => setShowAnalyzeModal(true)} disabled={loading}>
                  {loading ? "Analyzing..." : `Analyze ${selectedDisplayName}`}
                </button>
              </div>

              {loading && <LoadingState currentStep={loadingStep} />}
              {error && <ErrorState message={error} onRetry={() => { setError(null); setShowAnalyzeModal(true); }} />}
              {!loading && !error && signal && signal.direction === "NO SIGNAL" && <NoSignalState />}
              {!loading && !error && signal && signal.direction !== "NO SIGNAL" && <SignalPanel signal={signal} />}

              {technicalAnalysis && <MarketAnalysis ta={technicalAnalysis} />}

              <div className="analysis-section" style={{ marginTop: 12 }}>
                <div className="analysis-section-title">Candle Data</div>
                {candles.length > 0 ? (
                  <div className="data-table-container">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Time</th>
                          <th>Open</th>
                          <th>High</th>
                          <th>Low</th>
                          <th>Close</th>
                          <th>Volume</th>
                        </tr>
                      </thead>
                      <tbody>
                        {candles.slice(-20).reverse().map((c, i) => (
                          <tr key={i}>
                            <td>{new Date(c.timestamp).toLocaleString()}</td>
                            <td className="numeric">{c.open.toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
                            <td className="numeric">{c.high.toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
                            <td className="numeric">{c.low.toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
                            <td className="numeric">{c.close.toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
                            <td className="numeric">{c.volume.toLocaleString()}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)", fontSize: 12 }}>
                    No candle data available
                  </div>
                )}
              </div>
            </>
          )}

          {nav === "signals" && (
            <>
              <div style={{ marginBottom: 20 }}>
                <button className="btn btn-primary btn-lg" onClick={() => setShowAnalyzeModal(true)} disabled={loading}>
                  {loading ? "Analyzing..." : `Analyze ${selectedDisplayName}`}
                </button>
              </div>

              {loading && <LoadingState currentStep={loadingStep} />}
              {error && <ErrorState message={error} onRetry={() => { setError(null); setShowAnalyzeModal(true); }} />}
              {!loading && !error && !signal && <EmptyState />}
              {!loading && !error && signal && signal.direction === "NO SIGNAL" && <NoSignalState />}
              {!loading && !error && signal && signal.direction !== "NO SIGNAL" && <SignalPanel signal={signal} />}
            </>
          )}

          {nav === "strategies" && (
            <>
              <div className="analysis-section">
                <div className="analysis-section-title">Strategies</div>

                <div style={{ marginBottom: 16 }}>
                  <label className="btn btn-secondary" style={{ cursor: "pointer" }}>
                    {uploading ? "Uploading..." : "Upload Strategy"}
                    <input
                      type="file"
                      accept=".pdf,.txt,.md"
                      style={{ display: "none" }}
                      onChange={async (e) => {
                        const file = e.target.files?.[0];
                        if (file) {
                          const name = file.name.replace(/\.[^.]+$/, "");
                          await handleUpload(file, name);
                        }
                      }}
                      disabled={uploading}
                    />
                  </label>
                  {uploadError && <span style={{ color: "var(--red-primary)", fontSize: 12, marginLeft: 8 }}>{uploadError}</span>}
                </div>

                {strategies.length === 0 ? (
                  <div className="empty-state" style={{ padding: 30 }}>
                    <div className="empty-state-title" style={{ fontSize: 13 }}>No strategies uploaded</div>
                    <div className="empty-state-text" style={{ fontSize: 12 }}>Upload a PDF, TXT, or MD strategy document.</div>
                  </div>
                ) : (
                  strategies.map((s) => (
                    <div
                      key={s.id}
                      className={`analysis-row ${activeStrategy?.id === s.id ? "selected" : ""}`}
                      style={{ cursor: "pointer" }}
                      onClick={() => setActiveStrategy(s)}
                    >
                      <span className="analysis-row-label" style={{ fontWeight: 600, color: "var(--text-primary)" }}>{s.name}</span>
                      <span className="analysis-row-value">{s.source_type.toUpperCase()} · v{s.version}</span>
                    </div>
                  ))
                )}
              </div>
              <StrategyContext strategy={activeStrategy} />
            </>
          )}

          {nav === "history" && <AnalysisHistory analyses={analyses} />}
        </div>
      </div>

      <MobileNav activeSection={nav} onNavigate={setNav} />

      {showAnalyzeModal && (
        <AnalyzeModal
          selectedPair={selectedSymbol}
          selectedDisplayName={selectedDisplayName}
          onAnalyze={handleAnalyze}
          onClose={() => setShowAnalyzeModal(false)}
          loading={loading}
        />
      )}
    </div>
  );
}
