"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/contexts/auth";

/** Client-side handoff page for the SSO flow. The callback route redirects
 *  here with the session token in the URL fragment (never sent to servers);
 *  we adopt the session and continue to the original destination. */
export default function SsoBridgePage() {
  const { applySession } = useAuth();
  const router = useRouter();
  const [error, setError] = useState("");

  useEffect(() => {
    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const token = hash.get("token");
    const redirectParam = hash.get("redirect");
    const errorParam = hash.get("error");

    // Scrub the fragment immediately so the token doesn't linger
    history.replaceState(null, "", window.location.pathname + window.location.search);

    if (!token) {
      router.replace(
        `/login${errorParam ? `?sso_error=${encodeURIComponent(errorParam)}` : ""}`,
      );
      return;
    }

    const redirect = redirectParam && redirectParam.startsWith("/") ? redirectParam : "/dashboard";

    applySession(token).then((ok) => {
      if (ok) {
        router.replace(redirect);
      } else {
        setError("SSO session could not be established. Please try signing in again.");
      }
    });
  }, [applySession, router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#09090b]">
      <div className="text-center">
        {error ? (
          <>
            <p className="mb-4 text-sm text-red-400">{error}</p>
            <Link href="/login" className="text-sm text-brand-500 hover:text-brand-400">
              Back to sign in
            </Link>
          </>
        ) : (
          <p className="font-mono text-sm text-zinc-500">completing sign-in&hellip;</p>
        )}
      </div>
    </div>
  );
}
