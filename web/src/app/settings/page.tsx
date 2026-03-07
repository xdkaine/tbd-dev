"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/contexts/auth";
import { api } from "@/lib/api";
import { ConfirmModal } from "@/components/modal";

export default function SettingsPage() {
  const { user, refreshUser } = useAuth();
  const searchParams = useSearchParams();
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<"success" | "error">("success");
  const [linking, setLinking] = useState(false);
  const [unlinking, setUnlinking] = useState(false);
  const [showUnlinkConfirm, setShowUnlinkConfirm] = useState(false);

  /* Handle redirect back from GitHub OAuth callback */
  useEffect(() => {
    if (searchParams.get("github_linked") === "true") {
      setMessage("GitHub account linked successfully.");
      setMessageType("success");
      refreshUser();
    }
    const error = searchParams.get("github_error");
    if (error) {
      const errorMessages: Record<string, string> = {
        invalid_state: "OAuth session expired. Please try again.",
        token_exchange_failed: "Failed to authenticate with GitHub. Please try again.",
        no_access_token: "GitHub did not return an access token. Please try again.",
        user_fetch_failed: "Failed to fetch your GitHub profile. Please try again.",
        invalid_user_data: "Invalid data returned from GitHub. Please try again.",
        already_linked: "This GitHub account is already linked to another user.",
        user_not_found: "Your platform account was not found.",
      };
      setMessage(errorMessages[error] || `GitHub linking failed: ${error}`);
      setMessageType("error");
    }
  }, [searchParams, refreshUser]);

  async function handleLinkGitHub() {
    setLinking(true);
    setMessage("");
    try {
      const { authorize_url } = await api.auth.githubAuthorizeUrl();
      // Redirect the browser to GitHub's OAuth page
      window.location.href = authorize_url;
    } catch (err: unknown) {
      const detail = err instanceof Error ? err.message : "Failed to start GitHub linking";
      setMessage(detail);
      setMessageType("error");
      setLinking(false);
    }
  }

  async function handleUnlinkGitHub() {
    setShowUnlinkConfirm(false);
    setUnlinking(true);
    setMessage("");
    try {
      await api.auth.githubUnlink();
      setMessage("GitHub account unlinked.");
      setMessageType("success");
      await refreshUser();
    } catch (err: unknown) {
      const detail = err instanceof Error ? err.message : "Failed to unlink";
      setMessage(detail);
      setMessageType("error");
    } finally {
      setUnlinking(false);
    }
  }

  if (!user) return null;

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-zinc-100">Settings</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Manage your account and integrations.
        </p>
      </div>

      {/* Status message */}
      {message && (
        <div
          className={`rounded-md px-4 py-3 text-sm ${
            messageType === "success"
              ? "bg-green-950/30 text-green-400 border border-green-800"
              : "bg-red-950/30 text-red-400 border border-red-800"
          }`}
        >
          {message}
        </div>
      )}

      {/* Profile info (read-only, synced from AD) */}
      <div className="rounded-lg border border-zinc-800 p-4">
        <h2 className="mb-3 text-sm font-semibold text-zinc-100">Profile</h2>
        <dl className="space-y-2 text-sm">
          <div className="flex justify-between">
            <dt className="text-zinc-500">Name</dt>
            <dd className="font-medium text-zinc-100">{user.display_name}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-zinc-500">Username</dt>
            <dd className="font-medium text-zinc-100">{user.username}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-zinc-500">Email</dt>
            <dd className="font-medium text-zinc-100">{user.email}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-zinc-500">Role</dt>
            <dd>
              <span className="rounded bg-brand-950 px-1.5 py-0.5 text-xs font-semibold text-brand-400 uppercase">
                {user.role}
              </span>
            </dd>
          </div>
        </dl>
        <p className="mt-3 text-xs text-zinc-500">
          Profile information is synced from Active Directory.
        </p>
      </div>

      {/* GitHub Account Linking */}
      <div className="rounded-lg border border-zinc-800 p-4">
        <h2 className="mb-3 text-sm font-semibold text-zinc-100">
          GitHub Account
        </h2>

        {user.github_username ? (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white text-zinc-900">
                <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
                </svg>
              </div>
              <div>
                <p className="text-sm font-medium text-zinc-100">
                  {user.github_username}
                </p>
                <p className="text-xs text-zinc-500">Connected</p>
              </div>
            </div>
            <button
              onClick={() => setShowUnlinkConfirm(true)}
              disabled={unlinking}
              className="rounded-md border border-red-800 px-3 py-1.5 text-xs font-medium text-red-400 hover:bg-red-950/30 disabled:opacity-50"
            >
              {unlinking ? "Unlinking..." : "Unlink"}
            </button>
          </div>
        ) : (
          <div>
            <p className="mb-3 text-sm text-zinc-400">
              Link your GitHub account to import repositories and enable
              automatic deployments from your personal repos.
            </p>
            <button
              onClick={handleLinkGitHub}
              disabled={linking}
              className="inline-flex items-center gap-2 rounded-md bg-white px-4 py-2 text-sm font-medium text-zinc-900 hover:bg-zinc-200 disabled:opacity-50"
            >
              <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
              </svg>
              {linking ? "Connecting..." : "Link GitHub Account"}
            </button>
          </div>
        )}
      </div>

      <ConfirmModal
        open={showUnlinkConfirm}
        onClose={() => setShowUnlinkConfirm(false)}
        onConfirm={handleUnlinkGitHub}
        title="Unlink GitHub Account"
        description="Are you sure you want to unlink your GitHub account? You can re-link it at any time."
        confirmLabel="Unlink"
        variant="danger"
        loading={unlinking}
      />
    </div>
  );
}
