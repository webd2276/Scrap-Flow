import { Github, Menu, Moon, Sun, X } from "lucide-react";
import { useEffect, useState } from "react";
import { NAV_LINKS, REPO_URL, SECTION_IDS } from "../data/site";
import { cn } from "../lib/cn";
import { useTheme } from "../lib/theme";
import { useActiveSection } from "../lib/useActiveSection";

export function Navbar() {
  const { theme, toggle } = useTheme();
  const [open, setOpen] = useState(false);
  const active = useActiveSection(SECTION_IDS, "overview");

  useEffect(() => {
    if (!open) {
      return;
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <header
      className="fixed inset-x-0 top-0 z-40 border-b border-[var(--border)] backdrop-blur-md"
      style={{ backgroundColor: "color-mix(in srgb, var(--bg) 86%, transparent)" }}
    >
      <div className="container-page flex h-16 items-center justify-between gap-3">
        <a href="#top" className="flex shrink-0 items-center gap-2.5">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-indigo-400 to-cyan-300 font-mono text-sm font-extrabold text-slate-950 shadow-glow">
            SF
          </span>
          <span className="text-[15px] font-bold tracking-tight">ScrapeFlow</span>
        </a>

        <nav aria-label="Primary" className="hidden lg:block">
          <ul className="flex items-center gap-1">
            {NAV_LINKS.map((link) => (
              <li key={link.id}>
                <a
                  href={`#${link.id}`}
                  aria-current={active === link.id ? "true" : undefined}
                  className={cn(
                    "rounded-lg px-2.5 py-2 text-[13px] font-medium transition",
                    active === link.id
                      ? "bg-[var(--bg-soft)] text-[var(--text)]"
                      : "text-[var(--muted)] hover:text-[var(--text)]",
                  )}
                >
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={toggle}
            className="icon-btn"
            aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          >
            {theme === "dark" ? (
              <Sun aria-hidden="true" className="h-[18px] w-[18px]" />
            ) : (
              <Moon aria-hidden="true" className="h-[18px] w-[18px]" />
            )}
          </button>

          <a
            href={REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-ghost hidden !px-3 !py-2 sm:inline-flex"
          >
            <Github aria-hidden="true" className="h-4 w-4" />
            <span className="hidden md:inline">GitHub</span>
            <span className="sr-only md:hidden">ScrapeFlow on GitHub</span>
          </a>

          <button
            type="button"
            onClick={() => setOpen((current) => !current)}
            className="icon-btn lg:hidden"
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            aria-controls="mobile-navigation"
          >
            {open ? (
              <X aria-hidden="true" className="h-[18px] w-[18px]" />
            ) : (
              <Menu aria-hidden="true" className="h-[18px] w-[18px]" />
            )}
          </button>
        </div>
      </div>

      {open ? (
        <div
          id="mobile-navigation"
          className="border-t border-[var(--border)] bg-[var(--panel-solid)] lg:hidden"
        >
          <nav aria-label="Primary mobile" className="container-page py-3">
            <ul className="grid grid-cols-1 gap-1 sm:grid-cols-2">
              {NAV_LINKS.map((link) => (
                <li key={link.id}>
                  <a
                    href={`#${link.id}`}
                    onClick={() => setOpen(false)}
                    aria-current={active === link.id ? "true" : undefined}
                    className={cn(
                      "block rounded-lg px-3 py-2.5 text-sm font-medium",
                      active === link.id
                        ? "bg-[var(--bg-soft)] text-[var(--text)]"
                        : "text-[var(--muted)]",
                    )}
                  >
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
            <a
              href={REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-ghost mt-3 w-full"
            >
              <Github aria-hidden="true" className="h-4 w-4" />
              View on GitHub
            </a>
          </nav>
        </div>
      ) : null}
    </header>
  );
}
