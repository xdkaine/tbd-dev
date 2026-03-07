"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getDeployActivity, slugify, timeAgo } from "@/lib/utils";
import type { Deploy, DeployStatus, GitHubRepo, Project, UserInfo } from "@/lib/types";
import { useAuth } from "@/contexts/auth";
import { TemplateGallery } from "@/components/template-gallery";

type AddMode = null | "choose" | "import" | "template";

export default function DashboardPage() {
  const { user } = useAuth();
  const [projects, setProjects] = useState<Project[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [deploysLoading, setDeploysLoading] = useState(false);
  const [deploysMap, setDeploysMap] = useState<Record<string, Deploy[]>>({});
  const [addMode, setAddMode] = useState<AddMode>(null);

  const fetchProjects = useCallback(async () => {
    try {
      const res = await api.projects.list();
      const items = res.items;
      setProjects(items);
      setTotal(res.total);
      setDeploysLoading(true);
      Promise.allSettled(
        items.map((project) => api.deploys.list(project.id, 0, 20)),
      )
        .then((results) => {
          const nextDeploys: Record<string, Deploy[]> = {};
          results.forEach((result, index) => {
            const projectId = items[index]?.id;
            if (!projectId) return;
            if (result.status === "fulfilled") {
              nextDeploys[projectId] = [...result.value.items].sort(
                (a, b) =>
                  new Date(b.created_at).getTime() -
                  new Date(a.created_at).getTime(),
              );
            } else {
              nextDeploys[projectId] = [];
            }
          });
          setDeploysMap(nextDeploys);
        })
        .finally(() => {
          setDeploysLoading(false);
        });
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
          <h1 className="text-2xl font-bold text-zinc-100">Projects</h1>
          <p className="text-sm text-zinc-500">
            {total} project{total !== 1 ? "s" : ""}
          </p>
        </div>
        <button
          onClick={() => setAddMode("choose")}
          className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-black hover:bg-brand-400 transition-colors"
        >
          Add New...
        </button>
      </div>

      {/* Add-new chooser */}
      {addMode === "choose" && (
        <div className="mb-6 rounded-xl border border-zinc-800 bg-zinc-900/80 p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-zinc-200">
              Create a new project
            </h2>
            <button
              onClick={() => setAddMode(null)}
              className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              Cancel
            </button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <button
              onClick={() => setAddMode("import")}
              className="group flex items-start gap-3 rounded-lg border border-zinc-800 bg-zinc-800/30 p-4 text-left transition-all hover:border-brand-500/40 hover:bg-zinc-800/60"
            >
              <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-zinc-800 text-zinc-400 group-hover:text-brand-400 transition-colors">
                <svg className="h-5 w-5" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z" />
                </svg>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-zinc-200">
                  Import GitHub Repository
                </h3>
                <p className="mt-0.5 text-xs text-zinc-500">
                  Connect an existing repo and deploy it
                </p>
              </div>
            </button>
            <button
              onClick={() => {
                if (!githubLinked) {
                  setAddMode("import"); // will show ConnectGitHubPrompt
                } else {
                  setAddMode("template");
                }
              }}
              className="group flex items-start gap-3 rounded-lg border border-zinc-800 bg-zinc-800/30 p-4 text-left transition-all hover:border-brand-500/40 hover:bg-zinc-800/60"
            >
              <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-zinc-800 text-zinc-400 group-hover:text-brand-400 transition-colors">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 0 1 6 3.75h2.25A2.25 2.25 0 0 1 10.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H6a2.25 2.25 0 0 1-2.25-2.25V6ZM3.75 15.75A2.25 2.25 0 0 1 6 13.5h2.25a2.25 2.25 0 0 1 2.25 2.25V18a2.25 2.25 0 0 1-2.25 2.25H6A2.25 2.25 0 0 1 3.75 18v-2.25ZM13.5 6a2.25 2.25 0 0 1 2.25-2.25H18A2.25 2.25 0 0 1 20.25 6v2.25A2.25 2.25 0 0 1 18 10.5h-2.25a2.25 2.25 0 0 1-2.25-2.25V6ZM13.5 15.75a2.25 2.25 0 0 1 2.25-2.25H18a2.25 2.25 0 0 1 2.25 2.25V18A2.25 2.25 0 0 1 18 20.25h-2.25A2.25 2.25 0 0 1 13.5 18v-2.25Z" />
                </svg>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-zinc-200">
                  Start from Template
                </h3>
                <p className="mt-0.5 text-xs text-zinc-500">
                  Pick a starter project and deploy instantly
                </p>
              </div>
            </button>
          </div>
        </div>
      )}

      {/* Import from GitHub panel */}
      {addMode === "import" && (
        githubLinked ? (
          <ImportFromGitHub
            onImported={() => {
              setAddMode(null);
              fetchProjects();
            }}
            onCancel={() => setAddMode(null)}
          />
        ) : (
          <ConnectGitHubPrompt onCancel={() => setAddMode(null)} />
        )
      )}

      {/* Template gallery panel */}
      {addMode === "template" && (
        <TemplateGallery
          onDeployed={() => {
            setAddMode(null);
            fetchProjects();
          }}
          onCancel={() => setAddMode(null)}
        />
      )}

      {/* Project list */}
      {loading ? (
        <p className="text-sm text-zinc-500">Loading projects...</p>
      ) : projects.length === 0 ? (
        <div className="rounded-xl border border-dashed border-zinc-800 p-12 text-center">
          <svg
            className="mx-auto h-10 w-10 text-zinc-700"
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
          <h3 className="mt-3 text-sm font-semibold text-zinc-200">
            No projects yet
          </h3>
          <p className="mt-1 text-sm text-zinc-500">
            Import a GitHub repository or start from a template.
          </p>
          <button
            onClick={() => setAddMode("choose")}
            className="mt-4 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-black hover:bg-brand-400 transition-colors"
          >
            Get Started
          </button>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              deploys={deploysMap[project.id] ?? []}
              deploysLoading={deploysLoading}
              user={user}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ProjectCard({
  project,
  deploys,
  deploysLoading,
  user,
}: {
  project: Project;
  deploys: Deploy[];
  deploysLoading: boolean;
  user: UserInfo | null;
}) {
  const latestDeploy = deploys[0];
  const activity = useMemo(() => getDeployActivity(deploys, 7), [deploys]);
  const maxActivity = Math.max(...activity.map((item) => item.count), 1);
  const statusTone = getStatusTone(latestDeploy?.status);

  return (
    <Link
      href={`/dashboard/${project.id}`}
      className="group relative overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 transition-all hover:border-brand-500/30 hover:bg-zinc-900"
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <h3 className="font-semibold text-zinc-100 truncate">{project.name}</h3>
          {user && project.owner_id !== user.id && (
            <span className="inline-flex flex-shrink-0 items-center rounded-md bg-brand-950 px-1.5 py-0.5 text-xs font-medium text-brand-400 ring-1 ring-inset ring-brand-800">
              Contributor
            </span>
          )}
        </div>
        {project.repo?.repo_full_name && (
          <span className="ml-2 flex-shrink-0">
            <svg className="h-4 w-4 text-zinc-600 group-hover:text-zinc-400 transition-colors" viewBox="0 0 16 16" fill="currentColor">
              <path d="M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z" />
            </svg>
          </span>
        )}
      </div>
      {project.repo?.repo_full_name ? (
        <p className="mt-1 truncate text-xs text-zinc-500">
          {project.repo.repo_full_name}
        </p>
      ) : project.repo_url ? (
        <p className="mt-1 truncate text-xs text-zinc-500">{project.repo_url}</p>
      ) : null}
      <div className="mt-2 flex items-center gap-2">
        {project.framework && (
          <span className="inline-flex items-center rounded bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-400">
            {project.framework}
          </span>
        )}
        <span className="text-xs text-zinc-600">
          Created {timeAgo(project.created_at)}
        </span>
      </div>
      <div className="mt-4 rounded-lg border border-zinc-800/70 bg-zinc-950/40 p-3">
        {deploysLoading ? (
          <div className="space-y-2">
            <div className="h-3 w-40 animate-pulse rounded bg-zinc-800/70" />
            <div className="h-8 w-full animate-pulse rounded bg-zinc-800/50" />
          </div>
        ) : deploys.length === 0 ? (
          <div className="flex items-center justify-between text-xs text-zinc-500">
            <span>No deploys yet</span>
            <span className="rounded-full border border-zinc-800 px-2 py-0.5 text-[10px] uppercase tracking-wide">
              New
            </span>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs text-zinc-400">
                <span
                  className={
                    "h-2 w-2 rounded-full " +
                    statusTone.dot +
                    (statusTone.pulse ? " animate-pulse" : "")
                  }
                />
                <span className="text-zinc-200">{statusTone.label}</span>
                <span className="text-zinc-600">-</span>
                <span>deployed {timeAgo(latestDeploy.created_at)}</span>
              </div>
              <span className="text-[10px] font-medium uppercase tracking-[0.2em] text-zinc-600">
                7d
              </span>
            </div>
            <div className="flex items-end gap-1" style={{ height: "32px" }}>
              {activity.map((item) => (
                <div
                  key={item.date}
                  className="flex-1 rounded-sm bg-zinc-800/70"
                  style={{
                    height:
                      item.count > 0
                        ? `${Math.max((item.count / maxActivity) * 100, 20)}%`
                        : "2px",
                    backgroundColor:
                      item.count > 0 ? "rgba(0, 214, 143, 0.55)" : undefined,
                  }}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </Link>
  );
}

function getStatusTone(status?: DeployStatus) {
  switch (status) {
    case "active":
    case "healthy":
      return {
        dot: "bg-brand-500 shadow-[0_0_10px_rgba(0,214,143,0.6)]",
        label: "Healthy",
        pulse: true,
      };
    case "queued":
    case "building":
    case "provisioning":
      return {
        dot: "bg-amber-400/80 shadow-[0_0_10px_rgba(251,191,36,0.5)]",
        label: "Deploying",
        pulse: true,
      };
    case "failed":
      return {
        dot: "bg-red-500/80 shadow-[0_0_10px_rgba(239,68,68,0.5)]",
        label: "Failed",
        pulse: false,
      };
    case "stopped":
    case "rolled_back":
      return {
        dot: "bg-zinc-500/70",
        label: "Inactive",
        pulse: false,
      };
    case "superseded":
      return {
        dot: "bg-green-400/80 shadow-[0_0_10px_rgba(74,222,128,0.5)]",
        label: "Active",
        pulse: false,
      };
    case "artifact_ready":
      return {
        dot: "bg-blue-400/80 shadow-[0_0_10px_rgba(96,165,250,0.5)]",
        label: "Ready",
        pulse: false,
      };
    default:
      return {
        dot: "bg-zinc-500/70",
        label: "Inactive",
        pulse: false,
      };
  }
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
    <div className="mb-6 rounded-xl border border-amber-900/50 bg-amber-950/20 p-6">
      <div className="flex items-start gap-4">
        <div className="flex-shrink-0">
          <svg className="h-8 w-8 text-zinc-300" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z" />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-zinc-200">
            Connect your GitHub account
          </h3>
          <p className="mt-1 text-sm text-zinc-400">
            To import a repository, you need to connect your GitHub account first.
            This allows TBD to access your repositories and set up automatic deployments.
          </p>
          <div className="mt-4 flex gap-2">
            <button
              onClick={handleConnect}
              disabled={loading}
              className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-black hover:bg-brand-400 disabled:opacity-50 transition-colors"
            >
              {loading ? "Redirecting..." : "Connect GitHub"}
            </button>
            <button
              onClick={onCancel}
              className="rounded-lg border border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800 transition-colors"
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
    <div className="mb-6 rounded-xl border border-zinc-800 bg-zinc-900/80 p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-zinc-200">
            Import Git Repository
          </h2>
          {user?.github_username && (
            <p className="text-xs text-zinc-500">
              Showing repositories for{" "}
              <span className="font-medium text-zinc-400">{user.github_username}</span>
            </p>
          )}
        </div>
        <button
          onClick={onCancel}
          className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          Cancel
        </button>
      </div>

      {error && <p className="mb-2 text-xs text-red-400">{error}</p>}

      {loading ? (
        <div className="flex items-center gap-2 py-8 text-sm text-zinc-500">
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
            aria-label="Search repositories"
            className="mb-3 block w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
          />
          <div className="max-h-80 space-y-1 overflow-y-auto">
            {filtered.length === 0 ? (
              <p className="py-6 text-center text-sm text-zinc-500">
                {repos.length === 0
                  ? "No repositories found."
                  : "No matching repositories."}
              </p>
            ) : (
              filtered.map((repo) => (
                <div
                  key={repo.id}
                  className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-800/40 px-3 py-2.5"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-zinc-200">
                        {repo.full_name}
                      </p>
                      {repo.private && (
                        <span className="rounded bg-amber-950/50 px-1.5 py-0.5 text-xs text-amber-400">
                          private
                        </span>
                      )}
                    </div>
                    {repo.description && (
                      <p className="truncate text-xs text-zinc-500">
                        {repo.description}
                      </p>
                    )}
                  </div>
                  <div className="ml-3 flex-shrink-0">
                    <button
                      onClick={() => handleImport(repo)}
                      disabled={importing !== null}
                      className="rounded-lg bg-brand-500 px-3 py-1.5 text-xs font-medium text-black hover:bg-brand-400 disabled:opacity-50 transition-colors"
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
