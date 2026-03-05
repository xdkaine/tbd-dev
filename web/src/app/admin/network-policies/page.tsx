"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/auth";
import { formatDate } from "@/lib/utils";
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
      const res = await api.admin.networkPolicies.list({
        skip: page * limit,
        limit,
        direction: dirFilter || undefined,
      });
      setPolicies(res.items);
      setTotal(res.total);
    } catch {
      /* */
    } finally {
      setLoading(false);
    }
  }, [page, dirFilter]);

  const fetchProjects = useCallback(async () => {
    try {
      const res = await api.projects.list(0, 200);
      setProjects(res.items);
    } catch {
      /* */
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
      <p className="text-sm text-red-600">
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
    } catch {
      /* */
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(policyId: string) {
    if (!confirm("Delete this network policy?")) return;
    setDeleting(policyId);
    try {
      await api.admin.networkPolicies.delete(policyId);
      await fetchPolicies();
    } catch {
      /* */
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
    } catch {
      /* */
    } finally {
      setToggling(null);
    }
  }

  return (
    <div>
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            Network Policies
          </h1>
          <p className="text-sm text-gray-500">
            Firewall rules per project &mdash; default posture is deny-all
            egress
          </p>
        </div>
        {isFaculty && (
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
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
        <div className="mb-6 rounded-lg border border-brand-200 bg-brand-50 p-4">
          <h3 className="mb-3 text-sm font-semibold text-gray-900">
            Create Network Policy
          </h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                Project
              </label>
              <select
                value={createForm.project_id}
                onChange={(e) =>
                  setCreateForm({ ...createForm, project_id: e.target.value })
                }
                className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
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
              <label className="mb-1 block text-xs font-medium text-gray-700">
                Name
              </label>
              <input
                type="text"
                value={createForm.name}
                onChange={(e) =>
                  setCreateForm({ ...createForm, name: e.target.value })
                }
                className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
                placeholder="e.g. Allow HTTPS"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
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
                className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
              >
                <option value="egress">Egress</option>
                <option value="ingress">Ingress</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
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
                className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
              >
                <option value="tcp">TCP</option>
                <option value="udp">UDP</option>
                <option value="icmp">ICMP</option>
                <option value="any">Any</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
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
                className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
                placeholder="e.g. 443"
                min={1}
                max={65535}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
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
                className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
                placeholder="e.g. 0.0.0.0/0"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
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
                className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
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
                className="rounded bg-brand-600 px-4 py-1 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
              >
                {saving ? "Creating..." : "Create Policy"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="mb-4">
        <label className="mb-1 block text-xs font-medium text-gray-700">
          Direction
        </label>
        <select
          value={dirFilter}
          onChange={(e) => {
            setDirFilter(e.target.value);
            setPage(0);
          }}
          className="rounded-md border border-gray-300 px-2 py-1 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          {DIRECTION_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Table */}
      {loading ? (
        <p className="text-sm text-gray-500">Loading policies...</p>
      ) : policies.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-500">
          No network policies configured yet. All projects use the default
          deny-all egress posture.
        </p>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-gray-200">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left font-medium text-gray-500">
                    Name
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-gray-500">
                    Project
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-gray-500">
                    Direction
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-gray-500">
                    Rule
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-gray-500">
                    Action
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-gray-500">
                    Status
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-gray-500">
                    Created
                  </th>
                  {isFaculty && (
                    <th className="px-4 py-2 text-right font-medium text-gray-500">
                      Actions
                    </th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {policies.map((p) => (
                  <tr key={p.id} className="hover:bg-gray-50">
                    <td className="px-4 py-2 text-xs font-medium text-gray-900">
                      {p.name}
                    </td>
                    <td className="px-4 py-2 text-xs text-gray-600">
                      {p.project_name ?? p.project_id.slice(0, 8)}
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                          p.direction === "egress"
                            ? "bg-orange-100 text-orange-700"
                            : "bg-sky-100 text-sky-700"
                        }`}
                      >
                        {p.direction}
                      </span>
                    </td>
                    <td className="px-4 py-2">
                      <code className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-xs text-gray-700">
                        {p.protocol.toUpperCase()}
                        {p.port ? `:${p.port}` : ""} &rarr; {p.destination}
                      </code>
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                          p.action === "allow"
                            ? "bg-green-100 text-green-700"
                            : "bg-red-100 text-red-700"
                        }`}
                      >
                        {p.action}
                      </span>
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                          p.enabled
                            ? "bg-green-100 text-green-700"
                            : "bg-gray-100 text-gray-500"
                        }`}
                      >
                        {p.enabled ? "Active" : "Disabled"}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-2 text-xs text-gray-500">
                      {formatDate(p.created_at)}
                    </td>
                    {isFaculty && (
                      <td className="px-4 py-2 text-right">
                        <div className="flex justify-end gap-1">
                          <button
                            onClick={() => handleToggle(p)}
                            disabled={toggling === p.id}
                            className="rounded border border-gray-300 px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                          >
                            {toggling === p.id
                              ? "..."
                              : p.enabled
                                ? "Disable"
                                : "Enable"}
                          </button>
                          <button
                            onClick={() => handleDelete(p.id)}
                            disabled={deleting === p.id}
                            className="rounded border border-red-200 px-2 py-0.5 text-xs text-red-600 hover:bg-red-50 disabled:opacity-50"
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
              <p className="text-xs text-gray-500">
                Page {page + 1} of {totalPages}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="rounded border border-gray-300 px-3 py-1 text-xs disabled:opacity-50"
                >
                  Previous
                </button>
                <button
                  onClick={() =>
                    setPage((p) => Math.min(totalPages - 1, p + 1))
                  }
                  disabled={page >= totalPages - 1}
                  className="rounded border border-gray-300 px-3 py-1 text-xs disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
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
    <div className="rounded-lg border border-gray-200 p-4">
      <p className="text-xs font-medium text-gray-500">
        {label}
        {sub && (
          <span className="ml-1 font-normal text-gray-400">({sub})</span>
        )}
      </p>
      <p className="mt-1 text-2xl font-bold text-gray-900">{value}</p>
    </div>
  );
}
