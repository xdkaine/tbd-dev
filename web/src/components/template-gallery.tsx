"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { Modal } from "@/components/modal";
import type { Template } from "@/lib/types";

/* ------------------------------------------------------------------ */
/*  Framework icon/color mapping                                       */
/* ------------------------------------------------------------------ */

const FRAMEWORK_META: Record<
  string,
  { label: string; color: string; bg: string }
> = {
  nextjs: {
    label: "Next.js",
    color: "text-white",
    bg: "bg-black ring-1 ring-zinc-700",
  },
  "react-vite": {
    label: "React",
    color: "text-cyan-400",
    bg: "bg-cyan-950/40",
  },
  python: {
    label: "Python",
    color: "text-yellow-400",
    bg: "bg-yellow-950/40",
  },
  nodejs: {
    label: "Node.js",
    color: "text-green-400",
    bg: "bg-green-950/40",
  },
  go: {
    label: "Go",
    color: "text-sky-400",
    bg: "bg-sky-950/40",
  },
  static: {
    label: "Static",
    color: "text-orange-400",
    bg: "bg-orange-950/40",
  },
};

function FrameworkBadge({ framework }: { framework: string }) {
  const meta = FRAMEWORK_META[framework] ?? {
    label: framework,
    color: "text-zinc-400",
    bg: "bg-zinc-800",
  };
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${meta.color} ${meta.bg}`}
    >
      {meta.label}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/*  Framework SVG icons                                                */
/* ------------------------------------------------------------------ */

function FrameworkIcon({ framework }: { framework: string }) {
  const size = "h-8 w-8";

  switch (framework) {
    case "nextjs":
      return (
        <svg className={size} viewBox="0 0 24 24" fill="currentColor">
          <path d="M11.572 0c-.176 0-.31.001-.358.007a19.76 19.76 0 0 1-.364.033C7.443.346 4.25 2.185 2.228 5.012a11.875 11.875 0 0 0-2.119 5.243c-.096.659-.108.854-.108 1.747s.012 1.089.108 1.748c.652 4.506 3.86 8.292 8.209 9.695.779.25 1.6.422 2.534.525.363.04 1.935.04 2.299 0 1.611-.178 2.977-.577 4.323-1.264.207-.106.247-.134.219-.158-.02-.013-.9-1.193-1.955-2.62l-1.919-2.592-2.404-3.558a338.739 338.739 0 0 0-2.422-3.556c-.009-.002-.018 1.579-.023 3.51-.007 3.38-.01 3.515-.052 3.595a.426.426 0 0 1-.206.214c-.075.037-.14.044-.495.044H7.81l-.108-.068a.438.438 0 0 1-.157-.171l-.049-.106.006-4.703.007-4.705.073-.091a.637.637 0 0 1 .174-.143c.096-.047.134-.051.534-.051.469 0 .534.012.674.096a.923.923 0 0 1 .145.151c.04.056 1.337 1.999 2.882 4.318l4.2 6.317 1.885 2.836.095-.063a12.317 12.317 0 0 0 3.624-3.504 11.874 11.874 0 0 0 2.119-5.243c.096-.659.108-.854.108-1.748 0-.893-.012-1.088-.108-1.747-.652-4.506-3.86-8.292-8.209-9.695a12.597 12.597 0 0 0-2.498-.523A21.228 21.228 0 0 0 11.572 0zm4.069 7.217c.347 0 .408.005.486.047a.473.473 0 0 1 .237.277c.018.06.023 1.365.018 4.304l-.006 4.218-.744-1.14-.746-1.14v-3.066c0-1.982.009-3.097.023-3.15a.478.478 0 0 1 .233-.296c.096-.05.13-.054.5-.054z" />
        </svg>
      );
    case "react-vite":
      return (
        <svg className={size} viewBox="0 0 24 24" fill="currentColor">
          <path d="M14.23 12.004a2.236 2.236 0 0 1-2.235 2.236 2.236 2.236 0 0 1-2.236-2.236 2.236 2.236 0 0 1 2.235-2.236 2.236 2.236 0 0 1 2.236 2.236zm2.648-10.69c-1.346 0-3.107.96-4.888 2.622-1.78-1.653-3.542-2.602-4.887-2.602-.31 0-.592.062-.838.182C4.99 2.17 4.57 3.632 4.818 5.79c.063.546.163 1.112.298 1.693C2.54 8.472 1 9.85 1 11.318c0 1.466 1.54 2.844 4.115 3.834-.135.58-.235 1.147-.297 1.692-.248 2.161.172 3.622 1.447 4.276.246.12.528.182.837.182 1.346 0 3.108-.96 4.888-2.624 1.78 1.655 3.542 2.604 4.887 2.604.31 0 .592-.062.838-.182 1.275-.654 1.695-2.115 1.447-4.276a16.24 16.24 0 0 0-.298-1.693C21.46 14.163 23 12.785 23 11.318c0-1.466-1.54-2.844-4.115-3.834.135-.581.235-1.148.298-1.693.248-2.16-.172-3.621-1.447-4.276a1.748 1.748 0 0 0-.838-.201zm-.133 1.12c.185 0 .34.033.467.098.805.414 1.108 1.586.903 3.373a15.35 15.35 0 0 1-.272 1.535 23.456 23.456 0 0 0-3.05-.578 23.64 23.64 0 0 0-1.95-2.34c1.577-1.468 3.068-2.088 3.902-2.088zm-9.477.02c.83 0 2.317.615 3.89 2.068a23.36 23.36 0 0 0-1.943 2.34 23.133 23.133 0 0 0-3.052.578 15.13 15.13 0 0 1-.27-1.535c-.206-1.79.097-2.963.9-3.375a.93.93 0 0 1 .475-.076zM12 5.434c.457.49.895 1.01 1.31 1.56a22.4 22.4 0 0 0-2.62 0A20.04 20.04 0 0 1 12 5.434zm-5.992 4.26a21.22 21.22 0 0 1 1.527-.81c.26.609.554 1.23.884 1.855a22.93 22.93 0 0 1-.873 1.876c-.538-.2-1.05-.42-1.538-.66zm1.987 8.89c-.826 0-2.317-.613-3.89-2.065.607-.534 1.253-1.03 1.943-2.34a23.5 23.5 0 0 0 3.052-.578c.085.518.19 1.032.27 1.535.207 1.79-.096 2.963-.899 3.375a.93.93 0 0 1-.476.073zM12 18.567c-.457-.49-.895-1.01-1.31-1.56.868.05 1.752.05 2.62 0a20.7 20.7 0 0 1-1.31 1.56zm5.992-4.26a21.22 21.22 0 0 1-1.527.81 22.216 22.216 0 0 1-.884-1.855c.33-.617.64-1.244.873-1.876.538.2 1.05.42 1.538.66zm-3.99.87c-.374.7-.773 1.37-1.194 2.003a21.9 21.9 0 0 1-2.616 0 21.413 21.413 0 0 1-1.194-2.003 22.174 22.174 0 0 1-1.175-2.177c.365-.72.754-1.424 1.175-2.098A21.91 21.91 0 0 1 12 8.899c.453.66.883 1.339 1.283 2.003.42.674.81 1.378 1.175 2.098a21.71 21.71 0 0 1-1.175 2.177zM20.59 8.998c1.897.731 3.09 1.71 3.09 2.32 0 .608-1.193 1.589-3.09 2.319-.378.146-.78.278-1.2.398a23.68 23.68 0 0 0-1.112-2.717 23.52 23.52 0 0 0 1.113-2.718c.42.12.82.252 1.2.398zM3.41 8.998c.38-.146.78-.278 1.2-.398a23.56 23.56 0 0 0 1.113 2.718 23.52 23.52 0 0 0-1.112 2.717c-.42-.12-.822-.252-1.2-.398C1.514 12.906.32 11.927.32 11.318c0-.61 1.193-1.589 3.09-2.32zm13.326 10.63c.185 0 .34-.032.467-.097.805-.413 1.108-1.586.903-3.374a15.35 15.35 0 0 0-.272-1.536c.983-.256 1.927-.548 2.81-.883.127.39.24.78.342 1.171a8.87 8.87 0 0 1 .1 1.248c0 1.25-.43 2.118-1.183 2.505a.928.928 0 0 1-.476.073c-.83 0-2.317-.614-3.89-2.066.607-.534 1.253-1.03 1.943-2.34-.366-.08-.74-.17-1.124-.266z" />
        </svg>
      );
    case "python":
      return (
        <svg className={size} viewBox="0 0 24 24" fill="currentColor">
          <path d="M14.25.18l.9.2.73.26.59.3.45.32.34.34.25.34.16.33.1.3.04.26.02.2-.01.13V8.5l-.05.63-.13.55-.21.46-.26.38-.3.31-.33.25-.35.19-.35.14-.33.1-.3.07-.26.04-.21.02H8.77l-.69.05-.59.14-.5.22-.41.27-.33.32-.27.35-.2.36-.15.37-.1.35-.07.32-.04.27-.02.21v3.06H3.17l-.21-.03-.28-.07-.32-.12-.35-.18-.36-.26-.36-.36-.35-.46-.32-.59-.28-.73-.21-.88-.14-1.05-.05-1.23.06-1.22.16-1.04.24-.87.32-.71.36-.57.4-.44.42-.33.42-.24.4-.16.36-.1.32-.05.24-.01h.16l.06.01h8.16v-.83H6.18l-.01-2.75-.02-.37.05-.34.11-.31.17-.28.25-.26.31-.23.38-.2.44-.18.51-.15.58-.12.64-.1.71-.06.77-.04.84-.02 1.27.05zm-6.3 1.98l-.23.33-.08.41.08.41.23.34.33.22.41.09.41-.09.33-.22.23-.34.08-.41-.08-.41-.23-.33-.33-.22-.41-.09-.41.09-.33.22zM21.1 6.11l.28.06.32.12.35.18.36.27.36.35.35.47.32.59.28.73.21.88.14 1.04.05 1.23-.06 1.23-.16 1.04-.24.86-.32.71-.36.57-.4.45-.42.33-.42.24-.4.16-.36.09-.32.05-.24.02-.16-.01h-8.22v.82h5.84l.01 2.76.02.36-.05.34-.11.31-.17.29-.25.25-.31.24-.38.2-.44.17-.51.15-.58.13-.64.09-.71.07-.77.04-.84.01-1.27-.04-1.07-.14-.9-.2-.73-.25-.59-.3-.45-.33-.34-.34-.25-.34-.16-.33-.1-.3-.04-.25-.02-.2.01-.13v-5.34l.05-.64.13-.54.21-.46.26-.38.3-.32.33-.24.35-.2.35-.14.33-.1.3-.06.26-.04.21-.02.13-.01h5.84l.69-.05.59-.14.5-.21.41-.28.33-.32.27-.35.2-.36.15-.36.1-.35.07-.32.04-.28.02-.21V6.07h2.09l.14.01.21.03zm-6.47 14.25l-.23.33-.08.41.08.41.23.33.33.23.41.08.41-.08.33-.23.23-.33.08-.41-.08-.41-.23-.33-.33-.23-.41-.08-.41.08-.33.23z" />
        </svg>
      );
    case "nodejs":
      return (
        <svg className={size} viewBox="0 0 24 24" fill="currentColor">
          <path d="M11.998,24c-0.321,0-0.641-0.084-0.922-0.247l-2.936-1.737c-0.438-0.245-0.224-0.332-0.08-0.383 c0.585-0.203,0.703-0.25,1.328-0.604c0.065-0.037,0.151-0.023,0.218,0.017l2.256,1.339c0.082,0.045,0.197,0.045,0.272,0 l8.795-5.076c0.082-0.047,0.134-0.141,0.134-0.238V6.921c0-0.099-0.053-0.192-0.137-0.242l-8.791-5.072 c-0.081-0.047-0.189-0.047-0.271,0L3.075,6.68C2.99,6.729,2.936,6.825,2.936,6.921v10.15c0,0.097,0.054,0.189,0.136,0.235 l2.409,1.392c1.307,0.654,2.108-0.116,2.108-0.89V7.787c0-0.142,0.114-0.253,0.256-0.253h1.115c0.139,0,0.255,0.112,0.255,0.253 v10.021c0,1.745-0.95,2.745-2.604,2.745c-0.508,0-0.909,0-2.026-0.551L2.28,18.675c-0.57-0.329-0.922-0.945-0.922-1.604V6.921 c0-0.659,0.353-1.275,0.922-1.603l8.795-5.082c0.557-0.315,1.296-0.315,1.848,0l8.794,5.082c0.57,0.329,0.924,0.944,0.924,1.603 v10.15c0,0.659-0.354,1.273-0.924,1.604l-8.794,5.078C12.643,23.916,12.324,24,11.998,24z M19.099,13.993 c0-1.9-1.284-2.406-3.987-2.763c-2.731-0.361-3.009-0.548-3.009-1.187c0-0.528,0.235-1.233,2.258-1.233 c1.807,0,2.473,0.389,2.747,1.607c0.024,0.115,0.129,0.199,0.247,0.199h1.141c0.071,0,0.138-0.031,0.186-0.081 c0.048-0.054,0.074-0.123,0.067-0.196c-0.177-2.098-1.571-3.076-4.388-3.076c-2.508,0-4.004,1.058-4.004,2.833 c0,1.925,1.488,2.457,3.895,2.695c2.88,0.282,3.103,0.703,3.103,1.269c0,0.983-0.789,1.402-2.642,1.402 c-2.327,0-2.839-0.584-3.011-1.742c-0.02-0.124-0.126-0.215-0.253-0.215h-1.137c-0.141,0-0.254,0.112-0.254,0.253 c0,1.482,0.806,3.248,4.655,3.248C17.501,17.007,19.099,15.91,19.099,13.993z" />
        </svg>
      );
    case "go":
      return (
        <svg className={size} viewBox="0 0 24 24" fill="currentColor">
          <path d="M1.811 10.231c-.047 0-.058-.023-.035-.059l.246-.315c.023-.035.081-.058.128-.058h4.172c.046 0 .058.035.035.07l-.199.303c-.023.036-.082.07-.117.07zM.047 11.306c-.047 0-.059-.023-.035-.058l.245-.316c.023-.035.082-.058.129-.058h5.328c.047 0 .07.035.058.07l-.093.28c-.012.047-.058.07-.105.07zm2.828 1.075c-.047 0-.059-.035-.035-.07l.163-.292c.023-.035.07-.07.117-.07h2.337c.047 0 .07.035.07.082l-.023.28c0 .047-.047.082-.082.082zm12.129-2.36c-.736.187-1.239.327-1.963.514-.176.046-.187.058-.34-.117-.174-.199-.303-.327-.548-.444-.737-.362-1.45-.257-2.115.175-.795.514-1.204 1.274-1.192 2.22.011.935.654 1.706 1.577 1.835.795.105 1.46-.175 1.987-.771.105-.13.198-.27.315-.434H10.47c-.245 0-.304-.152-.222-.35.152-.362.432-.97.596-1.274a.315.315 0 0 1 .292-.187h4.253c-.023.316-.023.631-.07.947a4.983 4.983 0 0 1-.958 2.29c-.841 1.11-1.94 1.8-3.33 1.986-1.145.152-2.209-.07-3.143-.77-.865-.655-1.356-1.52-1.484-2.595-.152-1.274.222-2.419.993-3.424.83-1.086 1.928-1.776 3.272-2.02 1.098-.2 2.15-.06 3.096.642.538.398.958.924 1.227 1.554a.226.226 0 0 1-.035.234zm5.834 4.404c-.035 1.036-.675 1.94-1.59 2.384-.992.467-2.032.514-3.06.035-1.098-.514-1.718-1.403-1.812-2.616-.117-1.532.456-2.701 1.647-3.575.992-.725 2.22-.933 3.33-.35 1.25.643 1.649 1.845 1.543 3.237-.012.305-.047.28-.058.885zm-1.996-.691c-.012-.176-.023-.316-.058-.456-.234-1.075-1.227-1.554-2.163-1.05-.585.316-.876.852-.935 1.508-.082.97.397 1.776 1.286 2.01.724.187 1.484-.058 1.706-.854.093-.305.105-.643.164-1.158z" />
        </svg>
      );
    default:
      return (
        <svg
          className={size}
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M17.25 6.75 22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3-4.5 16.5"
          />
        </svg>
      );
  }
}

/* ------------------------------------------------------------------ */
/*  Template Gallery                                                   */
/* ------------------------------------------------------------------ */

interface TemplateGalleryProps {
  onDeployed: (projectId: string) => void;
  onCancel: () => void;
}

export function TemplateGallery({ onDeployed, onCancel }: TemplateGalleryProps) {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Template | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.templates.list();
        setTemplates(res.items);
      } catch (err) {
        if (err instanceof ApiError) setError(err.detail);
        else setError("Failed to load templates");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div className="mb-6 rounded-xl border border-zinc-800 bg-zinc-900/80 p-4">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-zinc-200">
            Start from a Template
          </h2>
          <p className="text-xs text-zinc-500">
            Pick a starter project. We&apos;ll create a GitHub repo and deploy
            it for you.
          </p>
        </div>
        <button
          onClick={onCancel}
          className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          Cancel
        </button>
      </div>

      {error && <p className="mb-3 text-xs text-red-400">{error}</p>}

      {loading ? (
        <div className="flex items-center gap-2 py-8 text-sm text-zinc-500">
          <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
          Loading templates...
        </div>
      ) : templates.length === 0 ? (
        <p className="py-6 text-center text-sm text-zinc-500">
          No templates available yet.
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {templates.map((t) => (
            <button
              key={t.id}
              onClick={() => setSelected(t)}
              className="group rounded-lg border border-zinc-800 bg-zinc-800/30 p-4 text-left transition-all hover:border-brand-500/40 hover:bg-zinc-800/60"
            >
              <div className="mb-3 flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-zinc-800 text-zinc-300 group-hover:text-brand-400 transition-colors">
                  <FrameworkIcon framework={t.framework} />
                </div>
                <div className="min-w-0 flex-1">
                  <h3 className="text-sm font-semibold text-zinc-200 truncate">
                    {t.name}
                  </h3>
                  <FrameworkBadge framework={t.framework} />
                </div>
              </div>
              <p className="text-xs text-zinc-500 line-clamp-2">
                {t.description}
              </p>
              {t.tags.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {t.tags.slice(0, 3).map((tag) => (
                    <span
                      key={tag}
                      className="rounded bg-zinc-800/80 px-1.5 py-0.5 text-[10px] text-zinc-500"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Deploy modal */}
      {selected && (
        <DeployTemplateModal
          template={selected}
          onClose={() => setSelected(null)}
          onDeployed={onDeployed}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Deploy modal                                                       */
/* ------------------------------------------------------------------ */

function DeployTemplateModal({
  template,
  onClose,
  onDeployed,
}: {
  template: Template;
  onClose: () => void;
  onDeployed: (projectId: string) => void;
}) {
  const router = useRouter();
  const [repoName, setRepoName] = useState(template.github_repo);
  const [description, setDescription] = useState("");
  const [isPrivate, setIsPrivate] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [error, setError] = useState("");

  async function handleDeploy() {
    if (!repoName.trim()) return;
    setDeploying(true);
    setError("");

    try {
      const result = await api.templates.deploy(template.slug, {
        repo_name: repoName.trim(),
        description,
        private: isPrivate,
      });
      onClose();
      router.push(`/dashboard/${result.project_id}`);
      onDeployed(result.project_id);
    } catch (err) {
      if (err instanceof ApiError) setError(err.detail);
      else setError("Failed to deploy template");
    } finally {
      setDeploying(false);
    }
  }

  return (
    <Modal open onClose={onClose}>
      <div className="p-6">
        <div className="mb-4 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-zinc-800 text-zinc-300">
            <FrameworkIcon framework={template.framework} />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-zinc-100">
              Deploy {template.name}
            </h3>
            <p className="text-xs text-zinc-500">
              Creates a new GitHub repo and deploys it
            </p>
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-md bg-red-950/30 border border-red-900/50 p-3">
            <p className="text-xs text-red-400">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          {/* Repo name */}
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">
              Repository Name
            </label>
            <input
              type="text"
              value={repoName}
              onChange={(e) => setRepoName(e.target.value)}
              placeholder="my-awesome-app"
              autoFocus
              className="block w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
            />
            <p className="mt-1 text-[10px] text-zinc-600">
              This will be the name of the new repo in your GitHub account
            </p>
          </div>

          {/* Description */}
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">
              Description
              <span className="text-zinc-600 font-normal"> (optional)</span>
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="A brief description of your project"
              className="block w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
            />
          </div>

          {/* Private toggle */}
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={isPrivate}
              onChange={(e) => setIsPrivate(e.target.checked)}
              className="h-4 w-4 rounded border-zinc-700 bg-zinc-900 text-brand-500 focus:ring-brand-500/50 focus:ring-offset-0"
            />
            <span className="text-xs text-zinc-400">Private repository</span>
          </label>
        </div>

        {/* Actions */}
        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onClose}
            disabled={deploying}
            className="rounded-md border border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800/50 disabled:opacity-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleDeploy}
            disabled={deploying || !repoName.trim()}
            className="rounded-md bg-brand-500 px-4 py-2 text-sm font-medium text-black hover:bg-brand-400 disabled:opacity-50 transition-colors"
          >
            {deploying ? (
              <span className="flex items-center gap-2">
                <svg
                  className="h-4 w-4 animate-spin"
                  viewBox="0 0 24 24"
                  fill="none"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
                Creating...
              </span>
            ) : (
              "Deploy"
            )}
          </button>
        </div>
      </div>
    </Modal>
  );
}
