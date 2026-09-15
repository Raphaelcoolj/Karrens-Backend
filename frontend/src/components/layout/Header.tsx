"use client";

import { useState, useRef, useEffect } from "react";
import type { Instrument } from "@/types";
import { searchPairs } from "@/lib/api";

interface HeaderProps {
  onPairSelect: (symbol: string, displayName: string) => void;
}

export function Header({ onPairSelect }: HeaderProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Instrument[]>([]);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSearch = async (value: string) => {
    setQuery(value);
    if (value.length < 2) {
      setResults([]);
      setOpen(false);
      return;
    }
    try {
      const data = await searchPairs(value);
      setResults(data);
      setOpen(data.length > 0);
    } catch {
      setResults([]);
    }
  };

  const handleSelect = (inst: Instrument) => {
    setQuery(inst.display_name);
    setOpen(false);
    setResults([]);
    onPairSelect(inst.symbol, inst.display_name);
  };

  return (
    <header className="header">
      <div className="header-left">
        <h2>Market Intelligence</h2>
        <p>AI-powered market analysis and signal validation</p>
      </div>
      <div className="header-right">
        <div ref={ref} style={{ position: "relative" }}>
          <input
            className="input"
            value={query}
            onChange={(e) => handleSearch(e.target.value)}
            onFocus={() => results.length > 0 && setOpen(true)}
            placeholder="Search market..."
            style={{ width: 220 }}
          />
          {open && results.length > 0 && (
            <div className="search-dropdown">
              {results.map((inst) => (
                <div
                  key={inst.symbol}
                  className="search-dropdown-item"
                  onClick={() => handleSelect(inst)}
                >
                  <span className="search-dropdown-item-name">{inst.display_name}</span>
                  <span className="search-dropdown-item-class">{inst.asset_class}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--text-tertiary)" }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--green-primary)", display: "inline-block" }} />
          Live
        </div>
      </div>
    </header>
  );
}
