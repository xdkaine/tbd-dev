"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

/* ═══════════════════════════════════════════════════════════════
   Icons — only what we need
   ═══════════════════════════════════════════════════════════════ */

function IconArrowRight({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
    </svg>
  );
}

function IconGitBranch({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 3v12m0 0a3 3 0 103 3h6a3 3 0 100-3m-9 0a3 3 0 013 3m6-3a3 3 0 013 3M18 3v6a3 3 0 01-3 3H9" />
    </svg>
  );
}

function IconContainer({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 7.5l-9-5.25L3 7.5m18 0l-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9" />
    </svg>
  );
}

function IconLock({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
    </svg>
  );
}

function IconGlobe({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5a17.92 17.92 0 01-8.716-4.247m0 0A8.966 8.966 0 013 12c0-1.528.382-2.968 1.055-4.228" />
    </svg>
  );
}

/* ═══════════════════════════════════════════════════════════════
   Hooks
   ═══════════════════════════════════════════════════════════════ */

function useScrollReveal() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const children = el.querySelectorAll("[data-reveal]");
    if (children.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("revealed");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.1, rootMargin: "0px 0px -40px 0px" }
    );

    children.forEach((child) => observer.observe(child));
    return () => observer.disconnect();
  }, []);

  return ref;
}

/* ═══════════════════════════════════════════════════════════════
   Navbar
   ═══════════════════════════════════════════════════════════════ */

