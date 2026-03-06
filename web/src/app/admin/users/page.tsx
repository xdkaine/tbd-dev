"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/auth";
import { formatDate } from "@/lib/utils";
import type { AdminUser } from "@/lib/types";

const ROLE_OPTIONS = [
  { value: "", label: "All Roles" },
  { value: "JAS_Developer", label: "Developer" },
  { value: "JAS-Staff", label: "Staff" },
  { value: "JAS-Faculty", label: "Faculty" },
];

const ROLE_LABELS: Record<string, string> = {
  JAS_Developer: "Developer",
  "JAS-Staff": "Staff",
  "JAS-Faculty": "Faculty",
};

const ROLE_COLORS: Record<string, string> = {
  JAS_Developer:
    "bg-blue-950/30 text-blue-400",
  "JAS-Staff":
    "bg-amber-950/30 text-amber-400",
  "JAS-Faculty":
    "bg-purple-950/30 text-purple-400",
};

export default function UsersPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [page, setPage] = useState(0);
  const [roleEditUserId, setRoleEditUserId] = useState<string | null>(null);
  const [roleEditValue, setRoleEditValue] = useState("");
  const [saving, setSaving] = useState(false);
  const limit = 25;

  const isFaculty = user?.role === "JAS-Faculty";

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.admin.users.list({
        skip: page * limit,
        limit,
        search: search || undefined,
        role: roleFilter || undefined,
      });
      setUsers(res.items);
      setTotal(res.total);
    } catch {
      /* */
    } finally {
      setLoading(false);
    }
  }, [page, search, roleFilter]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  if (user && user.role === "JAS_Developer") {
    return (
      <p className="text-sm text-red-400">
        You do not have permission to view this page.
      </p>
    );
  }

  const totalPages = Math.ceil(total / limit);

  // Role distribution counts
  const devCount = users.filter((u) => u.role === "JAS_Developer").length;
  const staffCount = users.filter((u) => u.role === "JAS-Staff").length;
  const facultyCount = users.filter((u) => u.role === "JAS-Faculty").length;

  function startRoleEdit(u: AdminUser) {
    setRoleEditUserId(u.id);
    setRoleEditValue(u.role);
  }

  function cancelRoleEdit() {
    setRoleEditUserId(null);
    setRoleEditValue("");
  }

  async function saveRole(userId: string) {
    setSaving(true);
    try {
      await api.admin.users.updateRole(userId, roleEditValue);
      setRoleEditUserId(null);
      setRoleEditValue("");
      await fetchUsers();
    } catch {
      /* */
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-zinc-100">User Management</h1>
        <p className="text-sm text-zinc-500">
          Platform users and role assignments &mdash; {total} total users
        </p>
      </div>

      {/* Summary cards */}
      <div className="mb-6 grid gap-4 sm:grid-cols-4">
        <SummaryCard label="Total Users" value={total} />
        <SummaryCard label="Developers" value={devCount} sub="this page" />
        <SummaryCard label="Staff" value={staffCount} sub="this page" />
        <SummaryCard label="Faculty" value={facultyCount} sub="this page" />
      </div>

      {/* Filters */}
      <div className="mb-4 flex gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-zinc-300">
            Search
          </label>
          <input
            type="text"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            className="rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1 text-sm text-zinc-200 placeholder-zinc-600 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
            placeholder="Username or name..."
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-zinc-300">
            Role
          </label>
          <select
            value={roleFilter}
            onChange={(e) => {
              setRoleFilter(e.target.value);
              setPage(0);
            }}
            className="rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1 text-sm text-zinc-200 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
          >
            {ROLE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <p className="text-sm text-zinc-500">Loading users...</p>
      ) : users.length === 0 ? (
        <p className="py-8 text-center text-sm text-zinc-500">
          No users found.
        </p>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-zinc-800">
            <table className="min-w-full divide-y divide-zinc-800 text-sm">
              <thead className="bg-zinc-900/50">
                <tr>
                  <th className="px-4 py-2 text-left font-medium text-zinc-400">
                    User
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-zinc-400">
                    Email
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-zinc-400">
                    Role
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-zinc-400">
                    GitHub
                  </th>
                  <th className="px-4 py-2 text-right font-medium text-zinc-400">
                    Projects
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-zinc-400">
                    Joined
                  </th>
                  {isFaculty && (
                    <th className="px-4 py-2 text-right font-medium text-zinc-400">
                      Actions
                    </th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {users.map((u) => {
                  const isEditingRole = roleEditUserId === u.id;
                  const isSelf = u.id === user?.id;

                  return (
                    <tr key={u.id} className="hover:bg-zinc-800/50">
                      <td className="px-4 py-2">
                        <div>
                          <p className="font-medium text-zinc-100">
                            {u.display_name}
                            {isSelf && (
                              <span className="ml-1 text-xs text-zinc-500">
                                (you)
                              </span>
                            )}
                          </p>
                          <p className="font-mono text-xs text-zinc-500">
                            {u.username}
                          </p>
                        </div>
                      </td>
                      <td className="px-4 py-2 text-xs text-zinc-400">
                        {u.email}
                      </td>
                      <td className="px-4 py-2">
                        {isEditingRole ? (
                          <select
                            value={roleEditValue}
                            onChange={(e) => setRoleEditValue(e.target.value)}
                            className="rounded-lg border border-zinc-800 bg-zinc-950 px-1.5 py-0.5 text-xs text-zinc-200"
                          >
                            <option value="JAS_Developer">Developer</option>
                            <option value="JAS-Staff">Staff</option>
                            <option value="JAS-Faculty">Faculty</option>
                          </select>
                        ) : (
                          <span
                            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${ROLE_COLORS[u.role] ?? "bg-zinc-800 text-zinc-400"}`}
                          >
                            {ROLE_LABELS[u.role] ?? u.role}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2 text-xs text-zinc-500">
                        {u.github_username ? (
                          <span className="font-mono text-xs text-zinc-300">
                            @{u.github_username}
                          </span>
                        ) : (
                          <span className="text-zinc-500">Not linked</span>
                        )}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-xs font-semibold text-zinc-100">
                        {u.project_count}
                      </td>
                      <td className="whitespace-nowrap px-4 py-2 text-xs text-zinc-500">
                        {formatDate(u.created_at)}
                      </td>
                      {isFaculty && (
                        <td className="px-4 py-2 text-right">
                          {isSelf ? (
                            <span className="text-xs text-zinc-500">
                              &mdash;
                            </span>
                          ) : isEditingRole ? (
                            <div className="flex justify-end gap-1">
                              <button
                                onClick={() => saveRole(u.id)}
                                disabled={saving}
                                className="rounded-lg bg-brand-500 px-2 py-0.5 text-xs font-medium text-black hover:bg-brand-400 disabled:opacity-50"
                              >
                                {saving ? "Saving..." : "Save"}
                              </button>
                              <button
                                onClick={cancelRoleEdit}
                                className="rounded-lg border border-zinc-700 px-2 py-0.5 text-xs text-zinc-400 hover:bg-zinc-800/50"
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => startRoleEdit(u)}
                              className="rounded-lg border border-zinc-700 px-2 py-0.5 text-xs text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
                            >
                              Edit Role
                            </button>
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })}
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
