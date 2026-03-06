"use client";

import { useEffect, useState, useRef, useCallback, KeyboardEvent } from "react";
import Link from "next/link";

/* ═══════════════════════════════════════════════════════════════
   Simulated Filesystem
   ═══════════════════════════════════════════════════════════════ */

type FSNode = { type: "file"; content: string } | { type: "dir"; children: Record<string, FSNode> };

const FILE_SYSTEM: Record<string, FSNode> = {
  "~": {
    type: "dir",
    children: {
      projects: {
        type: "dir",
        children: {
          portfolio: {
            type: "dir",
            children: {
              "index.html": {
                type: "file",
                content: `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>My Portfolio</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <div id="app"></div>
  <script src="src/app.js"></script>
</body>
</html>`,
              },
              "style.css": {
                type: "file",
                content: `* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: system-ui, sans-serif; background: #0a0a0a; color: #fafafa; }
#app { max-width: 960px; margin: 0 auto; padding: 2rem; }
h1 { font-size: 2.5rem; margin-bottom: 1rem; }
.projects { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.5rem; }`,
              },
              "package.json": {
                type: "file",
                content: `{
  "name": "portfolio",
  "version": "1.0.0",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "vite": "^5.0.0"
  }
}`,
              },
              "README.md": {
                type: "file",
                content: `# Portfolio

My personal portfolio site, deployed with tbd.

## Quick Start
\`\`\`
npm install
npm run dev
\`\`\`

## Deploy
Push to \`main\` — tbd handles the rest.
Live at https://portfolio.dev.sdc.cpp`,
              },
              src: {
                type: "dir",
                children: {
                  "app.js": {
                    type: "file",
                    content: `import { initRouter } from './utils.js';

const app = document.getElementById('app');
app.innerHTML = '<h1>Welcome</h1><p>Portfolio coming soon.</p>';
initRouter();`,
                  },
                  "utils.js": {
                    type: "file",
                    content: `export function initRouter() {
  window.addEventListener('popstate', () => {
    console.log('route changed:', location.pathname);
  });
}

export function formatDate(d) {
  return new Intl.DateTimeFormat('en-US').format(new Date(d));
}`,
                  },
                },
              },
              public: {
                type: "dir",
                children: {
                  "favicon.ico": { type: "file", content: "[binary file]" },
                  "logo.png": { type: "file", content: "[binary file]" },
                },
              },
            },
          },
        },
      },
    },
  },
};

function resolvePath(cwd: string, target: string): string | null {
  let parts: string[];
  if (target === "~" || target === "") {
    return "~";
  }
  if (target.startsWith("~/")) {
    parts = ["~", ...target.slice(2).split("/").filter(Boolean)];
  } else if (target.startsWith("/")) {
    parts = ["~", ...target.slice(1).split("/").filter(Boolean)];
  } else {
    parts = [...cwd.split("/").filter(Boolean), ...target.split("/").filter(Boolean)];
  }

  const resolved: string[] = [];
  for (const p of parts) {
    if (p === ".") continue;
    if (p === "..") {
      if (resolved.length > 1) resolved.pop();
      continue;
    }
    resolved.push(p);
  }
  return resolved.join("/") || "~";
}

function getNode(path: string): FSNode | null {
  const parts = path.split("/").filter(Boolean);
  let node: FSNode | null = FILE_SYSTEM["~"];
  if (!node) return null;
  for (let i = 1; i < parts.length; i++) {
    if (!node || node.type !== "dir") return null;
    node = node.children[parts[i]] ?? null;
  }
  return node;
}

/* ═══════════════════════════════════════════════════════════════
   Command Executor
   ═══════════════════════════════════════════════════════════════ */

