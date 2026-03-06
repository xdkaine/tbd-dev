"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/auth";
import { ApiError } from "@/lib/api";
import Link from "next/link";

export default function LoginPage() {
  const { login, user } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

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
              Sign in with your Active Directory credentials
            </p>
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
