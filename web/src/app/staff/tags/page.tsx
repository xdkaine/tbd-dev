"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { AdminProjectItem } from "@/lib/types";

export default function StaffTagsPage() {
  const [projects, setProjects] = useState<AdminProjectItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTag, setSelectedTag] = useState<string | null>(null);

  const fetchProjects = useCallback(async () => {
    setLoading(true);
    try {
      setError(null);
      const res = await api.admin.projects({
        limit: 200,
        tag: selectedTag || undefined,
      });
      setProjects(res.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  }, [selectedTag]);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  // Collect all unique tags and their counts
  const tagCounts = projects.reduce<Record<string, number>>((acc, p) => {
    p.tags.forEach((t) => {
      acc[t] = (acc[t] || 0) + 1;
    });
    return acc;
  }, {});

  const allTags = Object.entries(tagCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([tag, count]) => ({ tag, count }));

  // When no tag is selected, show all projects; when selected, the API filters
  const filteredProjects = projects;

  return (
    <div className="max-w-7xl">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-zinc-100">Tags</h1>
        <p className="text-sm text-zinc-500">
          Browse projects organized by tags
        </p>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/5 p-3">
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-3 py-12 text-sm text-zinc-500">
          <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading tags...
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-4">
          {/* Tag list sidebar */}
          <div className="lg:col-span-1">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50">
              <div className="border-b border-zinc-800 px-4 py-3">
                <h2 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                  Tags ({allTags.length})
                </h2>
              </div>
              <div className="max-h-[500px] overflow-y-auto">
                <button
                  onClick={() => setSelectedTag(null)}
                  className={`flex w-full items-center justify-between px-4 py-2 text-left text-xs transition-colors ${
                    selectedTag === null
                      ? "bg-brand-500/10 text-brand-400"
                      : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
                  }`}
                >
                  <span>All projects</span>
                  <span className="tabular-nums text-zinc-600">
                    {projects.length}
                  </span>
                </button>
                {allTags.map(({ tag, count }) => (
                  <button
                    key={tag}
                    onClick={() => setSelectedTag(tag)}
                    className={`flex w-full items-center justify-between px-4 py-2 text-left text-xs transition-colors ${
                      selectedTag === tag
                        ? "bg-brand-500/10 text-brand-400"
                        : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
                    }`}
                  >
                    <span className="truncate">{tag}</span>
                    <span className="ml-2 flex-shrink-0 tabular-nums text-zinc-600">
                      {count}
                    </span>
                  </button>
                ))}
                {allTags.length === 0 && (
                  <p className="px-4 py-6 text-center text-xs text-zinc-600">
                    No tags found
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Project list */}
          <div className="lg:col-span-3">
            {selectedTag && (
              <div className="mb-4 flex items-center gap-2">
                <span className="rounded bg-brand-500/10 px-2 py-1 text-xs font-medium text-brand-400">
                  {selectedTag}
                </span>
                <span className="text-xs text-zinc-500">
                  {filteredProjects.length} project{filteredProjects.length !== 1 ? "s" : ""}
                </span>
                <button
                  onClick={() => setSelectedTag(null)}
                  className="ml-auto text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
                >
                  Clear filter
                </button>
              </div>
            )}

            {filteredProjects.length === 0 ? (
              <p className="py-12 text-center text-sm text-zinc-500">
                No projects found{selectedTag ? ` with tag "${selectedTag}"` : ""}.
              </p>
            ) : (
              <div className="space-y-2">
                {filteredProjects.map((p) => (
                  <div
                    key={p.id}
                    className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 transition-all hover:bg-zinc-900/80"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <Link
                          href={`/dashboard/${p.id}`}
                          className="font-medium text-zinc-100 hover:text-brand-400 transition-colors text-sm"
                        >
                          {p.name}
                          <span className="ml-1.5 text-xs text-zinc-600">/{p.slug}</span>
                        </Link>
                        <p className="mt-0.5 text-xs text-zinc-500">
                          {p.owner_display_name}
                          <span className="ml-1 text-zinc-600">@{p.owner_username}</span>
                          {p.framework && (
                            <span className="ml-2 text-zinc-600">{p.framework}</span>
                          )}
                        </p>
                      </div>
                      <div className="flex items-center gap-3 text-xs tabular-nums text-zinc-500">
                        <span>{p.total_deploys}d</span>
                        <span>{p.total_builds}b</span>
                        <span className="text-zinc-600">{formatDate(p.created_at)}</span>
                      </div>
                    </div>
                    {p.tags.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {p.tags.map((tag) => (
                          <button
                            key={tag}
                            onClick={() => setSelectedTag(tag)}
                            className={`rounded px-1.5 py-0.5 text-[10px] transition-colors ${
                              tag === selectedTag
                                ? "bg-brand-500/20 text-brand-400"
                                : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-300"
                            }`}
                          >
                            {tag}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
