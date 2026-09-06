"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/auth";
import { ApiError } from "@/lib/api";
import Link from "next/link";

const SSO_ERROR_MESSAGES: Record<string, string> = {
  not_configured: "SSO is not configured for this environment.",
  invalid_callback: "The auth service returned an incomplete sign-in response.",
  missing_flow_cookie: "Your browser did not return the sign-in cookie. Please retry with cookies enabled.",
  state_mismatch: "Sign-in session expired or invalid. Please try again.",
  nonce_mismatch: "Sign-in could not be verified. Please try again.",
  token_exchange_failed: "Could not complete sign-in with the auth service.",
  missing_id_token: "Auth service did not return a sign-in token.",
  bad_id_token: "Auth service returned an unreadable sign-in token.",
  exchange_rejected: "The platform rejected the SSO sign-in.",
  exchange_failed: "Could not reach the API to complete SSO sign-in.",
  no_session_token: "SSO sign-in did not produce a session token.",
};

export default function LoginPage() {
  const { login, user } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Surface SSO errors passed back by /api/auth/oidc/callback
  useEffect(() => {
    const ssoError = new URLSearchParams(window.location.search).get("sso_error");
    if (ssoError) {
      setError(SSO_ERROR_MESSAGES[ssoError] ?? `SSO sign-in failed (${ssoError}).`);
      history.replaceState(null, "", window.location.pathname);
    }
  }, []);

  // Already logged in — redirect
  if (user) {
    router.replace("/dashboard");
    return null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
      router.replace("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("An unexpected error occurred.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#09090b] relative">
      {/* Background glow */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 60% 50% at 50% 40%, rgba(0,214,143,0.04), transparent)",
        }}
      />

      <div className="relative z-10 w-full max-w-sm px-4">
        {/* Logo */}
        <div className="mb-8 text-center">
          <Link
            href="/"
            className="font-mono text-2xl font-bold text-brand-500 hover:text-brand-400 transition-colors"
          >
            tbd
          </Link>
        </div>

        {/* Card */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/80 p-8 shadow-[0_0_60px_-15px_rgba(0,214,143,0.08)]">
          <div className="mb-6">
            <h1 className="font-mono text-sm text-zinc-400">
              <span className="text-brand-500">{">"}</span> authenticate
            </h1>
            <p className="mt-2 text-xs text-zinc-600">
              Sign in via SSO or with your Active Directory credentials
            </p>
          </div>

          <a
            href="/api/auth/oidc/login?redirect=/dashboard"
            className="mb-5 flex w-full items-center justify-center gap-2 rounded-lg border border-brand-500/40 bg-brand-500/10 px-4 py-2.5 text-sm font-medium text-brand-400 transition-all hover:border-brand-500/70 hover:bg-brand-500/20"
          >
            <svg
              className="h-4 w-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
              <polyline points="10 17 15 12 10 7" />
              <line x1="15" y1="12" x2="3" y2="12" />
            </svg>
            Sign in with SSO
          </a>

          <div className="mb-5 flex items-center gap-3">
            <div className="h-px flex-1 bg-zinc-800" />
            <span className="text-[10px] uppercase tracking-wider text-zinc-700">
              or AD credentials
            </span>
            <div className="h-px flex-1 bg-zinc-800" />
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="username"
                className="mb-1.5 block text-xs font-medium text-zinc-500"
              >
                Username
              </label>
              <input
                id="username"
                type="text"
                required
                autoFocus
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="block w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2.5 text-sm text-zinc-200 placeholder-zinc-700 transition-colors focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
                placeholder="jdoe"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="mb-1.5 block text-xs font-medium text-zinc-500"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="block w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2.5 text-sm text-zinc-200 placeholder-zinc-700 transition-colors focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
              />
            </div>

            {error && (
              <div className="rounded-lg border border-red-900/50 bg-red-950/50 px-3 py-2 text-sm text-red-400">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-brand-500 px-4 py-2.5 text-sm font-medium text-black transition-all hover:bg-brand-400 hover:shadow-[0_0_20px_rgba(0,214,143,0.25)] disabled:opacity-50 disabled:hover:shadow-none"
            >
              {loading ? "Authenticating..." : "Sign in"}
            </button>
          </form>
        </div>

        <p className="mt-6 text-center text-xs text-zinc-700">
          &copy; {new Date().getFullYear()} SDC &middot; TBD Platform
        </p>
      </div>
    </div>
  );
}