function executeCommand(
  input: string,
  cwd: string
): { output: string[]; newCwd: string } {
  const trimmed = input.trim();
  if (!trimmed) return { output: [], newCwd: cwd };

  const parts = trimmed.split(/\s+/);
  const cmd = parts[0];
  const args = parts.slice(1);

  switch (cmd) {
    case "help": {
      return {
        output: [
          "Available commands:",
          "  ls [dir]        List directory contents",
          "  cd <dir>        Change directory",
          "  pwd             Print working directory",
          "  cat <file>      Show file contents",
          "  clear           Clear terminal",
          "  echo <text>     Print text",
          "  whoami          Display current user",
          "  date            Display current date",
          "  tree            Show directory tree",
          "  help            Show this help message",
        ],
        newCwd: cwd,
      };
    }

    case "ls": {
      const target = args[0] ? resolvePath(cwd, args[0]) : cwd;
      if (!target) return { output: [`ls: cannot access '${args[0]}': No such file or directory`], newCwd: cwd };
      const node = getNode(target);
      if (!node) return { output: [`ls: cannot access '${args[0]}': No such file or directory`], newCwd: cwd };
      if (node.type === "file") return { output: [args[0] || cwd.split("/").pop() || ""], newCwd: cwd };
      const entries = Object.entries(node.children)
        .map(([name, n]) => (n.type === "dir" ? `${name}/` : name))
        .sort((a, b) => {
          const aDir = a.endsWith("/");
          const bDir = b.endsWith("/");
          if (aDir && !bDir) return -1;
          if (!aDir && bDir) return 1;
          return a.localeCompare(b);
        });
      return { output: [entries.join("  ")], newCwd: cwd };
    }

    case "cd": {
      if (!args[0] || args[0] === "~") return { output: [], newCwd: "~" };
      const target = resolvePath(cwd, args[0]);
      if (!target) return { output: [`cd: no such file or directory: ${args[0]}`], newCwd: cwd };
      const node = getNode(target);
      if (!node) return { output: [`cd: no such file or directory: ${args[0]}`], newCwd: cwd };
      if (node.type !== "dir") return { output: [`cd: not a directory: ${args[0]}`], newCwd: cwd };
      return { output: [], newCwd: target };
    }

    case "pwd": {
      return { output: [cwd.replace("~", "/home/developer")], newCwd: cwd };
    }

    case "cat": {
      if (!args[0]) return { output: ["cat: missing file operand"], newCwd: cwd };
      const target = resolvePath(cwd, args[0]);
      if (!target) return { output: [`cat: ${args[0]}: No such file or directory`], newCwd: cwd };
      const node = getNode(target);
      if (!node) return { output: [`cat: ${args[0]}: No such file or directory`], newCwd: cwd };
      if (node.type === "dir") return { output: [`cat: ${args[0]}: Is a directory`], newCwd: cwd };
      return { output: node.content.split("\n"), newCwd: cwd };
    }

    case "echo": {
      return { output: [args.join(" ")], newCwd: cwd };
    }

    case "whoami": {
      return { output: ["developer"], newCwd: cwd };
    }

    case "date": {
      return { output: [new Date().toString()], newCwd: cwd };
    }

    case "tree": {
      const target = args[0] ? resolvePath(cwd, args[0]) : cwd;
      if (!target) return { output: [`tree: '${args[0]}': No such file or directory`], newCwd: cwd };
      const node = getNode(target);
      if (!node) return { output: [`tree: '${args[0]}': No such file or directory`], newCwd: cwd };
      if (node.type === "file") return { output: [args[0] || "."], newCwd: cwd };
      const lines: string[] = ["."];
      const walk = (n: FSNode, prefix: string) => {
        if (n.type !== "dir") return;
        const entries = Object.entries(n.children).sort((a, b) => {
          const aDir = a[1].type === "dir";
          const bDir = b[1].type === "dir";
          if (aDir && !bDir) return -1;
          if (!aDir && bDir) return 1;
          return a[0].localeCompare(b[0]);
        });
        entries.forEach(([name, child], i) => {
          const isLast = i === entries.length - 1;
          const connector = isLast ? "└── " : "├── ";
          const display = child.type === "dir" ? `${name}/` : name;
          lines.push(`${prefix}${connector}${display}`);
          if (child.type === "dir") {
            walk(child, prefix + (isLast ? "    " : "│   "));
          }
        });
      }
      walk(node, "");
      return { output: lines, newCwd: cwd };
    }

    case "mkdir":
      return { output: [`mkdir: permission denied`], newCwd: cwd };
    case "touch":
      return { output: [`touch: permission denied`], newCwd: cwd };
    case "rm":
      return { output: [`rm: permission denied`], newCwd: cwd };
    case "mv":
      return { output: [`mv: permission denied`], newCwd: cwd };
    case "cp":
      return { output: [`cp: permission denied`], newCwd: cwd };
    case "vim":
    case "nano":
    case "vi":
      return { output: [`${cmd}: this is a demo terminal — try cat instead`], newCwd: cwd };
    case "git":
      return { output: [`On branch main`, `Your branch is up to date with 'origin/main'.`, `nothing to commit, working tree clean`], newCwd: cwd };
    case "npm":
      if (args[0] === "run" && args[1] === "dev") {
        return { output: ["VITE v5.0.0  ready in 124ms", "", "  ➜  Local:   http://localhost:5173/", "  ➜  Network: http://192.168.1.42:5173/"], newCwd: cwd };
      }
      if (args[0] === "install") {
        return { output: ["added 42 packages in 2.1s"], newCwd: cwd };
      }
      return { output: [`npm: try 'npm install' or 'npm run dev'`], newCwd: cwd };
    case "node":
      return { output: [`node: this is a demo terminal`], newCwd: cwd };
    case "python":
    case "python3":
      return { output: [`Python 3.12.0 (demo)`, `>>> this is a demo terminal`], newCwd: cwd };
    case "curl":
      return { output: [`curl: this is a demo terminal`], newCwd: cwd };
    case "sudo":
      return { output: [`developer is not in the sudoers file. This incident will be reported.`], newCwd: cwd };
    case "exit":
      return { output: ["logout", "Connection to demo closed."], newCwd: cwd };

    default:
      return { output: [`command not found: ${cmd}`], newCwd: cwd };
  }
}

