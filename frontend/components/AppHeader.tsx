"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function AppHeader() {
  const pathname = usePathname();
  const match = pathname.match(/^\/runs\/([^/]+)/);
  const runId = match?.[1];
  const runHref = runId ? `/runs/${runId}` : "/#claim-intake";
  const auditHref = runId ? `/runs/${runId}/audit` : "/#claim-intake";
  const links = [
    ["Home", "/", pathname === "/"],
    ["Run", runHref, Boolean(runId) && !pathname.endsWith("/audit")],
    ["Audit", auditHref, pathname.endsWith("/audit")],
    ["Eval", "/eval", pathname === "/eval"],
  ] as const;

  return (
    <header className="site-header">
      <Link className="wordmark" href="/" aria-label="VeriAgent home">
        <strong>VERI<span>AGENT</span></strong>
        <small>evidence ledger</small>
      </Link>
      <nav className="site-nav" aria-label="Primary navigation">
        {links.filter(([label]) => runId || (label !== "Run" && label !== "Audit")).map(([label, href, active]) => (
          <Link key={label} href={href} className={active ? "active" : undefined} aria-current={active ? "page" : undefined}>
            {label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
