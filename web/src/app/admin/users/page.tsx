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
    "bg-blue-100 text-blue-700",
  "JAS-Staff":
    "bg-amber-100 text-amber-700",
  "JAS-Faculty":
    "bg-purple-100 text-purple-700",
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
      <p className="text-sm text-red-600">
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
        <h1 className="text-2xl font-bold text-gray-900">User Management</h1>
        <p className="text-sm text-gray-500">
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
          <label className="mb-1 block text-xs font-medium text-gray-700">
            Search
          </label>
          <input
            type="text"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            className="rounded-md border border-gray-300 px-2 py-1 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            placeholder="Username or name..."
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-700">
            Role
          </label>
          <select
            value={roleFilter}
            onChange={(e) => {
              setRoleFilter(e.target.value);
              setPage(0);
            }}
            className="rounded-md border border-gray-300 px-2 py-1 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
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
        <p className="text-sm text-gray-500">Loading users...</p>
      ) : users.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-500">
          No users found.
        </p>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-gray-200">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left font-medium text-gray-500">
                    User
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-gray-500">
                    Email
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-gray-500">
                    Role
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-gray-500">
                    GitHub
                  </th>
                  <th className="px-4 py-2 text-right font-medium text-gray-500">
                    Projects
                  </th>
                  <th className="px-4 py-2 text-left font-medium text-gray-500">
                    Joined
                  </th>
                  {isFaculty && (
                    <th className="px-4 py-2 text-right font-medium text-gray-500">
                      Actions
                    </th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {users.map((u) => {
                  const isEditingRole = roleEditUserId === u.id;
                  const isSelf = u.id === user?.id;

                  return (
                    <tr key={u.id} className="hover:bg-gray-50">
                      <td className="px-4 py-2">
                        <div>
                          <p className="font-medium text-gray-900">
                            {u.display_name}
                            {isSelf && (
                              <span className="ml-1 text-xs text-gray-400">
                                (you)
                              </span>
                            )}
                          </p>
                          <p className="font-mono text-xs text-gray-400">
                            {u.username}
                          </p>
                        </div>
                      </td>
                      <td className="px-4 py-2 text-xs text-gray-600">
                        {u.email}
                      </td>
                      <td className="px-4 py-2">
                        {isEditingRole ? (
                          <select
                            value={roleEditValue}
                            onChange={(e) => setRoleEditValue(e.target.value)}
                            className="rounded border border-gray-300 px-1.5 py-0.5 text-xs"
                          >
                            <option value="JAS_Developer">Developer</option>
                            <option value="JAS-Staff">Staff</option>
                            <option value="JAS-Faculty">Faculty</option>
                          </select>
                        ) : (
                          <span
                            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${ROLE_COLORS[u.role] ?? "bg-gray-100 text-gray-600"}`}
                          >
                            {ROLE_LABELS[u.role] ?? u.role}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2 text-xs text-gray-500">
                        {u.github_username ? (
                          <span className="font-mono text-xs text-gray-700">
                            @{u.github_username}
                          </span>
                        ) : (
                          <span className="text-gray-400">Not linked</span>
                        )}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-xs font-semibold text-gray-900">
                        {u.project_count}
                      </td>
                      <td className="whitespace-nowrap px-4 py-2 text-xs text-gray-500">
                        {formatDate(u.created_at)}
                      </td>
                      {isFaculty && (
                        <td className="px-4 py-2 text-right">
                          {isSelf ? (
                            <span className="text-xs text-gray-400">
                              &mdash;
                            </span>
                          ) : isEditingRole ? (
                            <div className="flex justify-end gap-1">
                              <button
                                onClick={() => saveRole(u.id)}
                                disabled={saving}
                                className="rounded bg-brand-600 px-2 py-0.5 text-xs font-medium text-white hover:bg-brand-700 disabled:opacity-50"
                              >
                                {saving ? "Saving..." : "Save"}
                              </button>
                              <button
                                onClick={cancelRoleEdit}
                                className="rounded border border-gray-300 px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-50"
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => startRoleEdit(u)}
                              className="rounded border border-gray-300 px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-50 hover:text-gray-900"
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
