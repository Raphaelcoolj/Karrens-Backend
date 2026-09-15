"use client";

import type { NavSection } from "@/types";

interface MobileNavProps {
  activeSection: NavSection;
  onNavigate: (section: NavSection) => void;
}

const NAV_ITEMS: Array<{ id: NavSection; label: string; icon: string }> = [
  { id: "overview", label: "Overview", icon: "M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0a1 1 0 01-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 01-1 1" },
  { id: "markets", label: "Markets", icon: "M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" },
  { id: "signals", label: "Signals", icon: "M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" },
  { id: "strategies", label: "Strategies", icon: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" },
  { id: "history", label: "History", icon: "M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" },
];

export function MobileNav({ activeSection, onNavigate }: MobileNavProps) {
  return (
    <nav className="mobile-nav">
      <div className="mobile-nav-items">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            className={`mobile-nav-item ${activeSection === item.id ? "active" : ""}`}
            onClick={() => onNavigate(item.id)}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
              <path d={item.icon} />
            </svg>
            {item.label}
          </button>
        ))}
      </div>
    </nav>
  );
}
