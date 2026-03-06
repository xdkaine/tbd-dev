"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { formatDate, timeAgo } from "@/lib/utils";
import type { Project, Secret } from "@/lib/types";

type Scope = "project" | "production" | "staging" | "preview";

export default function SecretsPage() {
  const params = useParams();
  const projectId = params.projectId as string;

  const [project, setProject] = useState<Project | null>(null);
  const [secrets, setSecrets] = useState<Secret[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [proj, sec] = await Promise.all([
        api.projects.get(projectId),
        api.secrets.list(projectId),
      ]);
      setProject(proj);
      setSecrets(sec.items);
    } catch {
      /* */
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  async function handleDelete(key: string) {
    setDeleting(key);
    try {
      await api.secrets.delete(projectId, key);
      fetchData();
    } catch {
      /* */
    } finally {
      setDeleting(null);
    }
  }

  if (loading) {
    return <p className="text-sm text-zinc-500">Loading...</p>;
  }

  if (!project) {
    return <p className="text-sm text-red-400">Project not found</p>;
  }

  // Group secrets by scope
  const byScope = secrets.reduce<Record<string, Secret[]>>((acc, s) => {
    const key = s.scope;
    if (!acc[key]) acc[key] = [];
    acc[key].push(s);
    return acc;
  }, {});

  const scopeOrder: Scope[] = ["project", "production", "staging", "preview"];

  return (
    <div>
      {/* Breadcrumb */}
      <div className="mb-4 text-sm">
        <Link href="/dashboard" className="text-zinc-500 hover:text-zinc-300">
          Projects
        </Link>
        <span className="mx-1 text-zinc-600">/</span>
        <Link
          href={`/dashboard/${projectId}`}
          className="text-zinc-500 hover:text-zinc-300"
        >
          {project.name}
        </Link>
        <span className="mx-1 text-zinc-600">/</span>
        <span className="font-medium text-zinc-300">Secrets</span>
      </div>

      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100">Secrets</h1>
          <p className="text-sm text-zinc-400">
            Environment variables for {project.name}. Values are encrypted at
            rest and never displayed.
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="rounded-md bg-brand-500 px-4 py-2 text-sm font-medium text-black hover:bg-brand-400"
        >
          Add secret
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <CreateSecretForm
          projectId={projectId}
          onCreated={() => {
            setShowCreate(false);
            fetchData();
          }}
          onCancel={() => setShowCreate(false)}
        />
      )}

      {/* Secret list grouped by scope */}
      {secrets.length === 0 ? (
        <div className="rounded-lg border border-dashed border-zinc-800 p-8 text-center">
          <p className="text-sm text-zinc-400">No secrets configured yet.</p>
          <button
            onClick={() => setShowCreate(true)}
            className="mt-2 text-sm font-medium text-brand-400 hover:text-brand-300"
          >
            Add your first secret
          </button>
        </div>
      ) : (
        <div className="space-y-6">
          {scopeOrder.map((scope) => {
            const items = byScope[scope];
            if (!items || items.length === 0) return null;
            return (
              <div key={scope}>
                <h3 className="mb-2 text-sm font-semibold capitalize text-zinc-300">
                  {scope === "project" ? "Project-wide" : scope}
                </h3>
                <div className="overflow-hidden rounded-lg border border-zinc-800">
                  <table className="min-w-full divide-y divide-zinc-800 text-sm">
                    <thead className="bg-zinc-900/50">
                      <tr>
                        <th className="px-4 py-2 text-left font-medium text-zinc-500">
                          Key
                        </th>
                        <th className="px-4 py-2 text-left font-medium text-zinc-500">
                          Value
                        </th>
                        <th className="px-4 py-2 text-left font-medium text-zinc-500">
                          Created
                        </th>
                        <th className="px-4 py-2 text-right font-medium text-zinc-500">
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-800">
                      {items.map((s) => (
                        <tr key={s.id} className="hover:bg-zinc-800/50">
                          <td className="px-4 py-2 font-mono text-xs text-zinc-100">
                            {s.key}
                          </td>
                          <td className="px-4 py-2 text-xs text-zinc-500">
                            ••••••••
                          </td>
                          <td className="px-4 py-2 text-xs text-zinc-500">
                            {timeAgo(s.created_at)}
                          </td>
                          <td className="px-4 py-2 text-right">
                            <button
                              onClick={() => handleDelete(s.key)}
                              disabled={deleting === s.key}
                              className="text-xs text-red-400 hover:text-red-300 disabled:opacity-50"
                            >
                              {deleting === s.key ? "Deleting..." : "Delete"}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  Create secret form                                                     */
/* ---------------------------------------------------------------------- */

function CreateSecretForm({
  projectId,
  onCreated,
  onCancel,
}: {
  projectId: string;
  onCreated: () => void;
  onCancel: () => void;
}) {
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const [scope, setScope] = useState<Scope>("project");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    // Validate key format
    if (!/^[A-Z_][A-Z0-9_]*$/.test(key)) {
      setError(
        "Key must start with A-Z or underscore and contain only A-Z, 0-9, underscore",
      );
      return;
    }

    setSubmitting(true);
    try {
      await api.secrets.create(projectId, { key, value, scope });
      onCreated();
    } catch (err) {
      if (err instanceof ApiError) setError(err.detail);
      else setError("Failed to create secret");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mb-6 rounded-lg border border-brand-800 bg-brand-950/50 p-4">
      <h2 className="mb-3 text-sm font-semibold text-zinc-100">Add secret</h2>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-300">
              Key
            </label>
            <input
              type="text"
              required
              autoFocus
              value={key}
              onChange={(e) => setKey(e.target.value.toUpperCase())}
              className="block w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 py-1.5 font-mono text-sm text-zinc-200 placeholder-zinc-600 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
              placeholder="DATABASE_URL"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-300">
              Value
            </label>
            <input
              type="password"
              required
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="block w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
              placeholder="secret-value"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-300">
              Scope
            </label>
            <select
              value={scope}
              onChange={(e) => setScope(e.target.value as Scope)}
              className="block w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
            >
              <option value="project">Project-wide</option>
              <option value="production">Production only</option>
              <option value="staging">Staging only</option>
              <option value="preview">Preview only</option>
            </select>
          </div>
        </div>

        {error && <p className="text-xs text-red-400">{error}</p>}

        <div className="flex gap-2">
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-brand-500 px-3 py-1.5 text-xs font-medium text-black hover:bg-brand-400 disabled:opacity-50"
          >
            {submitting ? "Saving..." : "Add secret"}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
