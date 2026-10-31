"use client";

type Theme = "light" | "dark";

export function ThemeToggle() {
  function toggle() {
    const current = document.documentElement.dataset.theme
      ?? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next: Theme = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("veriagent-theme", next);
  }

  return (
    <button
      className="theme-toggle"
      type="button"
      onClick={toggle}
      aria-label="Toggle color theme"
      title="Toggle color theme"
    >
      <span aria-hidden="true">◐</span>
    </button>
  );
}
