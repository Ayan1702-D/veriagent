import Link from "next/link";
import { ThemeToggle } from "./ThemeToggle";

export function AppHeader() {
  return (
    <header className="site-header">
      <Link className="wordmark" href="/" aria-label="VeriAgent home">
        <span className="wordmark-mark" aria-hidden="true">VA</span>
        <span><b>VERIAGENT</b><small>Public evidence unit</small></span>
      </Link>
      <nav className="site-nav" aria-label="Primary navigation">
        <Link href="/">01 / Intake</Link>
        <Link href="/eval">02 / Calibration</Link>
        <ThemeToggle />
      </nav>
    </header>
  );
}