/* ═══════════════════════════════════════════════════════════════
   Demo Animation Lines
   ═══════════════════════════════════════════════════════════════ */

const DEMO_COMMAND = "git push origin main";

type DemoLine = {
  text: string;
  cls: string;
  delay?: number;     // ms before this line appears (after previous)
  gap?: boolean;      // extra margin-top
};

const GIT_OUTPUT: DemoLine[] = [
  { text: "Enumerating objects: 12, done.", cls: "text-zinc-500", delay: 200 },
  { text: "Compressing objects: 100% (8/8), done.", cls: "text-zinc-500", delay: 150 },
  { text: "Writing objects: 100% (12/12), 3.42 KiB, done.", cls: "text-zinc-500", delay: 150 },
  { text: "remote: Resolving deltas: 100% (3/3), done.", cls: "text-zinc-500", delay: 200 },
  { text: "To github.com:user/portfolio.git", cls: "text-zinc-500", delay: 100 },
  { text: "   a1f3c9e..b2d4e6f  main -> main", cls: "text-zinc-400", delay: 100 },
];

const BUILD_OUTPUT: DemoLine[] = [
  { text: "⏵ Webhook received — starting build...", cls: "text-zinc-400", gap: true, delay: 600 },
  { text: "⏵ Cloning repo...                          done", cls: "text-zinc-400", delay: 500 },
  { text: "⏵ Installing dependencies (npm install)...  done  3.2s", cls: "text-zinc-400", delay: 400 },
  { text: "⏵ Building project (npm run build)...       done 12.4s", cls: "text-zinc-400", delay: 500 },
  { text: "✓ Build succeeded", cls: "text-brand-400", delay: 300 },
  { text: "⏵ Provisioning container...                 done  1.8s", cls: "text-zinc-400", delay: 400 },
  { text: "⏵ Health check passed                             0.3s", cls: "text-zinc-400", delay: 300 },
  { text: "✓ Deployed", cls: "text-brand-400", delay: 300 },
];

const ALL_DEMO_LINES: DemoLine[] = [...GIT_OUTPUT, ...BUILD_OUTPUT];

/* ═══════════════════════════════════════════════════════════════
   Terminal Component
   ═══════════════════════════════════════════════════════════════ */

type TermLine = {
  text: string;
  cls?: string;
  gap?: boolean;
  isPrompt?: boolean;
  isLive?: boolean;
};

