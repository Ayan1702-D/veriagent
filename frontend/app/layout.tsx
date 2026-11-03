import type { Metadata } from "next";
import { Suspense } from "react";
import { Barlow_Condensed, JetBrains_Mono, Source_Serif_4 } from "next/font/google";
import { AppHeader } from "@/components/AppHeader";
import "./globals.css";

const serif = Source_Serif_4({ subsets: ["latin"], variable: "--font-serif" });
const condensed = Barlow_Condensed({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-condensed",
});
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: { default: "VeriAgent — Evidence ledger", template: "%s · VeriAgent" },
  description: "A bounded claim-investigation demo with an inspectable evidence trail.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${serif.variable} ${condensed.variable} ${mono.variable}`}>
      <body>
        <a className="skip-link" href="#main-content">Skip to content</a>
        <Suspense fallback={<header className="site-header"><span className="wordmark"><strong>VERI<span>AGENT</span></strong><small>evidence ledger</small></span></header>}>
          <AppHeader />
        </Suspense>
        {children}
      </body>
    </html>
  );
}
