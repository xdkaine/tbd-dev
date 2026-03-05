"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { slugify, timeAgo } from "@/lib/utils";
import type { GitHubRepo, Project } from "@/lib/types";
import { useAuth } from "@/contexts/auth";

export default function DashboardPage() {
  const { user } = useAuth();
  const [projects, setProjects] = useState<Project[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [showImport, setShowImport] = useState(false);

  const fetchProjects = useCallback(async () => {
    try {
      const res = await api.projects.list();
      setProjects(res.items);
      setTotal(res.total);
    } catch {
      /* handled by API layer */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const githubLinked = !!user?.github_username;

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Projects</h1>
          <p className="text-sm text-gray-500">
            {total} project{total !== 1 ? "s" : ""}
          </p>
        </div>
        <button
          onClick={() => setShowImport(true)}
          className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          Add New...
        </button>
      </div>

      {/* Import from GitHub panel */}
      {showImport && (
        githubLinked ? (
          <ImportFromGitHub
            onImported={() => {
              setShowImport(false);
              fetchProjects();
            }}
            onCancel={() => setShowImport(false)}
          />
        ) : (
          <ConnectGitHubPrompt onCancel={() => setShowImport(false)} />
        )
      )}

      {/* Project list */}
      {loading ? (
        <p className="text-sm text-gray-500">Loading projects...</p>
      ) : projects.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-12 text-center">
          <svg
            className="mx-auto h-10 w-10 text-gray-300"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 4.5v15m7.5-7.5h-15"
            />
          </svg>
          <h3 className="mt-3 text-sm font-semibold text-gray-900">
            No projects yet
          </h3>
          <p className="mt-1 text-sm text-gray-500">
            Import a GitHub repository to get started.
          </p>
          <button
            onClick={() => setShowImport(true)}
            className="mt-4 rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            Import GitHub Repository
          </button>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <Link
              key={project.id}
              href={`/dashboard/${project.id}`}
              className="rounded-lg border border-gray-200 p-4 transition hover:border-brand-300 hover:shadow-sm"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2 min-w-0">
                  <h3 className="font-semibold text-gray-900 truncate">{project.name}</h3>
                  {user && project.owner_id !== user.id && (
                    <span className="inline-flex flex-shrink-0 items-center rounded-md bg-brand-50 px-1.5 py-0.5 text-xs font-medium text-brand-700 ring-1 ring-inset ring-brand-200">
                      Contributor
                    </span>
                  )}
                </div>
                {project.repo?.repo_full_name && (
                  <span className="ml-2 flex-shrink-0">
                    <svg className="h-4 w-4 text-gray-400" viewBox="0 0 16 16" fill="currentColor">
                      <path d="M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z" />
                    </svg>
                  </span>
                )}
              </div>
              {project.repo?.repo_full_name ? (
                <p className="mt-1 truncate text-xs text-gray-400">
                  {project.repo.repo_full_name}
                </p>
              ) : project.repo_url ? (
                <p className="mt-1 truncate text-xs text-gray-400">
                  {project.repo_url}
                </p>
              ) : null}
              <div className="mt-2 flex items-center gap-2">
                {project.framework && (
                  <span className="inline-flex items-center rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">
                    {project.framework}
                  </span>
                )}
                <span className="text-xs text-gray-400">
                  {timeAgo(project.created_at)}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  Prompt to connect GitHub account                                       */
/* ---------------------------------------------------------------------- */

function ConnectGitHubPrompt({ onCancel }: { onCancel: () => void }) {
  const [loading, setLoading] = useState(false);

  async function handleConnect() {
    setLoading(true);
    try {
      const { authorize_url } = await api.auth.githubAuthorizeUrl();
      window.location.href = authorize_url;
    } catch {
      setLoading(false);
    }
  }

  return (
    <div className="mb-6 rounded-lg border border-yellow-200 bg-yellow-50 p-6">
      <div className="flex items-start gap-4">
        <div className="flex-shrink-0">
          <svg className="h-8 w-8 text-gray-700" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z" />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-gray-900">
            Connect your GitHub account
          </h3>
          <p className="mt-1 text-sm text-gray-600">
            To import a repository, you need to connect your GitHub account first.
            This allows TBD to access your repositories and set up automatic deployments.
          </p>
          <div className="mt-4 flex gap-2">
            <button
              onClick={handleConnect}
              disabled={loading}
              className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
            >
              {loading ? "Redirecting..." : "Connect GitHub"}
            </button>
            <button
              onClick={onCancel}
              className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  Import from GitHub flow                                                */
/* ---------------------------------------------------------------------- */

function ImportFromGitHub({
  onImported,
  onCancel,
}: {
  onImported: () => void;
  onCancel: () => void;
}) {
  const router = useRouter();
  const { user } = useAuth();
  const [repos, setRepos] = useState<GitHubRepo[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [importing, setImporting] = useState<number | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await api.github.listRepos();
        setRepos(data);
      } catch (err) {
        if (err instanceof ApiError) setError(err.detail);
        else setError("Failed to load repositories");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function handleImport(repo: GitHubRepo) {
    setImporting(repo.id);
    setError("");

    const slug = slugify(repo.name);

    try {
      // Step 1: Create the project
      const project = await api.projects.create({
        name: repo.name,
        slug,
        repo_url: repo.html_url,
      });

      // Step 2: Connect the repo (creates webhook via OAuth + links repo)
      await api.projects.connectRepo(project.id, {
        repo_id: repo.id,
        repo_full_name: repo.full_name,
        default_branch: repo.default_branch,
      });

      // Navigate to the new project
      router.push(`/dashboard/${project.id}`);
    } catch (err) {
      if (err instanceof ApiError) setError(err.detail);
      else setError("Failed to import repository");
    } finally {
      setImporting(null);
    }
  }

  const filtered = repos.filter((r) =>
    r.full_name.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="mb-6 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-gray-900">
            Import Git Repository
          </h2>
          {user?.github_username && (
            <p className="text-xs text-gray-500">
              Showing repositories for{" "}
              <span className="font-medium">{user.github_username}</span>
            </p>
          )}
        </div>
        <button
          onClick={onCancel}
          className="text-xs text-gray-500 hover:text-gray-700"
        >
          Cancel
        </button>
      </div>

      {error && <p className="mb-2 text-xs text-red-600">{error}</p>}

      {loading ? (
        <div className="flex items-center gap-2 py-8 text-sm text-gray-500">
          <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading repositories from GitHub...
        </div>
      ) : (
        <>
          <input
            type="text"
            placeholder="Search repositories..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            autoFocus
            className="mb-3 block w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
          <div className="max-h-80 space-y-1 overflow-y-auto">
            {filtered.length === 0 ? (
              <p className="py-6 text-center text-sm text-gray-500">
                {repos.length === 0
                  ? "No repositories found."
                  : "No matching repositories."}
              </p>
            ) : (
              filtered.map((repo) => (
                <div
                  key={repo.id}
                  className="flex items-center justify-between rounded-md border border-gray-100 bg-gray-50 px-3 py-2.5"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-gray-900">
                        {repo.full_name}
                      </p>
                      {repo.private && (
                        <span className="rounded bg-yellow-100 px-1.5 py-0.5 text-xs text-yellow-700">
                          private
                        </span>
                      )}
                    </div>
                    {repo.description && (
                      <p className="truncate text-xs text-gray-500">
                        {repo.description}
                      </p>
                    )}
                  </div>
                  <div className="ml-3 flex-shrink-0">
                    <button
                      onClick={() => handleImport(repo)}
                      disabled={importing !== null}
                      className="rounded-md bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-700 disabled:opacity-50"
                    >
                      {importing === repo.id ? "Importing..." : "Import"}
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}