function TerminalDemo() {
  const [phase, setPhase] = useState<"wait" | "typing" | "output" | "interactive">("wait");
  const [typedChars, setTypedChars] = useState(0);
  const [visibleLines, setVisibleLines] = useState(0);
  const [history, setHistory] = useState<TermLine[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [cwd, setCwd] = useState("~/projects/portfolio");
  const [cmdHistory, setCmdHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, []);

  // Phase: wait -> typing
  useEffect(() => {
    const t = setTimeout(() => setPhase("typing"), 500);
    return () => clearTimeout(t);
  }, []);

  // Phase: typing
  useEffect(() => {
    if (phase !== "typing") return;
    if (typedChars >= DEMO_COMMAND.length) {
      const t = setTimeout(() => setPhase("output"), 350);
      return () => clearTimeout(t);
    }
    const t = setTimeout(
      () => setTypedChars((c) => c + 1),
      40 + Math.random() * 35
    );
    return () => clearTimeout(t);
  }, [phase, typedChars]);

  // Phase: output — reveal lines with individual delays
  useEffect(() => {
    if (phase !== "output") return;
    if (visibleLines >= ALL_DEMO_LINES.length) {
      // Show the live line then transition
      const t = setTimeout(() => setPhase("interactive"), 600);
      return () => clearTimeout(t);
    }
    const delay = ALL_DEMO_LINES[visibleLines]?.delay ?? 300;
    const t = setTimeout(() => {
      setVisibleLines((l) => l + 1);
      scrollToBottom();
    }, delay);
    return () => clearTimeout(t);
  }, [phase, visibleLines, scrollToBottom]);

  // Auto-focus and scroll when interactive
  useEffect(() => {
    if (phase === "interactive") {
      inputRef.current?.focus();
      scrollToBottom();
    }
  }, [phase, scrollToBottom]);

  // Scroll on history change
  useEffect(() => {
    scrollToBottom();
  }, [history, scrollToBottom]);

  const handleCommand = useCallback(
    (input: string) => {
      const trimmed = input.trim();

      if (trimmed === "clear") {
        setHistory([]);
        setInputValue("");
        setCmdHistory((h) => [...h, trimmed]);
        setHistoryIndex(-1);
        return;
      }

      const { output, newCwd } = executeCommand(trimmed, cwd);

      const newLines: TermLine[] = [
        { text: `${shortCwd(cwd)} $ ${trimmed}`, isPrompt: true },
        ...output.map((line) => ({ text: line })),
      ];

      setHistory((h) => [...h, ...newLines]);
      setCwd(newCwd);
      setInputValue("");
      if (trimmed) {
        setCmdHistory((h) => [...h, trimmed]);
      }
      setHistoryIndex(-1);
    },
    [cwd]
  );

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      handleCommand(inputValue);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (cmdHistory.length === 0) return;
      const newIndex = historyIndex === -1 ? cmdHistory.length - 1 : Math.max(0, historyIndex - 1);
      setHistoryIndex(newIndex);
      setInputValue(cmdHistory[newIndex]);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (historyIndex === -1) return;
      const newIndex = historyIndex + 1;
      if (newIndex >= cmdHistory.length) {
        setHistoryIndex(-1);
        setInputValue("");
      } else {
        setHistoryIndex(newIndex);
        setInputValue(cmdHistory[newIndex]);
      }
    } else if (e.key === "l" && e.ctrlKey) {
      e.preventDefault();
      setHistory([]);
    }
  };

  const focusInput = () => {
    if (phase === "interactive") {
      inputRef.current?.focus();
    }
  };

  const promptCwd = shortCwd(cwd);

  return (
    <div className="w-full max-w-2xl mx-auto">
      <div
        className="rounded-xl border border-[var(--landing-border)] bg-[var(--landing-surface)] overflow-hidden shadow-[0_0_80px_-20px_rgba(0,214,143,0.10)]"
        onClick={focusInput}
      >
        {/* ── Title bar with traffic lights ── */}
        <div className="flex items-center px-4 py-3 border-b border-[var(--landing-border)]">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-[#ff5f57]" />
            <div className="w-3 h-3 rounded-full bg-[#febc2e]" />
            <div className="w-3 h-3 rounded-full bg-[#28c840]" />
          </div>
          <div className="flex-1 text-center">
            <span className="text-[12px] text-zinc-500 font-mono">
              ~/projects/portfolio
            </span>
          </div>
          <div className="w-[52px]" /> {/* spacer to balance traffic lights */}
        </div>

        {/* ── Terminal body ── */}
        <div
          ref={scrollRef}
          className="px-5 py-4 font-mono text-[13px] leading-relaxed min-h-[300px] max-h-[420px] overflow-y-auto cursor-text"
        >
          {/* ── Demo: command being typed ── */}
          {phase !== "interactive" && (
            <>
              <div>
                <span className="text-brand-500">{promptCwd} $</span>{" "}
                <span className="text-zinc-200">
                  {DEMO_COMMAND.slice(0, typedChars)}
                </span>
                {(phase === "typing" || phase === "wait") && (
                  <span className="terminal-cursor" />
                )}
              </div>

              {/* Demo output lines */}
              {ALL_DEMO_LINES.slice(0, visibleLines).map((line, i) => (
                <div
                  key={i}
                  className={`terminal-line ${line.cls} ${line.gap ? "mt-3" : ""}`}
                >
                  {"  "}{line.text}
                </div>
              ))}

              {/* Live URL line */}
              {visibleLines >= ALL_DEMO_LINES.length && (
                <div className="terminal-line mt-3">
                  <span className="text-brand-400 live-dot">{"●"}</span>{" "}
                  <span className="text-zinc-200">
                    Live at{" "}
                    <span className="underline decoration-zinc-700 underline-offset-2">
                      https://portfolio.dev.sdc.cpp
                    </span>
                  </span>
                </div>
              )}
            </>
          )}

          {/* ── Interactive history ── */}
          {phase === "interactive" && (
            <>
              {/* Show the demo as finished history */}
              <div>
                <span className="text-brand-500">{promptCwd} $</span>{" "}
                <span className="text-zinc-200">{DEMO_COMMAND}</span>
              </div>
              {ALL_DEMO_LINES.map((line, i) => (
                <div key={`d-${i}`} className={`${line.cls} ${line.gap ? "mt-3" : ""}`}>
                  {"  "}{line.text}
                </div>
              ))}
              <div className="mt-3">
                <span className="text-brand-400 live-dot">{"●"}</span>{" "}
                <span className="text-zinc-200">
                  Live at{" "}
                  <span className="underline decoration-zinc-700 underline-offset-2">
                    https://portfolio.dev.sdc.cpp
                  </span>
                </span>
              </div>

              <div className="mt-3 mb-1 text-zinc-600 text-[11px]">
                {"── interactive terminal ─ type help for commands ──"}
              </div>

              {/* Command history */}
              {history.map((line, i) => (
                <div
                  key={i}
                  className={`${line.isPrompt ? "" : "text-zinc-300"} ${line.gap ? "mt-3" : ""} whitespace-pre-wrap break-all`}
                >
                  {line.isPrompt ? (
                    <>
                      <span className="text-brand-500">
                        {line.text.split(" $ ")[0]} $
                      </span>{" "}
                      <span className="text-zinc-200">
                        {line.text.split(" $ ").slice(1).join(" $ ")}
                      </span>
                    </>
                  ) : (
                    line.text
                  )}
                </div>
              ))}

              {/* Active input line */}
              <div className="flex items-center">
                <span className="text-brand-500 shrink-0">
                  {shortCwd(cwd)} $
                </span>
                <input
                  ref={inputRef}
                  type="text"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                  className="terminal-input"
                  spellCheck={false}
                  autoCapitalize="off"
                  autoCorrect="off"
                  autoComplete="off"
                />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/** Shorten cwd for prompt display */
function shortCwd(cwd: string): string {
  if (cwd === "~") return "~";
  const parts = cwd.split("/");
  if (parts.length <= 2) return cwd;
  return parts.slice(-2).join("/");
}

/* ═══════════════════════════════════════════════════════════════
   Landing Page
   ═══════════════════════════════════════════════════════════════ */

export default function LandingPage() {
  return (
    <div className="landing h-screen flex flex-col overflow-hidden relative">
      {/* Background glow */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 80% 50% at 50% -20%, rgba(0,214,143,0.07), transparent)",
        }}
      />

      {/* ────── Navbar ────── */}
      <nav className="relative z-10 flex items-center justify-between px-6 py-4 max-w-5xl mx-auto w-full">
        <Link
          href="/"
          className="font-mono text-lg font-bold tracking-tight text-brand-500"
        >
          tbd
        </Link>

        <Link
          href="/login"
          className="text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          Sign in
        </Link>
      </nav>

      {/* ────── Centered content ────── */}
      <main className="relative z-10 flex-1 flex flex-col items-center justify-center px-6 -mt-4">
        <h1 className="text-[clamp(1.75rem,4.5vw,3rem)] font-bold tracking-tight leading-[1.2] text-center">
          <span className="text-white">Push to GitHub.</span>
          <br />
          <span className="text-zinc-500">Auto Build.</span>
          <br />
          <span className="text-brand-500">Deployed @ dev.sdc.cpp</span>
        </h1>

        {/* Terminal */}
        <div className="mt-8 sm:mt-10 w-full max-w-2xl">
          <TerminalDemo />
        </div>
      </main>

      {/* ────── Footer ────── */}
      <footer className="relative z-10 px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <span className="text-xs text-zinc-700 font-mono">tbd</span>
          <span className="text-xs text-zinc-700">
            &copy; {new Date().getFullYear()} SDC
          </span>
        </div>
      </footer>
    </div>
  );
}
