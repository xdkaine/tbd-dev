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
    return <p className="text-sm text-gray-500">Loading...</p>;
  }

  if (!project) {
    return <p className="text-sm text-red-600">Project not found</p>;
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
        <Link href="/dashboard" className="text-gray-400 hover:text-gray-600">
          Projects
        </Link>
        <span className="mx-1 text-gray-300">/</span>
        <Link
          href={`/dashboard/${projectId}`}
          className="text-gray-400 hover:text-gray-600"
        >
          {project.name}
        </Link>
        <span className="mx-1 text-gray-300">/</span>
        <span className="font-medium text-gray-700">Secrets</span>
      </div>

      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Secrets</h1>
          <p className="text-sm text-gray-500">
            Environment variables for {project.name}. Values are encrypted at
            rest and never displayed.
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
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
        <div className="rounded-lg border border-dashed border-gray-300 p-8 text-center">
          <p className="text-sm text-gray-500">No secrets configured yet.</p>
          <button
            onClick={() => setShowCreate(true)}
            className="mt-2 text-sm font-medium text-brand-600 hover:text-brand-700"
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
                <h3 className="mb-2 text-sm font-semibold capitalize text-gray-700">
                  {scope === "project" ? "Project-wide" : scope}
                </h3>
                <div className="overflow-hidden rounded-lg border border-gray-200">
                  <table className="min-w-full divide-y divide-gray-200 text-sm">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-4 py-2 text-left font-medium text-gray-500">
                          Key
                        </th>
                        <th className="px-4 py-2 text-left font-medium text-gray-500">
                          Value
                        </th>
                        <th className="px-4 py-2 text-left font-medium text-gray-500">
                          Created
                        </th>
                        <th className="px-4 py-2 text-right font-medium text-gray-500">
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {items.map((s) => (
                        <tr key={s.id} className="hover:bg-gray-50">
                          <td className="px-4 py-2 font-mono text-xs text-gray-900">
                            {s.key}
                          </td>
                          <td className="px-4 py-2 text-xs text-gray-400">
                            ••••••••
                          </td>
                          <td className="px-4 py-2 text-xs text-gray-500">
                            {timeAgo(s.created_at)}
                          </td>
                          <td className="px-4 py-2 text-right">
                            <button
                              onClick={() => handleDelete(s.key)}
                              disabled={deleting === s.key}
                              className="text-xs text-red-600 hover:text-red-800 disabled:opacity-50"
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
    <div className="mb-6 rounded-lg border border-brand-200 bg-brand-50 p-4">
      <h2 className="mb-3 text-sm font-semibold text-gray-900">Add secret</h2>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              Key
            </label>
            <input
              type="text"
              required
              autoFocus
              value={key}
              onChange={(e) => setKey(e.target.value.toUpperCase())}
              className="block w-full rounded-md border border-gray-300 px-3 py-1.5 font-mono text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              placeholder="DATABASE_URL"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              Value
            </label>
            <input
              type="password"
              required
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="block w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              placeholder="secret-value"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              Scope
            </label>
            <select
              value={scope}
              onChange={(e) => setScope(e.target.value as Scope)}
              className="block w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            >
              <option value="project">Project-wide</option>
              <option value="production">Production only</option>
              <option value="staging">Staging only</option>
              <option value="preview">Preview only</option>
            </select>
          </div>
        </div>

        {error && <p className="text-xs text-red-600">{error}</p>}

        <div className="flex gap-2">
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {submitting ? "Saving..." : "Add secret"}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
