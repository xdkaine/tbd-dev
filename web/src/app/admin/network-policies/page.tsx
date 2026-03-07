"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/auth";
import { formatDate } from "@/lib/utils";
import { ConfirmModal } from "@/components/modal";
import type {
  NetworkPolicy,
  NetworkPolicyCreate,
  Project,
} from "@/lib/types";

const DIRECTION_OPTIONS = [
  { value: "", label: "All Directions" },
  { value: "egress", label: "Egress" },
  { value: "ingress", label: "Ingress" },
];

export default function NetworkPoliciesPage() {
  const { user } = useAuth();
  const [policies, setPolicies] = useState<NetworkPolicy[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [dirFilter, setDirFilter] = useState("");
  const [page, setPage] = useState(0);
  const [showCreate, setShowCreate] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const limit = 25;

  const isFaculty = user?.role === "JAS-Faculty";

  // Create form state
  const [createForm, setCreateForm] = useState<NetworkPolicyCreate>({
    project_id: "",
    name: "",
    direction: "egress",
    protocol: "tcp",
    port: undefined,
    destination: "",
    action: "allow",
  });

  const fetchPolicies = useCallback(async () => {
    setLoading(true);
    try {
      setError(null);
      const res = await api.admin.networkPolicies.list({
        skip: page * limit,
        limit,
        direction: dirFilter || undefined,
      });
      setPolicies(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load network policies");
    } finally {
      setLoading(false);
    }
  }, [page, dirFilter]);

  const fetchProjects = useCallback(async () => {
    try {
      const res = await api.projects.list(0, 200);
      setProjects(res.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load projects");
    }
  }, []);

  useEffect(() => {
    fetchPolicies();
  }, [fetchPolicies]);

  useEffect(() => {
    if (showCreate && projects.length === 0) {
      fetchProjects();
    }
  }, [showCreate, projects.length, fetchProjects]);

  if (user && user.role === "JAS_Developer") {
    return (
      <p className="text-sm text-red-400">
        You do not have permission to view this page.
      </p>
    );
  }

  const totalPages = Math.ceil(total / limit);

  // Summary counts (page-level for breakdown, total from API)
  const egressCount = policies.filter((p) => p.direction === "egress").length;
  const ingressCount = policies.filter((p) => p.direction === "ingress").length;
  const enabledCount = policies.filter((p) => p.enabled).length;

  async function handleCreate() {
    if (!createForm.project_id || !createForm.name || !createForm.destination) {
      return;
    }
    setSaving(true);
    try {
      await api.admin.networkPolicies.create(createForm);
      setShowCreate(false);
      setCreateForm({
        project_id: "",
        name: "",
        direction: "egress",
        protocol: "tcp",
        port: undefined,
        destination: "",
        action: "allow",
      });
      await fetchPolicies();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create policy");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(policyId: string) {
    setDeleteConfirmId(null);
    setDeleting(policyId);
    try {
      await api.admin.networkPolicies.delete(policyId);
      await fetchPolicies();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete policy");
    } finally {
      setDeleting(null);
    }
  }

  async function handleToggle(policy: NetworkPolicy) {
    setToggling(policy.id);
    try {
      await api.admin.networkPolicies.update(policy.id, {
        enabled: !policy.enabled,
      });
      await fetchPolicies();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to toggle policy");
    } finally {
      setToggling(null);
    }
  }

  return (
    <div>
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100">
            Network Policies
          </h1>
          <p className="text-sm text-zinc-500">
            Firewall rules per project &mdash; default posture is deny-all
            egress
          </p>
        </div>
        {isFaculty && (
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="rounded-lg bg-brand-500 px-3 py-1.5 text-sm font-medium text-black hover:bg-brand-400"
          >
            {showCreate ? "Cancel" : "New Policy"}
          </button>
        )}
      </div>

      {/* Summary cards */}
      <div className="mb-6 grid gap-4 sm:grid-cols-4">
        <SummaryCard label="Total Policies" value={total} />
        <SummaryCard label="Egress Rules" value={egressCount} sub="this page" />
        <SummaryCard label="Ingress Rules" value={ingressCount} sub="this page" />
        <SummaryCard label="Enabled" value={enabledCount} sub="this page" />
      </div>

      {/* Create form */}
      {showCreate && isFaculty && (
        <div className="mb-6 rounded-lg border border-brand-800 bg-brand-950/50 p-4">
          <h3 className="mb-3 text-sm font-semibold text-zinc-100">
            Create Network Policy
          </h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-zinc-300">
                Project
              </label>
              <select
                value={createForm.project_id}
                onChange={(e) =>
                  setCreateForm({ ...createForm, project_id: e.target.value })
                }
                className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1 text-sm text-zinc-200"
              >
                <option value="">Select project...</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-zinc-300">
                Name
              </label>
              <input
                type="text"
                value={createForm.name}
                onChange={(e) =>
                  setCreateForm({ ...createForm, name: e.target.value })
                }
                className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1 text-sm text-zinc-200 placeholder-zinc-600"
                placeholder="e.g. Allow HTTPS"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-zinc-300">
                Direction
              </label>
              <select
                value={createForm.direction}
                onChange={(e) =>
                  setCreateForm({
                    ...createForm,
                    direction: e.target.value as "egress" | "ingress",
                  })
                }
                className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1 text-sm text-zinc-200"
              >
                <option value="egress">Egress</option>
                <option value="ingress">Ingress</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-zinc-300">
                Protocol
              </label>
              <select
                value={createForm.protocol}
                onChange={(e) =>
                  setCreateForm({
                    ...createForm,
                    protocol: e.target.value as "tcp" | "udp" | "icmp" | "any",
                  })
                }
                className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1 text-sm text-zinc-200"
              >
                <option value="tcp">TCP</option>
                <option value="udp">UDP</option>
                <option value="icmp">ICMP</option>
                <option value="any">Any</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-zinc-300">
                Port
              </label>
              <input
                type="number"
                value={createForm.port ?? ""}
                onChange={(e) =>
                  setCreateForm({
                    ...createForm,
                    port: e.target.value ? Number(e.target.value) : undefined,
                  })
                }
                className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1 text-sm text-zinc-200 placeholder-zinc-600"
                placeholder="e.g. 443"
                min={1}
                max={65535}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-zinc-300">
                Destination
              </label>
              <input
                type="text"
                value={createForm.destination}
                onChange={(e) =>
                  setCreateForm({
                    ...createForm,
                    destination: e.target.value,
                  })
                }
                className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1 text-sm text-zinc-200 placeholder-zinc-600"
                placeholder="e.g. 0.0.0.0/0"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-zinc-300">
                Action
              </label>
              <select
                value={createForm.action}
                onChange={(e) =>
                  setCreateForm({
                    ...createForm,
                    action: e.target.value as "allow" | "deny",
                  })
                }
                className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1 text-sm text-zinc-200"
              >
                <option value="allow">Allow</option>
                <option value="deny">Deny</option>
              </select>
            </div>
            <div className="flex items-end">
              <button
                onClick={handleCreate}
                disabled={
                  saving ||
                  !createForm.project_id ||
                  !createForm.name ||
                  !createForm.destination
                }
                className="rounded-lg bg-brand-500 px-4 py-1 text-sm font-medium text-black hover:bg-brand-400 disabled:opacity-50"
              >
                {saving ? "Creating..." : "Create Policy"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="mb-4">
        <label className="mb-1 block text-xs font-medium text-zinc-300">
          Direction
        </label>
        <select
          value={dirFilter}
          onChange={(e) => {
            setDirFilter(e.target.value);
            setPage(0);
          }}
          className="rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1 text-sm text-zinc-200 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
        >
          {DIRECTION_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Table */}
      {error && (
        <p className="mb-4 text-sm text-red-400">{error}</p>
      )}
      {loading ? (
        <p className="text-sm text-zinc-500">Loading policies...</p>
      ) : policies.length === 0 ? (
        <p className="py-8 text-center text-sm text-zinc-500">
          No network policies configured yet. All projects use the default
          deny-all egress posture.
        </p>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-zinc-800">
            <table className="min-w-full divide-y divide-zinc-800 text-sm">
              <thead className="bg-zinc-900/50">
                <tr>
                  <th className="px-4 py-2 text-left font-medium text-zinc-400">
                    Name
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-zinc-400">
                    Project
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-zinc-400">
                    Direction
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-zinc-400">
                    Rule
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-zinc-400">
                    Action
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-zinc-400">
                    Status
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-zinc-400">
                    Created
                  </th>
                  {isFaculty && (
                    <th className="px-4 py-2 text-right font-medium text-zinc-400">
                      Actions
                    </th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {policies.map((p) => (
                  <tr key={p.id} className="hover:bg-zinc-800/50">
                    <td className="px-4 py-2 text-xs font-medium text-zinc-100">
                      {p.name}
                    </td>
                    <td className="px-4 py-2 text-xs text-zinc-400">
                      {p.project_name ?? p.project_id.slice(0, 8)}
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                          p.direction === "egress"
                            ? "bg-orange-950/30 text-orange-400"
                            : "bg-sky-950/30 text-sky-400"
                        }`}
                      >
                        {p.direction}
                      </span>
                    </td>
                    <td className="px-4 py-2">
                      <code className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-xs text-zinc-300">
                        {p.protocol.toUpperCase()}
                        {p.port ? `:${p.port}` : ""} &rarr; {p.destination}
                      </code>
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                          p.action === "allow"
                            ? "bg-green-950/30 text-green-400"
                            : "bg-red-950/30 text-red-400"
                        }`}
                      >
                        {p.action}
                      </span>
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                          p.enabled
                            ? "bg-green-950/30 text-green-400"
                            : "bg-zinc-800 text-zinc-500"
                        }`}
                      >
                        {p.enabled ? "Active" : "Disabled"}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-2 text-xs text-zinc-500">
                      {formatDate(p.created_at)}
                    </td>
                    {isFaculty && (
                      <td className="px-4 py-2 text-right">
                        <div className="flex justify-end gap-1">
                          <button
                            onClick={() => handleToggle(p)}
                            disabled={toggling === p.id}
                            className="rounded-lg border border-zinc-700 px-2 py-0.5 text-xs text-zinc-400 hover:bg-zinc-800/50 disabled:opacity-50"
                          >
                            {toggling === p.id
                              ? "..."
                              : p.enabled
                                ? "Disable"
                                : "Enable"}
                          </button>
                          <button
                            onClick={() => setDeleteConfirmId(p.id)}
                            disabled={deleting === p.id}
                            className="rounded-lg border border-red-900 px-2 py-0.5 text-xs text-red-400 hover:bg-red-950/30 disabled:opacity-50"
                          >
                            {deleting === p.id ? "..." : "Delete"}
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-3 flex items-center justify-between text-sm">
              <p className="text-xs text-zinc-500">
                Page {page + 1} of {totalPages}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="rounded-lg border border-zinc-700 px-3 py-1 text-xs text-zinc-400 disabled:opacity-50"
                >
                  Previous
                </button>
                <button
                  onClick={() =>
                    setPage((p) => Math.min(totalPages - 1, p + 1))
                  }
                  disabled={page >= totalPages - 1}
                  className="rounded-lg border border-zinc-700 px-3 py-1 text-xs text-zinc-400 disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}

      <ConfirmModal
        open={deleteConfirmId !== null}
        onClose={() => setDeleteConfirmId(null)}
        onConfirm={() => deleteConfirmId && handleDelete(deleteConfirmId)}
        title="Delete Network Policy"
        description="Are you sure you want to delete this network policy? This action cannot be undone."
        confirmLabel="Delete"
        variant="danger"
        loading={deleting !== null}
      />
    </div>
  );
}

function SummaryCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: number;
  sub?: string;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
      <p className="text-xs font-medium text-zinc-500">
        {label}
        {sub && (
          <span className="ml-1 font-normal text-zinc-500">({sub})</span>
        )}
      </p>
      <p className="mt-1 text-2xl font-bold text-zinc-100">{value}</p>
    </div>
  );
}
