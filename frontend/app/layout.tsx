import type { Metadata } from "next";
import { AppHeader } from "@/components/AppHeader";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "VeriAgent — Follow the evidence", template: "%s · VeriAgent" },
  description: "Scope-aware research and fact verification with a reproducible evidence trail.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <a className="skip-link" href="#main-content">Skip to content</a>
        <AppHeader />
        {children}
        <footer className="site-footer">
          <span>VeriAgent / Evidence, with conditions.</span>
          <span>Every conclusion keeps its receipts.</span>
        </footer>
      </body>
    </html>
  );
}