function Navbar() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled
          ? "bg-black/80 backdrop-blur-xl border-b border-[var(--landing-border)]"
          : "bg-transparent"
      }`}
    >
      <div className="mx-auto max-w-5xl flex items-center justify-between px-6 py-4">
        <Link href="/" className="font-mono text-lg font-bold tracking-tight text-[var(--landing-text)]">
          tbd
        </Link>

        <div className="flex items-center gap-6">
          <Link
            href="/login"
            className="text-sm text-[var(--landing-muted)] hover:text-[var(--landing-text)] transition-colors"
          >
            Sign in
          </Link>
          <Link
            href="/login"
            className="inline-flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-400"
          >
            Get Started
            <IconArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>
    </nav>
  );
}

/* ═══════════════════════════════════════════════════════════════
   Terminal Demo
   ═══════════════════════════════════════════════════════════════ */

const TERMINAL_LINES = [
  { prompt: true, text: "git push origin main" },
  { prompt: false, text: "remote: Resolving deltas: 100% (12/12), done." },
  { prompt: false, text: "remote: Build started for commit a1f3c9e..." },
  { prompt: false, text: "remote: Installing dependencies..." },
  { prompt: false, text: "remote: Building application..." },
  { prompt: false, text: "remote: Build succeeded in 24s", color: "text-green-400" },
  { prompt: false, text: "remote: Provisioning LXC container..." },
  { prompt: false, text: "remote: Container healthy, routing traffic...", color: "text-green-400" },
  { prompt: false, text: "" },
  { prompt: false, text: "Deploy live at https://myapp.dev.sdc.cpp", color: "text-white" },
];

function TerminalDemo() {
  const [visibleLines, setVisibleLines] = useState(0);
  const terminalRef = useRef<HTMLDivElement>(null);
  const hasStarted = useRef(false);

  useEffect(() => {
    const el = terminalRef.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !hasStarted.current) {
          hasStarted.current = true;
          let i = 0;
          const interval = setInterval(() => {
            i++;
            setVisibleLines(i);
            if (i >= TERMINAL_LINES.length) clearInterval(interval);
          }, 500);
        }
      },
      { threshold: 0.3 }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={terminalRef} className="w-full max-w-2xl mx-auto">
      <div className="rounded-lg border border-[var(--landing-border)] bg-[var(--landing-surface)] overflow-hidden">
        {/* Title bar */}
        <div className="flex items-center px-4 py-2.5 border-b border-[var(--landing-border)]">
          <span className="text-xs text-[var(--landing-muted)] font-mono">
            terminal
          </span>
        </div>

        {/* Output */}
        <div className="p-5 font-mono text-[13px] leading-relaxed min-h-[260px]">
          {TERMINAL_LINES.map((line, i) => (
            <div
              key={i}
              className={`terminal-line ${
                i < visibleLines ? "" : "!opacity-0 !animate-none"
              } ${line.color || "text-[#888]"}`}
              style={{ animationDelay: `${i * 0.05}s` }}
            >
              {line.prompt && (
                <span className="text-[var(--landing-muted)] select-none">$ </span>
              )}
              {line.text}
              {i === visibleLines - 1 &&
                visibleLines < TERMINAL_LINES.length && (
                  <span className="terminal-cursor" />
                )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   Feature data
   ═══════════════════════════════════════════════════════════════ */

const FEATURES = [
  {
    icon: <IconGitBranch className="w-5 h-5" />,
    title: "Push to deploy",
    description:
      "Connect your GitHub repo and deploy on every push to main. No CI config, no YAML files.",
  },
  {
    icon: <IconContainer className="w-5 h-5" />,
    title: "LXC containers",
    description:
      "Lightweight Linux containers on Proxmox. Fast cold starts, full isolation, low overhead.",
  },
  {
    icon: <IconLock className="w-5 h-5" />,
    title: "Secrets & config",
    description:
      "Encrypted environment variables scoped per environment. Inject at build or runtime.",
  },
  {
    icon: <IconGlobe className="w-5 h-5" />,
    title: "Instant DNS",
    description:
      "Every deploy gets a unique *.dev.sdc.cpp URL automatically. Zero DNS configuration.",
  },
];

/* ═══════════════════════════════════════════════════════════════
   Page
   ═══════════════════════════════════════════════════════════════ */

export default function LandingPage() {
  const featuresRef = useScrollReveal();

  return (
    <div className="landing min-h-screen">
      <Navbar />

      {/* ────── Hero ────── */}
      <section className="flex flex-col items-center justify-center px-6 pt-40 pb-20 sm:pt-48 sm:pb-28">
        <div className="max-w-3xl mx-auto text-center">
          <h1 className="text-[clamp(2.5rem,6vw,4.25rem)] font-bold tracking-tight leading-[1.1] text-white">
            Ship your code.
            <br />
            We handle the rest.
          </h1>

          <p className="mt-6 text-lg text-[var(--landing-muted)] max-w-xl mx-auto leading-relaxed">
            A free deployment platform for SDC developers. Push to GitHub,
            get a live URL. No cloud bills, no complexity.
          </p>

          <p className="mt-4 text-sm text-[var(--landing-muted)] tracking-wide">
            Built by developers, for developers.
          </p>

          <div className="mt-10">
            <Link
              href="/login"
              className="inline-flex items-center gap-2 rounded-lg bg-brand-500 px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-brand-400"
            >
              Start deploying
              <IconArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* ────── Terminal ────── */}
      <section className="px-6 pb-28 sm:pb-36">
        <TerminalDemo />
      </section>

      {/* ────── Features ────── */}
      <section className="border-t border-[var(--landing-border)] px-6 py-24 sm:py-32">
        <div ref={featuresRef} className="mx-auto max-w-2xl">
          <div className="space-y-12">
            {FEATURES.map((feature, i) => (
              <div
                key={feature.title}
                data-reveal
                className={`stagger-${i + 1} flex gap-4`}
              >
                <div className="flex-shrink-0 mt-0.5 text-[var(--landing-muted)]">
                  {feature.icon}
                </div>
                <div>
                  <h3 className="text-base font-medium text-[var(--landing-text)]">
                    {feature.title}
                  </h3>
                  <p className="mt-1 text-sm text-[var(--landing-muted)] leading-relaxed">
                    {feature.description}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ────── CTA ────── */}
      <section className="border-t border-[var(--landing-border)] px-6 py-24 sm:py-32">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
            Ready to deploy?
          </h2>
          <p className="mt-4 text-[var(--landing-muted)]">
            Sign in with your school credentials and ship your first project in under a minute.
          </p>
          <div className="mt-8">
            <Link
              href="/login"
              className="inline-flex items-center gap-2 rounded-lg bg-brand-500 px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-brand-400"
            >
              Get started
              <IconArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* ────── Footer ────── */}
      <footer className="border-t border-[var(--landing-border)] px-6 py-8">
        <div className="mx-auto max-w-5xl flex items-center justify-between">
          <span className="font-mono text-sm text-[var(--landing-muted)]">
            tbd
          </span>
          <span className="text-sm text-[var(--landing-muted)]">
            &copy; {new Date().getFullYear()} SDC
          </span>
        </div>
      </footer>
    </div>
  );
}
