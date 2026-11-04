import { Inter } from "next/font/google";
import "./globals.css";
import AppShell from "@/components/AppShell";

// 2026-11-03: application frame with sidebar, top bar and session guard (previous version: layout.jsx.bak_20261103).
const sans = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });

export const metadata = {
  title: "Intelligent Traffic Management Luxembourg",
  description: "Supervision et pilotage intelligent des feux de quatre carrefours de l'avenue J.F. Kennedy (Kirchberg).",
  icons: { icon: "/icon.svg" },
};

export const viewport = { themeColor: "#101D2E" };

export default function RootLayout({ children }) {
  return (
    <html lang="fr" className={sans.variable}>
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
