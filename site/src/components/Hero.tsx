import { ArrowRight, Github } from "lucide-react";
import { HERO, REPO_URL, STATS } from "../data/site";
import { CountUp } from "./CountUp";
import { Reveal } from "./Reveal";

export function Hero() {
  return (
    <section
      id="top"
      className="hero-glow relative overflow-hidden pb-14 pt-28 sm:pb-16 sm:pt-32 lg:pb-20"
    >
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 grid-lines" />

      <div className="container-page relative">
        <div className="grid items-start gap-10 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] lg:gap-14">
          <div>
            <Reveal>
              <p className="eyebrow">{HERO.eyebrow}</p>
              <h1 className="mt-4 text-5xl font-extrabold tracking-tight sm:text-6xl lg:text-[4.6rem] lg:leading-[0.95]">
                <span className="gradient-text">{HERO.title}</span>
              </h1>
              <p className="mt-5 max-w-2xl text-base leading-relaxed text-[var(--muted)] sm:text-lg">
                {HERO.subtitle}
              </p>
            </Reveal>

            <Reveal delay={90}>
              <ul className="mt-6 flex flex-wrap gap-2" aria-label="Technology chips">
                {HERO.chips.map((chip) => (
                  <li key={chip} className="chip">
                    {chip}
                  </li>
                ))}
              </ul>

              <div className="mt-8 flex flex-wrap gap-3">
                <a href="#setup" className="btn-primary">
                  Get Started
                  <ArrowRight aria-hidden="true" className="h-4 w-4" />
                </a>
                <a
                  href={REPO_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-ghost"
                >
                  <Github aria-hidden="true" className="h-4 w-4" />
                  View on GitHub
                </a>
              </div>
            </Reveal>
          </div>

          <Reveal delay={160} className="lg:pt-2">
            <div className="card overflow-hidden p-0">
              <div className="flex items-center gap-2 border-b border-[var(--border)] bg-[var(--bg-soft)] px-4 py-2.5">
                <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full bg-rose-400/80" />
                <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full bg-amber-400/80" />
                <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full bg-emerald-400/80" />
                <span className="ml-2 font-mono text-[11px] text-[var(--muted)]">
                  scrapeflow — bash
                </span>
              </div>
              <div className="bg-[var(--code-bg)] p-5 font-mono text-[13px] leading-6 text-slate-300">
                <p>
                  <span className="text-emerald-400">$</span>{" "}
                  <span className="text-slate-100">{HERO.terminal.command.slice(2)}</span>
                </p>
                <p className="mt-4 text-emerald-300">{HERO.terminal.ready}</p>
                <p className="mt-1 text-slate-500">Dashboard  http://127.0.0.1:3000</p>
                <p className="text-slate-500">API        http://127.0.0.1:8000</p>
                <p className="mt-4 text-slate-500">
                  11 services · postgres · redis · api · worker · beat · web
                </p>
                <p className="mt-3">
                  <span className="text-emerald-400">$</span>{" "}
                  <span
                    aria-hidden="true"
                    className="inline-block h-4 w-2 translate-y-0.5 animate-blink bg-slate-300"
                  />
                </p>
              </div>
            </div>
          </Reveal>
        </div>

        <Reveal delay={220}>
          <ul className="mt-10 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:mt-14 lg:grid-cols-5">
            {STATS.map((stat) => (
              <li key={stat.label} className="card px-4 py-4">
                <p className="text-2xl font-extrabold tracking-tight sm:text-[1.7rem]">
                  <CountUp
                    value={stat.value}
                    decimals={stat.decimals ?? 0}
                    suffix={stat.suffix ?? ""}
                  />
                </p>
                <p className="mt-1 text-xs text-[var(--muted)]">{stat.label}</p>
              </li>
            ))}
          </ul>
        </Reveal>
      </div>
    </section>
  );
}
