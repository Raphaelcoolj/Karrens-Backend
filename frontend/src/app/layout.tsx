import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Karren - Trading Signal Intelligence",
  description: "Private AI-powered trading signal analysis system",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
