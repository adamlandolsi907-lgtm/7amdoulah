import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ADWYA Energy Intelligence",
  description: "Pipeline d'analyse documentaire et bilan CO₂ — Usine Pharmaceutique ADWYA",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" suppressHydrationWarning>
      <body className="antialiased">{children}</body>
    </html>
  );
}
