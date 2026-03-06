"use client";

import { useEffect, useState, useRef, useCallback, KeyboardEvent } from "react";
import Link from "next/link";

/* ═══════════════════════════════════════════════════════════════
   Simulated Filesystem (in-memory only)
   ═══════════════════════════════════════════════════════════════ */

type FSFile = { type: "file"; content: string; mtime: number; mode: string };
type FSDir = { type: "dir"; children: Record<string, FSNode>; mtime: number; mode: string };
type FSNode = FSFile | FSDir;

const HOME_DIR = "/home/developer";
const DEFAULT_FILE_MODE = "-rw-r--r--";
const DEFAULT_DIR_MODE = "drwxr-xr-x";
const BASE_TIME = Date.UTC(2024, 4, 12, 9, 30, 0);

const makeFile = (content: string, mtime = BASE_TIME): FSFile => ({
  type: "file",
  content,
  mtime,
  mode: DEFAULT_FILE_MODE,
});

const makeDir = (children: Record<string, FSNode>, mtime = BASE_TIME): FSDir => ({
  type: "dir",
  children,
  mtime,
  mode: DEFAULT_DIR_MODE,
});

const INITIAL_FS: FSDir = makeDir({
  projects: makeDir({
    portfolio: makeDir({
      "index.html": makeFile(`<!DOCTYPE html>
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
</html>`),
      "style.css": makeFile(`* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: system-ui, sans-serif; background: #0a0a0a; color: #fafafa; }
#app { max-width: 960px; margin: 0 auto; padding: 2rem; }
h1 { font-size: 2.5rem; margin-bottom: 1rem; }
.projects { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.5rem; }`),
      "package.json": makeFile(`{
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
}`),
      "README.md": makeFile(`# Portfolio

My personal portfolio site, deployed with tbd.

## Quick Start
\`\`\`
npm install
npm run dev
\`\`\`

## Deploy
Push to \`main\` — tbd handles the rest.
Live at https://portfolio.dev.sdc.cpp`),
      src: makeDir({
        "app.js": makeFile(`import { initRouter } from './utils.js';

const app = document.getElementById('app');
app.innerHTML = '<h1>Welcome</h1><p>Portfolio coming soon.</p>';
initRouter();`),
        "utils.js": makeFile(`export function initRouter() {
  window.addEventListener('popstate', () => {
    console.log('route changed:', location.pathname);
  });
}

export function formatDate(d) {
  return new Intl.DateTimeFormat('en-US').format(new Date(d));
}`),
      }),
      public: makeDir({
        "favicon.ico": makeFile("[binary file]"),
        "logo.png": makeFile("[binary file]"),
      }),
    }),
    api: makeDir({
      "README.md": makeFile(`# API Service

Small JSON API for the portfolio.`),
      "package.json": makeFile(`{
  "name": "portfolio-api",
  "version": "0.1.0",
  "scripts": {
    "dev": "node src/server.js"
  }
}`),
      src: makeDir({
        "server.js": makeFile(`const http = require('http');

http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ status: 'ok' }));
}).listen(8080);`),
      }),
    }),
  }),
  notes: makeDir({
    "todo.txt": makeFile("- landing page refresh\n- add docs\n- ship"),
    "ideas.md": makeFile("# Ideas\n\n- Bento landing\n- Build pipeline view"),
  }),
  bin: makeDir({
    deploy: makeFile("#!/usr/bin/env bash\necho \"deploying...\""),
  }),
  ".ssh": makeDir({
    config: makeFile("Host github.com\n  User git\n  IdentityFile ~/.ssh/id_ed25519"),
    known_hosts: makeFile("github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA..."),
  }),
  ".bashrc": makeFile("export PATH=\"$HOME/bin:$PATH\"\nalias ll='ls -la'\n"),
  ".gitconfig": makeFile("[user]\n  name = Developer\n  email = dev@example.com\n"),
});

function cloneNode(node: FSNode): FSNode {
  if (node.type === "file") return { ...node };
  const children: Record<string, FSNode> = {};
  for (const [name, child] of Object.entries(node.children)) {
    children[name] = cloneNode(child);
  }
  return { ...node, children };
}

function splitPath(path: string): string[] {
  return path.split("/").filter(Boolean);
}

function resolvePath(cwd: string, target: string): string | null {
  if (!target || target === "~") return "~";
  if (target === "/") return "~";

  let parts: string[] = [];
  if (target.startsWith("~/")) {
    parts = ["~", ...splitPath(target.slice(2))];
  } else if (target.startsWith("/")) {
    parts = ["~", ...splitPath(target.slice(1))];
  } else {
    parts = [...splitPath(cwd), ...splitPath(target)];
  }

  const resolved: string[] = [];
  for (const p of parts) {
    if (p === ".") continue;
    if (p === "..") {
      if (resolved.length > 1) resolved.pop();
      continue;
    }
    if (p === "~") {
      resolved.length = 1;
      resolved[0] = "~";
      continue;
    }
    resolved.push(p);
  }
  if (resolved.length === 0) return "~";
  if (resolved[0] !== "~") resolved.unshift("~");
  return resolved.join("/");
}

function getNode(root: FSDir, path: string): FSNode | null {
  const parts = splitPath(path);
  if (parts.length === 0 || parts[0] !== "~") return null;
  let node: FSNode = root;
  for (let i = 1; i < parts.length; i++) {
    if (node.type !== "dir") return null;
    node = node.children[parts[i]] ?? null;
    if (!node) return null;
  }
  return node;
}

function getParent(root: FSDir, path: string): { parent: FSDir | null; name: string } {
  const parts = splitPath(path);
  const name = parts.pop();
  if (!name) return { parent: null, name: "" };
  const parentPath = parts.length ? parts.join("/") : "~";
  const parent = getNode(root, parentPath);
  if (!parent || parent.type !== "dir") return { parent: null, name };
  return { parent, name };
}

function listEntries(dir: FSDir, showHidden: boolean): [string, FSNode][] {
  const entries = Object.entries(dir.children).filter(([name]) =>
    showHidden ? true : !name.startsWith(".")
  );
  entries.sort((a, b) => {
    const aDir = a[1].type === "dir";
    const bDir = b[1].type === "dir";
    if (aDir && !bDir) return -1;
    if (!aDir && bDir) return 1;
    return a[0].localeCompare(b[0]);
  });
  return entries;
}

function formatSize(bytes: number, human: boolean): string {
  if (!human) return `${bytes}`;
  const units = ["B", "K", "M", "G"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(value >= 10 || i === 0 ? 0 : 1)}${units[i]}`;
}

function formatDate(ts: number): string {
  const d = new Date(ts);
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const month = months[d.getMonth()];
  const day = String(d.getDate()).padStart(2, " ");
  const hours = String(d.getHours()).padStart(2, "0");
  const mins = String(d.getMinutes()).padStart(2, "0");
  return `${month} ${day} ${hours}:${mins}`;
}

function toAbsolute(path: string): string {
  return path.replace("~", HOME_DIR);
}

function isValidVarName(name: string): boolean {
  return /^[A-Za-z_][A-Za-z0-9_]*$/.test(name);
}

function matchPattern(input: string, pattern: string): boolean {
  const escaped = pattern.replace(/[-/\\^$+?.()|[\]{}]/g, "\\$&");
  const regex = "^" + escaped.replace(/\*/g, ".*").replace(/\?/g, ".") + "$";
  return new RegExp(regex).test(input);
}

function walkTree(node: FSNode, basePath: string, onFile: (path: string, node: FSNode) => void) {
  if (node.type === "file") {
    onFile(basePath, node);
    return;
  }
  onFile(basePath, node);
  for (const [name, child] of Object.entries(node.children)) {
    walkTree(child, `${basePath}/${name}`, onFile);
  }
}

function writeFile(root: FSDir, path: string, content: string, append: boolean): string | null {
  const { parent, name } = getParent(root, path);
  if (!parent) return `cannot create '${path}': No such file or directory`;
  const existing = parent.children[name];
  if (existing && existing.type === "dir") return `cannot overwrite '${name}': Is a directory`;
  const now = Date.now();
  if (existing && existing.type === "file") {
    existing.content = append ? `${existing.content}${content}` : content;
    existing.mtime = now;
    return null;
  }
  parent.children[name] = makeFile(content, now);
  return null;
}

function makeDirAt(root: FSDir, path: string, recursive: boolean): string | null {
  const parts = splitPath(path);
  if (parts.length === 0 || parts[0] !== "~") return "invalid path";
  let node: FSDir = root;
  for (let i = 1; i < parts.length; i++) {
    const name = parts[i];
    const existing = node.children[name];
    if (!existing) {
      if (!recursive && i !== parts.length - 1) {
        return `cannot create directory '${path}': No such file or directory`;
      }
      const created = makeDir({}, Date.now());
      node.children[name] = created;
      node = created;
      continue;
    }
    if (existing.type !== "dir") {
      return `cannot create directory '${path}': Not a directory`;
    }
    node = existing;
  }
  return null;
}

function removeNode(root: FSDir, path: string, recursive: boolean): string | null {
  const { parent, name } = getParent(root, path);
  if (!parent) return `cannot remove '${path}': No such file or directory`;
  const node = parent.children[name];
  if (!node) return `cannot remove '${path}': No such file or directory`;
  if (node.type === "dir" && !recursive) {
    return `cannot remove '${path}': Is a directory`;
  }
  delete parent.children[name];
  return null;
}

function copyNode(root: FSDir, src: string, dest: string, recursive: boolean): string | null {
  const srcNode = getNode(root, src);
  if (!srcNode) return `cannot stat '${src}': No such file or directory`;
  if (srcNode.type === "dir" && !recursive) {
    return `omitting directory '${src}'`;
  }
  const destNode = getNode(root, dest);
  const { parent, name } = getParent(root, dest);
  if (!parent) return `cannot create '${dest}': No such file or directory`;

  if (destNode && destNode.type === "dir") {
    parent.children[name] = destNode;
  }
  const finalParent = destNode && destNode.type === "dir" ? destNode : parent;
  const finalName = destNode && destNode.type === "dir" ? src.split("/").pop() || name : name;
  finalParent.children[finalName] = cloneNode(srcNode);
  return null;
}

function moveNode(root: FSDir, src: string, dest: string): string | null {
  const srcNode = getNode(root, src);
  if (!srcNode) return `cannot stat '${src}': No such file or directory`;
  const { parent, name } = getParent(root, src);
  if (!parent) return `cannot move '${src}': No such file or directory`;
  const destNode = getNode(root, dest);
  const destParent = destNode && destNode.type === "dir" ? destNode : getParent(root, dest).parent;
  if (!destParent) return `cannot move '${dest}': No such file or directory`;
  const destName = destNode && destNode.type === "dir" ? name : dest.split("/").pop() || name;
  destParent.children[destName] = srcNode;
  delete parent.children[name];
  return null;
}

/* ═══════════════════════════════════════════════════════════════
   Shell Parsing + Commands
   ═══════════════════════════════════════════════════════════════ */

type OutputLine = { text: string; cls?: string };
type CommandResult = { output: OutputLine[]; cwd: string; exitCode: number; clear?: boolean };

const COMMAND_LIST = [
  "help",
  "ls",
  "cd",
  "pwd",
  "cat",
  "echo",
  "clear",
  "reset",
  "whoami",
  "id",
  "date",
  "tree",
  "mkdir",
  "touch",
  "rm",
  "mv",
  "cp",
  "find",
  "stat",
  "grep",
  "head",
  "tail",
  "wc",
  "sort",
  "uniq",
  "cut",
  "tr",
  "sed",
  "history",
  "alias",
  "unalias",
  "export",
  "unset",
  "env",
  "printenv",
  "which",
  "type",
  "file",
  "uname",
  "hostname",
  "uptime",
  "ps",
  "df",
  "free",
  "ip",
  "ifconfig",
  "netstat",
  "ping",
  "curl",
  "wget",
  "ssh",
  "git",
  "npm",
  "npx",
  "node",
  "python",
  "python3",
  "make",
  "docker",
  "sleep",
  "true",
  "false",
  "yes",
  "seq",
  "factor",
  "bc",
  "expr",
  "cal",
  "man",
  "apropos",
  "fortune",
  "cowsay",
  "sl",
  "exit",
];

const HELP_LINES = [
  "Files: ls, cd, pwd, cat, touch, mkdir, rm, mv, cp, find, stat, tree",
  "Text: grep, sort, uniq, wc, head, tail, cut, tr, sed",
  "Shell: alias, export, unset, env, printenv, history, type, which, clear",
  "System: date, uname, id, whoami, uptime, ps, df, free, hostname",
  "Network: ping, curl, wget, ssh, ip, ifconfig, netstat",
  "Dev: git, npm, npx, node, python3, make, docker",
  "Fun: fortune, cowsay, man, apropos, sl",
  "Features: pipes |, redirection > >>, variables $VAR, chaining &&",
];

function tokenize(input: string): string[] {
  const tokens: string[] = [];
  let current = "";
  let inSingle = false;
  let inDouble = false;

  const push = () => {
    if (current.length) tokens.push(current);
    current = "";
  };

  for (let i = 0; i < input.length; i++) {
    const ch = input[i];
    if (ch === "\\" && !inSingle) {
      if (i + 1 < input.length) {
        current += input[i + 1];
        i++;
        continue;
      }
    }
    if (ch === "'" && !inDouble) {
      inSingle = !inSingle;
      continue;
    }
    if (ch === '"' && !inSingle) {
      inDouble = !inDouble;
      continue;
    }
    if (!inSingle && !inDouble) {
      if (ch === "&" && input[i + 1] === "&") {
        push();
        tokens.push("&&");
        i++;
        continue;
      }
      if (ch === ">") {
        push();
        if (input[i + 1] === ">") {
          tokens.push(">>");
          i++;
        } else {
          tokens.push(">");
        }
        continue;
      }
      if (ch === "|" || ch === ";") {
        push();
        tokens.push(ch);
        continue;
      }
      if (/\s/.test(ch)) {
        push();
        continue;
      }
    }
    current += ch;
  }
  push();
  return tokens;
}

function expandToken(token: string, env: Record<string, string>, lastStatus: number, cwd: string): string {
  return token.replace(/\$(\w+|\?|\{[^}]+\})/g, (_, name: string) => {
    let key = name;
    if (key.startsWith("{") && key.endsWith("}")) {
      key = key.slice(1, -1);
    }
    if (key === "?") return String(lastStatus);
    if (key === "PWD") return env.PWD ?? toAbsolute(cwd);
    if (key === "HOME") return env.HOME ?? HOME_DIR;
    return env[key] ?? "";
  });
}

function splitByOperator(tokens: string[], op: string): string[][] {
  const groups: string[][] = [];
  let current: string[] = [];
  for (const token of tokens) {
    if (token === op) {
      if (current.length) groups.push(current);
      current = [];
    } else {
      current.push(token);
    }
  }
  if (current.length) groups.push(current);
  return groups;
}

function parseRedirection(tokens: string[]): { tokens: string[]; redirect?: { path: string; append: boolean } } {
  const idx = tokens.findIndex((t) => t === ">" || t === ">>");
  if (idx === -1) return { tokens };
  const op = tokens[idx];
  const target = tokens[idx + 1];
  if (!target) return { tokens: tokens.slice(0, idx) };
  const cleaned = [...tokens.slice(0, idx), ...tokens.slice(idx + 2)];
  return { tokens: cleaned, redirect: { path: target, append: op === ">>" } };
}

function limitOutput(lines: OutputLine[], limit = 300): OutputLine[] {
  if (lines.length <= limit) return lines;
  return [...lines.slice(0, limit), { text: `... (${lines.length - limit} more lines truncated)`, cls: "text-zinc-500" }];
}

function safeEvalMath(expr: string): string | null {
  let i = 0;

  const skip = () => {
    while (i < expr.length && /\s/.test(expr[i])) i++;
  };

  const parseNumber = (): number | null => {
    skip();
    let start = i;
    let seenDot = false;
    while (i < expr.length) {
      const ch = expr[i];
      if (ch === ".") {
        if (seenDot) break;
        seenDot = true;
        i++;
        continue;
      }
      if (!/[0-9]/.test(ch)) break;
      i++;
    }
    if (start === i) return null;
    const value = Number(expr.slice(start, i));
    if (Number.isNaN(value)) return null;
    return value;
  };

  const parseFactor = (): number | null => {
    skip();
    const ch = expr[i];
    if (ch === "+") {
      i++;
      return parseFactor();
    }
    if (ch === "-") {
      i++;
      const value = parseFactor();
      return value === null ? null : -value;
    }
    if (ch === "(") {
      i++;
      const value = parseExpression();
      skip();
      if (expr[i] !== ")") return null;
      i++;
      return value;
    }
    return parseNumber();
  };

  const parseTerm = (): number | null => {
    let value = parseFactor();
    if (value === null) return null;
    while (true) {
      skip();
      const op = expr[i];
      if (op !== "*" && op !== "/" && op !== "%") break;
      i++;
      const rhs = parseFactor();
      if (rhs === null) return null;
      if (op === "*") value *= rhs;
      if (op === "/") {
        if (rhs === 0) return null;
        value /= rhs;
      }
      if (op === "%") {
        if (rhs === 0) return null;
        value %= rhs;
      }
    }
    return value;
  };

  const parseExpression = (): number | null => {
    let value = parseTerm();
    if (value === null) return null;
    while (true) {
      skip();
      const op = expr[i];
      if (op !== "+" && op !== "-") break;
      i++;
      const rhs = parseTerm();
      if (rhs === null) return null;
      if (op === "+") value += rhs;
      if (op === "-") value -= rhs;
    }
    return value;
  };

  const result = parseExpression();
  skip();
  if (result === null || i < expr.length) return null;
  if (!Number.isFinite(result)) return null;
  return String(result);
}

function formatCalendar(date = new Date()): string[] {
  const year = date.getFullYear();
  const month = date.getMonth();
  const monthNames = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
  ];
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const lines: string[] = [];
  const title = `${monthNames[month]} ${year}`;
  lines.push(title.padStart(10 + Math.floor(title.length / 2), " "));
  lines.push("Su Mo Tu We Th Fr Sa");
  let line = "".padStart(firstDay * 3, " ");
  for (let day = 1; day <= daysInMonth; day++) {
    line += String(day).padStart(2, " ") + " ";
    if ((firstDay + day) % 7 === 0 || day === daysInMonth) {
      lines.push(line.trimEnd());
      line = "";
    }
  }
  return lines;
}

function cowsay(text: string): string[] {
  const content = text || "Hello";
  const top = " " + "_".repeat(content.length + 2);
  const mid = `< ${content} >`;
  const bot = " " + "-".repeat(content.length + 2);
  return [
    top,
    mid,
    bot,
    "        \\",
    "         \\",
    "          ^__^",
    "          (oo)\\_______",
    "          (__)\\       )\\/\\",
    "              ||----w |",
    "              ||     ||",
  ];
}

function tokenizeAlias(value: string): string[] {
  return tokenize(value);
}

function getCommandCandidates(aliases: Record<string, string>): string[] {
  const aliasNames = Object.keys(aliases);
  return Array.from(new Set([...COMMAND_LIST, ...aliasNames])).sort();
}

/* ═══════════════════════════════════════════════════════════════
   Demo Animation Lines
   ═══════════════════════════════════════════════════════════════ */

const DEMO_COMMAND = "git push origin main";

type DemoLine = {
  text: string;
  cls: string;
  delay?: number;
  gap?: boolean;
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
  const fsRef = useRef<FSDir>(cloneNode(INITIAL_FS) as FSDir);
  const envRef = useRef<Record<string, string>>({
    HOME: HOME_DIR,
    USER: "developer",
    LOGNAME: "developer",
    SHELL: "/bin/bash",
    TERM: "xterm-256color",
    LANG: "en_US.UTF-8",
    EDITOR: "vim",
  });
  const aliasRef = useRef<Record<string, string>>({ ll: "ls -la" });
  const lastStatusRef = useRef(0);

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => setPhase("typing"), 500);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (phase !== "typing") return;
    if (typedChars >= DEMO_COMMAND.length) {
      const t = setTimeout(() => setPhase("output"), 350);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setTypedChars((c) => c + 1), 40 + Math.random() * 35);
    return () => clearTimeout(t);
  }, [phase, typedChars]);

  useEffect(() => {
    if (phase !== "output") return;
    if (visibleLines >= ALL_DEMO_LINES.length) {
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

  useEffect(() => {
    if (phase === "interactive") {
      inputRef.current?.focus();
      scrollToBottom();
    }
  }, [phase, scrollToBottom]);

  useEffect(() => {
    scrollToBottom();
  }, [history, scrollToBottom]);

  const runCommandTokens = (
    tokens: string[],
    stdin: string[],
    currentCwd: string,
    env: Record<string, string>,
    aliases: Record<string, string>
  ): CommandResult => {
    const error = (text: string): OutputLine => ({ text, cls: "text-red-400" });
    const info = (text: string): OutputLine => ({ text, cls: "text-zinc-400" });
    const ok = (lines: string[], cls?: string): OutputLine[] =>
      lines.map((line) => ({ text: line, cls }));

    if (tokens.length === 0) {
      return { output: [], cwd: currentCwd, exitCode: 0 };
    }

    let workingTokens = [...tokens];
    const assignRegex = /^[A-Za-z_][A-Za-z0-9_]*=.*/;
    while (workingTokens[0] && assignRegex.test(workingTokens[0])) {
      const [key, ...rest] = workingTokens[0].split("=");
      if (isValidVarName(key)) {
        env[key] = rest.join("=");
      }
      workingTokens.shift();
    }

    if (workingTokens.length === 0) {
      return { output: [], cwd: currentCwd, exitCode: 0 };
    }

    const cmd = workingTokens[0];
    const args = workingTokens.slice(1);

    switch (cmd) {
      case "help": {
        return { output: [info("Available commands:"), ...ok(HELP_LINES)], cwd: currentCwd, exitCode: 0 };
      }

      case "clear":
      case "reset": {
        return { output: [], cwd: currentCwd, exitCode: 0, clear: true };
      }

      case "pwd": {
        return { output: ok([toAbsolute(currentCwd)]), cwd: currentCwd, exitCode: 0 };
      }

      case "cd": {
        if (!args[0] || args[0] === "~") return { output: [], cwd: "~", exitCode: 0 };
        const target = resolvePath(currentCwd, args[0]);
        if (!target) return { output: [error(`cd: no such file or directory: ${args[0]}`)], cwd: currentCwd, exitCode: 1 };
        const node = getNode(fsRef.current, target);
        if (!node) return { output: [error(`cd: no such file or directory: ${args[0]}`)], cwd: currentCwd, exitCode: 1 };
        if (node.type !== "dir") return { output: [error(`cd: not a directory: ${args[0]}`)], cwd: currentCwd, exitCode: 1 };
        return { output: [], cwd: target, exitCode: 0 };
      }

      case "ls": {
        const flags = new Set<string>();
        const targets: string[] = [];
        for (const arg of args) {
          if (arg.startsWith("-") && arg !== "-") {
            for (const ch of arg.slice(1)) flags.add(ch);
          } else {
            targets.push(arg);
          }
        }
        const showHidden = flags.has("a");
        const long = flags.has("l");
        const human = flags.has("h");
        const onePerLine = flags.has("1");
        const output: OutputLine[] = [];
        const listTarget = (targetPath: string, label?: string) => {
          const node = getNode(fsRef.current, targetPath);
          if (!node) {
            output.push(error(`ls: cannot access '${label ?? targetPath}': No such file or directory`));
            return;
          }
          if (label && targets.length > 1) {
            output.push(info(`${label}:`));
          }
          if (node.type === "file") {
            output.push({ text: label ?? (targetPath.split("/").pop() || ""), cls: "text-zinc-300" });
            return;
          }
          const entries = listEntries(node, showHidden);
          if (showHidden) {
            entries.unshift([".", node]);
            entries.unshift(["..", node]);
          }
          if (long) {
            for (const [name, child] of entries) {
              const size = child.type === "file" ? child.content.length : 512;
              const displayName = child.type === "dir" ? `${name}/` : name;
              output.push({
                text: `${child.mode} 1 developer staff ${formatSize(size, human).padStart(5, " ")} ${formatDate(child.mtime)} ${displayName}`,
                cls: "text-zinc-300",
              });
            }
          } else if (onePerLine) {
            for (const [name, child] of entries) {
              output.push({ text: child.type === "dir" ? `${name}/` : name, cls: "text-zinc-300" });
            }
          } else {
            const list = entries.map(([name, child]) => (child.type === "dir" ? `${name}/` : name));
            output.push({ text: list.join("  "), cls: "text-zinc-300" });
          }
        };

        if (targets.length === 0) {
          listTarget(currentCwd);
        } else {
          for (const target of targets) {
            const resolved = resolvePath(currentCwd, target);
            if (!resolved) {
              output.push(error(`ls: cannot access '${target}': No such file or directory`));
              continue;
            }
            listTarget(resolved, target);
          }
        }

        return { output: output.length ? output : [], cwd: currentCwd, exitCode: output.some((l) => l.cls === "text-red-400") ? 1 : 0 };
      }

      case "cat": {
        if (args.length === 0) {
          return { output: ok(stdin), cwd: currentCwd, exitCode: 0 };
        }
        const out: OutputLine[] = [];
        let exitCode = 0;
        for (const arg of args) {
          const target = resolvePath(currentCwd, arg);
          if (!target) {
            out.push(error(`cat: ${arg}: No such file or directory`));
            exitCode = 1;
            continue;
          }
          const node = getNode(fsRef.current, target);
          if (!node) {
            out.push(error(`cat: ${arg}: No such file or directory`));
            exitCode = 1;
            continue;
          }
          if (node.type === "dir") {
            out.push(error(`cat: ${arg}: Is a directory`));
            exitCode = 1;
            continue;
          }
          out.push(...ok(node.content.split("\n")));
        }
        return { output: out, cwd: currentCwd, exitCode };
      }

      case "echo": {
        const noNewline = args[0] === "-n";
        const start = noNewline ? 1 : 0;
        const content = args.slice(start).join(" ");
        return { output: ok([content]), cwd: currentCwd, exitCode: 0 };
      }

      case "whoami": {
        return { output: ok(["developer"]), cwd: currentCwd, exitCode: 0 };
      }

      case "id": {
        return {
          output: ok(["uid=1000(developer) gid=1000(developer) groups=1000(developer)"]),
          cwd: currentCwd,
          exitCode: 0,
        };
      }

      case "date": {
        const now = new Date();
        if (args.includes("-I")) {
          return { output: ok([now.toISOString().slice(0, 10)]), cwd: currentCwd, exitCode: 0 };
        }
        if (args.includes("-R")) {
          return { output: ok([now.toUTCString()]), cwd: currentCwd, exitCode: 0 };
        }
        if (args.includes("-u")) {
          return { output: ok([now.toUTCString()]), cwd: currentCwd, exitCode: 0 };
        }
        return { output: ok([now.toString()]), cwd: currentCwd, exitCode: 0 };
      }

      case "tree": {
        const target = args[0] ? resolvePath(currentCwd, args[0]) : currentCwd;
        if (!target) return { output: [error(`tree: '${args[0]}': No such file or directory`)], cwd: currentCwd, exitCode: 1 };
        const node = getNode(fsRef.current, target);
        if (!node) return { output: [error(`tree: '${args[0]}': No such file or directory`)], cwd: currentCwd, exitCode: 1 };
        if (node.type === "file") return { output: ok([args[0] || "."]), cwd: currentCwd, exitCode: 0 };
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
        };
        walk(node, "");
        return { output: ok(lines), cwd: currentCwd, exitCode: 0 };
      }

      case "mkdir": {
        if (args.length === 0) return { output: [error("mkdir: missing operand")], cwd: currentCwd, exitCode: 1 };
        const recursive = args.includes("-p");
        const targets = args.filter((a) => a !== "-p");
        const out: OutputLine[] = [];
        let exitCode = 0;
        for (const targetRaw of targets) {
          const target = resolvePath(currentCwd, targetRaw);
          if (!target) {
            out.push(error(`mkdir: cannot create directory '${targetRaw}'`));
            exitCode = 1;
            continue;
          }
          if (getNode(fsRef.current, target)) {
            if (!recursive) {
              out.push(error(`mkdir: cannot create directory '${targetRaw}': File exists`));
              exitCode = 1;
            }
            continue;
          }
          const err = makeDirAt(fsRef.current, target, recursive);
          if (err) {
            out.push(error(`mkdir: ${err}`));
            exitCode = 1;
          }
        }
        return { output: out, cwd: currentCwd, exitCode };
      }

      case "touch": {
        if (args.length === 0) return { output: [error("touch: missing file operand")], cwd: currentCwd, exitCode: 1 };
        const out: OutputLine[] = [];
        let exitCode = 0;
        for (const arg of args) {
          const target = resolvePath(currentCwd, arg);
          if (!target) {
            out.push(error(`touch: cannot touch '${arg}': No such file or directory`));
            exitCode = 1;
            continue;
          }
          const existing = getNode(fsRef.current, target);
          if (existing) {
            existing.mtime = Date.now();
            continue;
          }
          const err = writeFile(fsRef.current, target, "", false);
          if (err) {
            out.push(error(`touch: ${err}`));
            exitCode = 1;
          }
        }
        return { output: out, cwd: currentCwd, exitCode };
      }

      case "rm": {
        if (args.length === 0) return { output: [error("rm: missing operand")], cwd: currentCwd, exitCode: 1 };
        const recursive = args.includes("-r") || args.includes("-rf") || args.includes("-fr");
        const force = args.includes("-f") || args.includes("-rf") || args.includes("-fr");
        const targets = args.filter((a) => !a.startsWith("-"));
        const out: OutputLine[] = [];
        let exitCode = 0;
        for (const arg of targets) {
          const target = resolvePath(currentCwd, arg);
          if (!target) {
            if (!force) out.push(error(`rm: cannot remove '${arg}': No such file or directory`));
            if (!force) exitCode = 1;
            continue;
          }
          const err = removeNode(fsRef.current, target, recursive);
          if (err && !force) {
            out.push(error(`rm: ${err}`));
            exitCode = 1;
          }
        }
        return { output: out, cwd: currentCwd, exitCode };
      }

      case "mv": {
        if (args.length < 2) return { output: [error("mv: missing file operand")], cwd: currentCwd, exitCode: 1 };
        const destRaw = args[args.length - 1];
        const sources = args.slice(0, -1);
        const dest = resolvePath(currentCwd, destRaw);
        if (!dest) return { output: [error(`mv: cannot move to '${destRaw}'`)], cwd: currentCwd, exitCode: 1 };
        let exitCode = 0;
        const out: OutputLine[] = [];
        for (const srcRaw of sources) {
          const src = resolvePath(currentCwd, srcRaw);
          if (!src) {
            out.push(error(`mv: cannot stat '${srcRaw}': No such file or directory`));
            exitCode = 1;
            continue;
          }
          const err = moveNode(fsRef.current, src, dest);
          if (err) {
            out.push(error(`mv: ${err}`));
            exitCode = 1;
          }
        }
        return { output: out, cwd: currentCwd, exitCode };
      }

      case "cp": {
        if (args.length < 2) return { output: [error("cp: missing file operand")], cwd: currentCwd, exitCode: 1 };
        const recursive = args.includes("-r") || args.includes("-R");
        const filtered = args.filter((a) => !a.startsWith("-"));
        const destRaw = filtered[filtered.length - 1];
        const sources = filtered.slice(0, -1);
        const dest = resolvePath(currentCwd, destRaw);
        if (!dest) return { output: [error(`cp: cannot copy to '${destRaw}'`)], cwd: currentCwd, exitCode: 1 };
        const out: OutputLine[] = [];
        let exitCode = 0;
        for (const srcRaw of sources) {
          const src = resolvePath(currentCwd, srcRaw);
          if (!src) {
            out.push(error(`cp: cannot stat '${srcRaw}': No such file or directory`));
            exitCode = 1;
            continue;
          }
          const err = copyNode(fsRef.current, src, dest, recursive);
          if (err) {
            out.push(error(`cp: ${err}`));
            exitCode = 1;
          }
        }
        return { output: out, cwd: currentCwd, exitCode };
      }

      case "find": {
        let startPath = ".";
        let namePattern: string | null = null;
        let typePattern: string | null = null;
        for (let i = 0; i < args.length; i++) {
          const arg = args[i];
          if (arg === "-name") {
            namePattern = args[i + 1] ?? null;
            i++;
            continue;
          }
          if (arg === "-type") {
            typePattern = args[i + 1] ?? null;
            i++;
            continue;
          }
          if (!arg.startsWith("-")) startPath = arg;
        }

        const resolved = resolvePath(currentCwd, startPath);
        if (!resolved) return { output: [error(`find: '${startPath}': No such file or directory`)], cwd: currentCwd, exitCode: 1 };
        const node = getNode(fsRef.current, resolved);
        if (!node) return { output: [error(`find: '${startPath}': No such file or directory`)], cwd: currentCwd, exitCode: 1 };
        const absResolved = toAbsolute(resolved);
        const lines: string[] = [];
        walkTree(node, resolved, (path, n) => {
          if (typePattern) {
            if (typePattern === "f" && n.type !== "file") return;
            if (typePattern === "d" && n.type !== "dir") return;
          }
          if (namePattern) {
            const base = path.split("/").pop() || "";
            if (!matchPattern(base, namePattern)) return;
          }
          const absPath = toAbsolute(path);
          const display = absPath === absResolved ? "." : absPath.replace(absResolved, ".");
          lines.push(display);
        });
        return { output: ok(lines), cwd: currentCwd, exitCode: 0 };
      }

      case "stat": {
        if (!args[0]) return { output: [error("stat: missing operand")], cwd: currentCwd, exitCode: 1 };
        const target = resolvePath(currentCwd, args[0]);
        if (!target) return { output: [error(`stat: cannot stat '${args[0]}'`)], cwd: currentCwd, exitCode: 1 };
        const node = getNode(fsRef.current, target);
        if (!node) return { output: [error(`stat: cannot stat '${args[0]}'`)], cwd: currentCwd, exitCode: 1 };
        const size = node.type === "file" ? node.content.length : 512;
        const mode = node.mode;
        const type = node.type === "dir" ? "directory" : "regular file";
        const date = new Date(node.mtime).toString();
        return {
          output: ok([
            `  File: ${args[0]}`,
            `  Size: ${size}        Blocks: 8          IO Block: 4096 ${type}`,
            `Device: 00h/0d Inode: 0       Links: 1`,
            `Access: (${mode})  Uid: ( 1000/ developer)   Gid: ( 1000/ developer)`,
            `Access: ${date}`,
            `Modify: ${date}`,
            `Change: ${date}`,
          ]),
          cwd: currentCwd,
          exitCode: 0,
        };
      }

      case "grep": {
        const recursive = args.includes("-r");
        const ignoreCase = args.includes("-i");
        const showLine = args.includes("-n");
        const filtered = args.filter((a) => !a.startsWith("-"));
        const pattern = filtered[0];
        const targets = filtered.slice(1);
        if (!pattern) return { output: [error("grep: missing search pattern")], cwd: currentCwd, exitCode: 2 };
        let regex: RegExp;
        try {
          regex = new RegExp(pattern, ignoreCase ? "i" : undefined);
        } catch {
          return { output: [error("grep: invalid regex")], cwd: currentCwd, exitCode: 2 };
        }
        const out: OutputLine[] = [];
        const searchLines = (lines: string[], label?: string) => {
          lines.forEach((line, idx) => {
            if (regex.test(line)) {
              const prefix = label ? `${label}:` : "";
              const lineNum = showLine ? `${idx + 1}:` : "";
              out.push({ text: `${prefix}${lineNum}${line}`, cls: "text-zinc-300" });
            }
          });
        };

        if (targets.length === 0) {
          searchLines(stdin);
          return { output: out, cwd: currentCwd, exitCode: out.length ? 0 : 1 };
        }

        for (const targetRaw of targets) {
          const target = resolvePath(currentCwd, targetRaw);
          if (!target) {
            out.push(error(`grep: ${targetRaw}: No such file or directory`));
            continue;
          }
          const node = getNode(fsRef.current, target);
          if (!node) {
            out.push(error(`grep: ${targetRaw}: No such file or directory`));
            continue;
          }
          if (node.type === "file") {
            searchLines(node.content.split("\n"), targetRaw);
          } else if (recursive) {
            walkTree(node, target, (path, child) => {
              if (child.type !== "file") return;
              searchLines(child.content.split("\n"), path);
            });
          } else {
            out.push(error(`grep: ${targetRaw}: Is a directory`));
          }
        }

        return { output: out, cwd: currentCwd, exitCode: out.length ? 0 : 1 };
      }

      case "head": {
        const countIdx = args.indexOf("-n");
        const count = countIdx !== -1 ? Number(args[countIdx + 1] ?? 10) : 10;
        const files = countIdx !== -1
          ? args.filter((_, idx) => idx !== countIdx && idx !== countIdx + 1)
          : args.filter((a) => !a.startsWith("-"));
        if (files.length === 0) {
          return { output: ok(stdin.slice(0, count)), cwd: currentCwd, exitCode: 0 };
        }
        const out: OutputLine[] = [];
        let exitCode = 0;
        for (const file of files) {
          const target = resolvePath(currentCwd, file);
          const node = target ? getNode(fsRef.current, target) : null;
          if (!node || node.type !== "file") {
            out.push(error(`head: cannot open '${file}' for reading`));
            exitCode = 1;
            continue;
          }
          out.push(...ok(node.content.split("\n").slice(0, count)));
        }
        return { output: out, cwd: currentCwd, exitCode };
      }

      case "tail": {
        const countIdx = args.indexOf("-n");
        const count = countIdx !== -1 ? Number(args[countIdx + 1] ?? 10) : 10;
        const files = countIdx !== -1
          ? args.filter((_, idx) => idx !== countIdx && idx !== countIdx + 1)
          : args.filter((a) => !a.startsWith("-"));
        if (files.length === 0) {
          return { output: ok(stdin.slice(-count)), cwd: currentCwd, exitCode: 0 };
        }
        const out: OutputLine[] = [];
        let exitCode = 0;
        for (const file of files) {
          const target = resolvePath(currentCwd, file);
          const node = target ? getNode(fsRef.current, target) : null;
          if (!node || node.type !== "file") {
            out.push(error(`tail: cannot open '${file}' for reading`));
            exitCode = 1;
            continue;
          }
          out.push(...ok(node.content.split("\n").slice(-count)));
        }
        return { output: out, cwd: currentCwd, exitCode };
      }

      case "wc": {
        const flags = new Set<string>();
        const files: string[] = [];
        for (const arg of args) {
          if (arg.startsWith("-")) {
            for (const ch of arg.slice(1)) flags.add(ch);
          } else {
            files.push(arg);
          }
        }
        const countLines = flags.size === 0 || flags.has("l");
        const countWords = flags.size === 0 || flags.has("w");
        const countBytes = flags.size === 0 || flags.has("c");
        const out: OutputLine[] = [];

        const summarize = (label: string, content: string) => {
          const lines = content.split("\n");
          const words = content.trim().length ? content.trim().split(/\s+/).length : 0;
          const bytes = content.length;
          const parts = [
            countLines ? String(lines.length).padStart(7, " ") : "",
            countWords ? String(words).padStart(7, " ") : "",
            countBytes ? String(bytes).padStart(7, " ") : "",
            label,
          ].filter(Boolean);
          out.push({ text: parts.join(" "), cls: "text-zinc-300" });
        };

        if (files.length === 0) {
          summarize("", stdin.join("\n"));
          return { output: out, cwd: currentCwd, exitCode: 0 };
        }

        for (const file of files) {
          const target = resolvePath(currentCwd, file);
          const node = target ? getNode(fsRef.current, target) : null;
          if (!node || node.type !== "file") {
            out.push(error(`wc: ${file}: No such file or directory`));
            continue;
          }
          summarize(file, node.content);
        }
        return { output: out, cwd: currentCwd, exitCode: out.some((l) => l.cls === "text-red-400") ? 1 : 0 };
      }

      case "sort": {
        const reverse = args.includes("-r");
        const numeric = args.includes("-n");
        const files = args.filter((a) => !a.startsWith("-"));
        let lines: string[] = [];
        if (files.length === 0) {
          lines = [...stdin];
        } else {
          for (const file of files) {
            const target = resolvePath(currentCwd, file);
            const node = target ? getNode(fsRef.current, target) : null;
            if (!node || node.type !== "file") return { output: [error(`sort: ${file}: No such file or directory`)], cwd: currentCwd, exitCode: 1 };
            lines.push(...node.content.split("\n"));
          }
        }
        lines.sort((a, b) => {
          if (numeric) return Number(a.trim()) - Number(b.trim());
          return a.localeCompare(b);
        });
        if (reverse) lines.reverse();
        return { output: ok(lines), cwd: currentCwd, exitCode: 0 };
      }

      case "uniq": {
        const count = args.includes("-c");
        const files = args.filter((a) => !a.startsWith("-"));
        const lines = files.length ? [] : [...stdin];
        if (files.length) {
          for (const file of files) {
            const target = resolvePath(currentCwd, file);
            const node = target ? getNode(fsRef.current, target) : null;
            if (!node || node.type !== "file") return { output: [error(`uniq: ${file}: No such file or directory`)], cwd: currentCwd, exitCode: 1 };
            lines.push(...node.content.split("\n"));
          }
        }
        const out: string[] = [];
        let prev = "";
        let countNum = 0;
        const flush = () => {
          if (countNum === 0) return;
          out.push(count ? `${String(countNum).padStart(7, " ")} ${prev}` : prev);
        };
        for (const line of lines) {
          if (line === prev) {
            countNum++;
          } else {
            flush();
            prev = line;
            countNum = 1;
          }
        }
        flush();
        return { output: ok(out), cwd: currentCwd, exitCode: 0 };
      }

      case "cut": {
        let delim = "\t";
        let fieldsRaw: string | null = null;
        const files: string[] = [];
        for (let i = 0; i < args.length; i++) {
          const arg = args[i];
          if (arg === "-d") {
            delim = args[i + 1] ?? "\t";
            i++;
            continue;
          }
          if (arg === "-f") {
            fieldsRaw = args[i + 1] ?? null;
            i++;
            continue;
          }
          if (arg.startsWith("-")) continue;
          files.push(arg);
        }
        if (!fieldsRaw) return { output: [error("cut: missing -f list")], cwd: currentCwd, exitCode: 1 };
        const fields = fieldsRaw.split(",").map((n) => Number(n) - 1);
        let lines: string[] = [];
        if (files.length === 0) {
          lines = [...stdin];
        } else {
          for (const file of files) {
            const target = resolvePath(currentCwd, file);
            const node = target ? getNode(fsRef.current, target) : null;
            if (!node || node.type !== "file") return { output: [error(`cut: ${file}: No such file or directory`)], cwd: currentCwd, exitCode: 1 };
            lines.push(...node.content.split("\n"));
          }
        }
        const out = lines.map((line) => {
          const parts = line.split(delim);
          return fields.map((idx) => parts[idx] ?? "").join(delim);
        });
        return { output: ok(out), cwd: currentCwd, exitCode: 0 };
      }

      case "tr": {
        if (args.length < 2) return { output: [error("tr: missing operand")], cwd: currentCwd, exitCode: 1 };
        const from = args[0];
        const to = args[1];
        const mapChar = (ch: string) => {
          const idx = from.indexOf(ch);
          if (idx === -1) return ch;
          return to[idx] ?? to[to.length - 1] ?? "";
        };
        const lines = stdin.map((line) => line.split("").map(mapChar).join(""));
        return { output: ok(lines), cwd: currentCwd, exitCode: 0 };
      }

      case "sed": {
        const expr = args[0];
        if (!expr) return { output: [error("sed: missing expression")], cwd: currentCwd, exitCode: 1 };
        const match = expr.match(/^s(.)(.*)\1(.*)\1([gim]*)$/);
        if (!match) return { output: [error("sed: invalid expression")], cwd: currentCwd, exitCode: 1 };
        const [, , pattern, replacement, flags] = match;
        let regex: RegExp;
        try {
          const reFlags = flags.includes("g") ? "g" : "";
          regex = new RegExp(pattern, reFlags);
        } catch {
          return { output: [error("sed: invalid regex")], cwd: currentCwd, exitCode: 1 };
        }
        const lines = stdin.map((line) => line.replace(regex, replacement));
        return { output: ok(lines), cwd: currentCwd, exitCode: 0 };
      }

      case "history": {
        const lines = cmdHistory.map((cmdLine, idx) => `${String(idx + 1).padStart(4, " ")}  ${cmdLine}`);
        return { output: ok(lines), cwd: currentCwd, exitCode: 0 };
      }

      case "alias": {
        if (args.length === 0) {
          const lines = Object.entries(aliases).map(([name, value]) => `alias ${name}='${value}'`);
          return { output: ok(lines), cwd: currentCwd, exitCode: 0 };
        }
        const assignment = args.join(" ").trim();
        const eqIdx = assignment.indexOf("=");
        if (eqIdx === -1) return { output: [error("alias: invalid assignment")], cwd: currentCwd, exitCode: 1 };
        const name = assignment.slice(0, eqIdx).trim();
        let value = assignment.slice(eqIdx + 1).trim();
        if (!name) return { output: [error("alias: invalid name")], cwd: currentCwd, exitCode: 1 };
        value = value.replace(/^['"]|['"]$/g, "");
        aliases[name] = value;
        return { output: [], cwd: currentCwd, exitCode: 0 };
      }

      case "unalias": {
        if (!args[0]) return { output: [error("unalias: usage: unalias name")], cwd: currentCwd, exitCode: 1 };
        delete aliases[args[0]];
        return { output: [], cwd: currentCwd, exitCode: 0 };
      }

      case "export": {
        if (args.length === 0) {
          const lines = Object.keys(env)
            .sort()
            .map((key) => `export ${key}="${env[key]}"`);
          return { output: ok(lines), cwd: currentCwd, exitCode: 0 };
        }
        for (const arg of args) {
          const [key, ...rest] = arg.split("=");
          if (!isValidVarName(key)) continue;
          if (rest.length === 0) {
            env[key] = env[key] ?? "";
          } else {
            env[key] = rest.join("=");
          }
        }
        return { output: [], cwd: currentCwd, exitCode: 0 };
      }

      case "unset": {
        for (const arg of args) {
          delete env[arg];
        }
        return { output: [], cwd: currentCwd, exitCode: 0 };
      }

      case "env":
      case "printenv": {
        const lines = Object.keys(env)
          .sort()
          .map((key) => `${key}=${env[key]}`);
        return { output: ok(lines), cwd: currentCwd, exitCode: 0 };
      }

      case "which":
      case "type": {
        if (!args[0]) return { output: [error(`${cmd}: missing operand`)], cwd: currentCwd, exitCode: 1 };
        const out: OutputLine[] = [];
        for (const name of args) {
          if (aliases[name]) {
            out.push({ text: `${name} is aliased to '${aliases[name]}'`, cls: "text-zinc-300" });
            continue;
          }
          if (COMMAND_LIST.includes(name)) {
            out.push({ text: `/usr/bin/${name}`, cls: "text-zinc-300" });
            continue;
          }
          out.push(error(`${name} not found`));
        }
        return { output: out, cwd: currentCwd, exitCode: out.some((l) => l.cls === "text-red-400") ? 1 : 0 };
      }

      case "file": {
        if (!args[0]) return { output: [error("file: missing operand")], cwd: currentCwd, exitCode: 1 };
        const target = resolvePath(currentCwd, args[0]);
        if (!target) return { output: [error(`file: cannot open '${args[0]}'`)], cwd: currentCwd, exitCode: 1 };
        const node = getNode(fsRef.current, target);
        if (!node) return { output: [error(`file: cannot open '${args[0]}'`)], cwd: currentCwd, exitCode: 1 };
        if (node.type === "dir") return { output: ok([`${args[0]}: directory`]), cwd: currentCwd, exitCode: 0 };
        const hint = args[0].endsWith(".json") ? "JSON text data" : "ASCII text";
        return { output: ok([`${args[0]}: ${hint}`]), cwd: currentCwd, exitCode: 0 };
      }

      case "uname": {
        return { output: ok(["Linux tbd-dev 6.2.0-rc1 x86_64 GNU/Linux"]), cwd: currentCwd, exitCode: 0 };
      }

      case "hostname": {
        return { output: ok(["tbd-dev"]), cwd: currentCwd, exitCode: 0 };
      }

      case "uptime": {
        return { output: ok([" 10:24:18 up 5 days,  3:12,  1 user,  load average: 0.12, 0.08, 0.03"]), cwd: currentCwd, exitCode: 0 };
      }

      case "ps": {
        return {
          output: ok([
            "USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND",
            "developer  101  0.0  0.1  53284  4120 pts/0    S+   09:12   0:00 bash",
            "developer  202  0.1  0.3 158420 12400 pts/0    Sl   09:12   0:01 node dev-server",
          ]),
          cwd: currentCwd,
          exitCode: 0,
        };
      }

      case "df": {
        if (args.includes("-h")) {
          return {
            output: ok([
              "Filesystem      Size  Used Avail Use% Mounted on",
              "/dev/sda1        64G   12G   49G  20% /",
              "tmpfs           1.9G     0  1.9G   0% /dev/shm",
            ]),
            cwd: currentCwd,
            exitCode: 0,
          };
        }
        return { output: ok(["Filesystem 1K-blocks Used Available Use% Mounted on", "/dev/sda1 67108864 12582912 51407232 20% /"]), cwd: currentCwd, exitCode: 0 };
      }

      case "free": {
        return {
          output: ok([
            "              total        used        free      shared  buff/cache   available",
            "Mem:           3.8Gi       1.2Gi       1.4Gi       128Mi       1.2Gi       2.3Gi",
            "Swap:          2.0Gi          0B       2.0Gi",
          ]),
          cwd: currentCwd,
          exitCode: 0,
        };
      }

      case "ip":
      case "ifconfig": {
        return {
          output: ok([
            "eth0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500",
            "        inet 192.168.1.42  netmask 255.255.255.0  broadcast 192.168.1.255",
            "        ether 02:42:ac:11:00:02  txqueuelen 1000  (Ethernet)",
          ]),
          cwd: currentCwd,
          exitCode: 0,
        };
      }

      case "netstat": {
        return {
          output: ok([
            "Active Internet connections (w/o servers)",
            "Proto Recv-Q Send-Q Local Address           Foreign Address         State",
            "tcp        0      0 192.168.1.42:5173      93.184.216.34:https     ESTABLISHED",
          ]),
          cwd: currentCwd,
          exitCode: 0,
        };
      }

      case "ping": {
        const host = args[0] ?? "localhost";
        return {
          output: ok([
            `PING ${host} (93.184.216.34) 56(84) bytes of data.`,
            `64 bytes from ${host}: icmp_seq=1 ttl=56 time=10.2 ms`,
            `64 bytes from ${host}: icmp_seq=2 ttl=56 time=11.0 ms`,
            `64 bytes from ${host}: icmp_seq=3 ttl=56 time=9.8 ms`,
            `--- ${host} ping statistics ---`,
            `3 packets transmitted, 3 received, 0% packet loss, time 2002ms`,
          ]),
          cwd: currentCwd,
          exitCode: 0,
        };
      }

      case "curl": {
        const url = args.find((a) => a.startsWith("http")) ?? "https://example.com";
        if (args.includes("-I") || args.includes("-sI")) {
          return {
            output: ok([
              `HTTP/1.1 200 OK`,
              `content-type: text/html; charset=UTF-8`,
              `server: demo`,
              `date: ${new Date().toUTCString()}`,
            ]),
            cwd: currentCwd,
            exitCode: 0,
          };
        }
        return {
          output: ok([
            `<!doctype html>`,
            `<html>`,
            `<head><title>${url}</title></head>`,
            `<body>demo response</body>`,
            `</html>`,
          ]),
          cwd: currentCwd,
          exitCode: 0,
        };
      }

      case "wget": {
        const url = args[0] ?? "https://example.com";
        return {
          output: ok([
            `--${new Date().toUTCString()}--  ${url}`,
            `Resolving ${url.replace("https://", "")}... 93.184.216.34`,
            `Connecting to ${url.replace("https://", "")}... connected.`,
            `HTTP request sent, awaiting response... 200 OK`,
            `Length: 1256 (1.2K) [text/html]`,
            `Saving to: 'index.html'`,
            ``,
            `index.html            100%[===================>]   1.23K  --.-KB/s    in 0s`,
          ]),
          cwd: currentCwd,
          exitCode: 0,
        };
      }

      case "ssh": {
        const host = args[0] ?? "unknown";
        return { output: [error(`ssh: connect to host ${host} port 22: Connection refused`)], cwd: currentCwd, exitCode: 255 };
      }

      case "git": {
        const sub = args[0] ?? "status";
        if (sub === "status") {
          return {
            output: ok([
              "On branch main",
              "Your branch is up to date with 'origin/main'.",
              "nothing to commit, working tree clean",
            ]),
            cwd: currentCwd,
            exitCode: 0,
          };
        }
        if (sub === "log") {
          return {
            output: ok([
              "commit b2d4e6f (HEAD -> main)",
              "Author: Developer <dev@example.com>",
              "Date:   Thu May 9 10:11:12 2024 +0000",
              "",
              "    feat: initial portfolio",
            ]),
            cwd: currentCwd,
            exitCode: 0,
          };
        }
        if (sub === "branch") {
          return { output: ok(["* main"]), cwd: currentCwd, exitCode: 0 };
        }
        if (sub === "diff") {
          return { output: ok([""], "text-zinc-400"), cwd: currentCwd, exitCode: 0 };
        }
        if (sub === "add" || sub === "commit" || sub === "push" || sub === "pull") {
          return { output: ok(["(demo) command acknowledged"]), cwd: currentCwd, exitCode: 0 };
        }
        if (sub === "clone") {
          const repo = args[1] ?? "repo";
          return { output: ok([`Cloning into '${repo.split("/").pop()}'...`, "done."]), cwd: currentCwd, exitCode: 0 };
        }
        if (sub === "init") {
          return { output: ok(["Initialized empty Git repository in .git/"]), cwd: currentCwd, exitCode: 0 };
        }
        if (sub === "remote") {
          return { output: ok(["origin\thttps://github.com/user/portfolio.git (fetch)", "origin\thttps://github.com/user/portfolio.git (push)"]), cwd: currentCwd, exitCode: 0 };
        }
        return { output: ok([`git: '${sub}' not implemented in demo`], "text-zinc-400"), cwd: currentCwd, exitCode: 0 };
      }

      case "npm": {
        const sub = args[0];
        if (sub === "install") return { output: ok(["added 42 packages in 2.1s"]), cwd: currentCwd, exitCode: 0 };
        if (sub === "run" && args[1] === "dev") {
          return { output: ok(["VITE v5.0.0  ready in 124ms", "", "  ➜  Local:   http://localhost:5173/", "  ➜  Network: http://192.168.1.42:5173/"]), cwd: currentCwd, exitCode: 0 };
        }
        if (sub === "run" && args[1] === "build") {
          return { output: ok(["vite v5.0.0 building for production...", "dist/index.html  1.2 kB", "✓ built in 1.1s"]), cwd: currentCwd, exitCode: 0 };
        }
        if (sub === "test") return { output: ok(["0 failing"], "text-zinc-400"), cwd: currentCwd, exitCode: 0 };
        if (sub === "audit") return { output: ok(["found 0 vulnerabilities"], "text-zinc-400"), cwd: currentCwd, exitCode: 0 };
        return { output: ok(["npm: try 'npm install' or 'npm run dev'"], "text-zinc-400"), cwd: currentCwd, exitCode: 0 };
      }

      case "npx": {
        const pkg = args[0] ?? "pkg";
        return { output: ok([`npx: installed 1 in 1.1s`, `running ${pkg}...`]), cwd: currentCwd, exitCode: 0 };
      }

      case "node": {
        if (args[0] === "-e") {
          return { output: ok(["(demo) node -e executed"], "text-zinc-400"), cwd: currentCwd, exitCode: 0 };
        }
        return { output: ok(["Node.js v20.0.0 (demo)", "> this is a demo runtime"], "text-zinc-400"), cwd: currentCwd, exitCode: 0 };
      }

      case "python":
      case "python3": {
        return { output: ok(["Python 3.12.0 (demo)", ">>> this is a demo runtime"], "text-zinc-400"), cwd: currentCwd, exitCode: 0 };
      }

      case "make": {
        return { output: [error("make: *** No targets specified and no makefile found.  Stop.")], cwd: currentCwd, exitCode: 2 };
      }

      case "docker": {
        const sub = args[0] ?? "ps";
        if (sub === "ps") {
          return { output: ok(["CONTAINER ID   IMAGE     COMMAND   STATUS    PORTS   NAMES"]), cwd: currentCwd, exitCode: 0 };
        }
        if (sub === "images") {
          return { output: ok(["REPOSITORY   TAG       IMAGE ID       CREATED        SIZE"]), cwd: currentCwd, exitCode: 0 };
        }
        return { output: ok([`docker ${sub}: command not executed in demo`], "text-zinc-400"), cwd: currentCwd, exitCode: 0 };
      }

      case "sleep": {
        return { output: [], cwd: currentCwd, exitCode: 0 };
      }

      case "true": {
        return { output: [], cwd: currentCwd, exitCode: 0 };
      }

      case "false": {
        return { output: [], cwd: currentCwd, exitCode: 1 };
      }

      case "yes": {
        const word = args[0] ?? "y";
        const lines = Array.from({ length: 25 }, () => word);
        return { output: ok(lines), cwd: currentCwd, exitCode: 0 };
      }

      case "seq": {
        const start = args.length >= 2 ? Number(args[0]) : 1;
        const end = args.length >= 2 ? Number(args[1]) : Number(args[0] ?? 1);
        if (Number.isNaN(start) || Number.isNaN(end)) return { output: [error("seq: invalid range")], cwd: currentCwd, exitCode: 1 };
        const lines: string[] = [];
        const step = start <= end ? 1 : -1;
        for (let i = start; step > 0 ? i <= end : i >= end; i += step) lines.push(String(i));
        return { output: ok(lines), cwd: currentCwd, exitCode: 0 };
      }

      case "factor": {
        const n = Number(args[0]);
        if (!args[0] || Number.isNaN(n)) return { output: [error("factor: invalid number")], cwd: currentCwd, exitCode: 1 };
        let value = n;
        const factors: number[] = [];
        let divisor = 2;
        while (value > 1 && divisor <= value) {
          while (value % divisor === 0) {
            factors.push(divisor);
            value /= divisor;
          }
          divisor++;
        }
        return { output: ok([`${n}: ${factors.join(" ")}`]), cwd: currentCwd, exitCode: 0 };
      }

      case "bc":
      case "expr": {
        const expr = args.join(" ");
        const result = safeEvalMath(expr);
        if (!result) return { output: [error(`${cmd}: invalid expression`)], cwd: currentCwd, exitCode: 1 };
        return { output: ok([result]), cwd: currentCwd, exitCode: 0 };
      }

      case "cal": {
        return { output: ok(formatCalendar()), cwd: currentCwd, exitCode: 0 };
      }

      case "man": {
        const topic = args[0];
        if (!topic) return { output: [error("man: missing manual page")], cwd: currentCwd, exitCode: 1 };
        if (topic === "ls") {
          return { output: ok(["LS(1)", "NAME", "  ls - list directory contents", "SYNOPSIS", "  ls [OPTION]... [FILE]..."]), cwd: currentCwd, exitCode: 0 };
        }
        return { output: ok([`No manual entry for ${topic}`], "text-zinc-400"), cwd: currentCwd, exitCode: 0 };
      }

      case "apropos": {
        const term = args[0];
        if (!term) return { output: [error("apropos: missing keyword")], cwd: currentCwd, exitCode: 1 };
        const matches = HELP_LINES.flatMap((line) => line.split(": ")[1]?.split(", ") ?? []).filter((cmdName) => cmdName.includes(term));
        if (matches.length === 0) return { output: ok(["nothing appropriate"], "text-zinc-400"), cwd: currentCwd, exitCode: 0 };
        return { output: ok(matches.map((m) => `${m} - demo command`)), cwd: currentCwd, exitCode: 0 };
      }

      case "fortune": {
        const fortunes = [
          "Build small. Ship fast.",
          "Write tests for the edge cases.",
          "Keep latency low and feedback fast.",
          "Make it work, then make it right.",
        ];
        const pick = fortunes[Math.floor(Math.random() * fortunes.length)];
        return { output: ok([pick]), cwd: currentCwd, exitCode: 0 };
      }

      case "cowsay": {
        return { output: ok(cowsay(args.join(" "))), cwd: currentCwd, exitCode: 0 };
      }

      case "sl": {
        return {
          output: ok([
            "     ====        ________                ___________ ",
            " _D _|  |_______/        \\__I_I_____===__|_________| ",
            "  |(_)---  |   H\\________/ |   |        =|___ ___|   ",
            "  /     |  |   H  |  |     |   |         ||_| |_||    ",
            " |      |  |   H  |__--------------------| [___] |    ",
          ]),
          cwd: currentCwd,
          exitCode: 0,
        };
      }

      case "exit": {
        return { output: ok(["logout", "Connection to demo closed."]), cwd: currentCwd, exitCode: 0 };
      }

      default: {
        return { output: [error(`command not found: ${cmd}`)], cwd: currentCwd, exitCode: 127 };
      }
    }
  };

  const runShell = useCallback(
    (input: string): CommandResult => {
      const tokens = tokenize(input);
      const env = { ...envRef.current, PWD: toAbsolute(cwd) };
      const aliases = { ...aliasRef.current };
      let currentCwd = cwd;
      let lastStatus = lastStatusRef.current;

      if (tokens.length === 0) return { output: [], cwd: currentCwd, exitCode: 0 };

      const expandedTokens = tokens.map((t) => expandToken(t, env, lastStatus, currentCwd));
      const sequences = splitByOperator(expandedTokens, ";");

      const allOutput: OutputLine[] = [];
      let exitCode = 0;
      let shouldClear = false;

      for (const sequence of sequences) {
        const andSegments = splitByOperator(sequence, "&&");
        for (const segment of andSegments) {
          if (segment.length === 0) continue;
          const pipelineParts = splitByOperator(segment, "|");
          let stdin: string[] = [];
          let pipeExit = 0;
          let localCwd = currentCwd;
          let outputLines: OutputLine[] = [];

          for (let i = 0; i < pipelineParts.length; i++) {
            const part = pipelineParts[i];
            const { tokens: cleanTokens, redirect } = parseRedirection(part);
            let tokensToRun = cleanTokens;

            if (tokensToRun.length && aliases[tokensToRun[0]]) {
              const aliasTokens = tokenizeAlias(aliases[tokensToRun[0]]);
              tokensToRun = [...aliasTokens, ...tokensToRun.slice(1)];
            }

            const result = runCommandTokens(tokensToRun, stdin, localCwd, env, aliases);
            localCwd = result.cwd;
            pipeExit = result.exitCode;
            outputLines = result.output;
            if (result.clear) {
              shouldClear = true;
              outputLines = [];
            }

            if (redirect && i === pipelineParts.length - 1) {
              const targetPath = resolvePath(localCwd, redirect.path);
              if (!targetPath) {
                outputLines = [{ text: `redirect: cannot write '${redirect.path}'`, cls: "text-red-400" }];
                pipeExit = 1;
              } else {
                const content = outputLines.map((l) => l.text).join("\n") + "\n";
                const err = writeFile(fsRef.current, targetPath, content, redirect.append);
                if (err) {
                  outputLines = [{ text: `redirect: ${err}`, cls: "text-red-400" }];
                  pipeExit = 1;
                } else {
                  outputLines = [];
                  pipeExit = 0;
                }
              }
            }

            stdin = outputLines.map((l) => l.text);
            if (pipeExit !== 0 && i < pipelineParts.length - 1) {
              break;
            }
          }

          currentCwd = localCwd;
          exitCode = pipeExit;
          if (outputLines.length) {
            allOutput.push(...outputLines);
          }

          if (exitCode !== 0) break;
        }
      }

      envRef.current = { ...env, PWD: toAbsolute(currentCwd) };
      aliasRef.current = aliases;
      lastStatusRef.current = exitCode;
      return { output: limitOutput(allOutput), cwd: currentCwd, exitCode, clear: shouldClear };
    },
    [cwd, cmdHistory]
  );

  const handleCommand = useCallback(
    (input: string) => {
      const trimmed = input.trim();
      if (!trimmed) return;

      const result = runShell(trimmed);

      const newLines: TermLine[] = [
        { text: `${shortCwd(cwd)} $ ${trimmed}`, isPrompt: true },
        ...result.output.map((line) => ({ text: line.text, cls: line.cls })),
      ];

      if (result.clear) {
        setHistory([]);
      } else {
        setHistory((h) => [...h, ...newLines]);
      }

      setCwd(result.cwd);
      setInputValue("");
      setCmdHistory((h) => [...h, trimmed]);
      setHistoryIndex(-1);
    },
    [cwd, runShell]
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
    } else if (e.key === "Tab") {
      e.preventDefault();
      const input = inputValue;
      const cursor = inputRef.current?.selectionStart ?? input.length;
      if (cursor !== input.length) return;
      const before = input.slice(0, cursor);
      const parts = before.split(/\s+/);
      const last = parts[parts.length - 1] ?? "";
      const hasCommand = parts.length > 1 || before.endsWith(" ");

      if (!hasCommand) {
        const candidates = getCommandCandidates(aliasRef.current).filter((c) => c.startsWith(last));
        if (candidates.length === 1) {
          setInputValue(candidates[0] + " ");
        } else if (candidates.length > 1) {
          setHistory((h) => [...h, ...candidates.map((c) => ({ text: c, cls: "text-zinc-400" }))]);
        }
        return;
      }

      const pathToken = last;
      const dirPart = pathToken.includes("/") ? pathToken.slice(0, pathToken.lastIndexOf("/") + 1) : "";
      const basePart = pathToken.includes("/") ? pathToken.slice(pathToken.lastIndexOf("/") + 1) : pathToken;
      const searchPath = resolvePath(cwd, dirPart || ".") ?? cwd;
      const dirNode = getNode(fsRef.current, searchPath);
      if (!dirNode || dirNode.type !== "dir") return;
      const matches = listEntries(dirNode, false)
        .map(([name, node]) => (node.type === "dir" ? `${name}/` : name))
        .filter((name) => name.startsWith(basePart));
      if (matches.length === 1) {
        const completed = `${dirPart}${matches[0]}`;
        parts[parts.length - 1] = completed;
        setInputValue(parts.join(" "));
      } else if (matches.length > 1) {
        setHistory((h) => [...h, { text: matches.join("  "), cls: "text-zinc-400" }]);
      }
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
        <div className="flex items-center px-4 py-3 border-b border-[var(--landing-border)]">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-[#ff5f57]" />
            <div className="w-3 h-3 rounded-full bg-[#febc2e]" />
            <div className="w-3 h-3 rounded-full bg-[#28c840]" />
          </div>
          <div className="flex-1 text-center">
            <span className="text-[12px] text-zinc-500 font-mono">~/projects/portfolio</span>
          </div>
          <div className="w-[52px]" />
        </div>

        <div ref={scrollRef} className="px-5 py-4 font-mono text-[13px] leading-relaxed h-[420px] overflow-y-auto cursor-text">
          {phase !== "interactive" && (
            <>
              <div>
                <span className="text-brand-500">{promptCwd} $</span>{" "}
                <span className="text-zinc-200">{DEMO_COMMAND.slice(0, typedChars)}</span>
                {(phase === "typing" || phase === "wait") && <span className="terminal-cursor" />}
              </div>

              {ALL_DEMO_LINES.slice(0, visibleLines).map((line, i) => (
                <div key={i} className={`terminal-line ${line.cls} ${line.gap ? "mt-3" : ""}`}>
                  {"  "}
                  {line.text}
                </div>
              ))}

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

          {phase === "interactive" && (
            <>
              <div>
                <span className="text-brand-500">{promptCwd} $</span>{" "}
                <span className="text-zinc-200">{DEMO_COMMAND}</span>
              </div>
              {ALL_DEMO_LINES.map((line, i) => (
                <div key={`d-${i}`} className={`${line.cls} ${line.gap ? "mt-3" : ""}`}>
                  {"  "}
                  {line.text}
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

              {history.map((line, i) => (
                <div
                  key={i}
                  className={`${line.isPrompt ? "" : line.cls ?? "text-zinc-300"} ${line.gap ? "mt-3" : ""} whitespace-pre-wrap break-all`}
                >
                  {line.isPrompt ? (
                    <>
                      <span className="text-brand-500">{line.text.split(" $ ")[0]} $</span>{" "}
                      <span className="text-zinc-200">{line.text.split(" $ ").slice(1).join(" $ ")}</span>
                    </>
                  ) : (
                    line.text
                  )}
                </div>
              ))}

              <div className="flex items-center">
                <span className="text-brand-500 shrink-0">{shortCwd(cwd)} $</span>
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
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: "radial-gradient(ellipse 80% 50% at 50% -20%, rgba(0,214,143,0.07), transparent)",
        }}
      />

      <nav className="relative z-10 flex items-center justify-between px-6 py-4 max-w-5xl mx-auto w-full">
        <Link href="/" className="font-mono text-lg font-bold tracking-tight text-brand-500">
          tbd
        </Link>

        <Link href="/login" className="text-sm text-zinc-400 hover:text-zinc-200 transition-colors">
          Sign in
        </Link>
      </nav>

      <main className="relative z-10 flex-1 flex flex-col items-center justify-center px-6 -mt-4">
        <h1 className="text-[clamp(1.75rem,4.5vw,3rem)] font-bold tracking-tight leading-[1.2] text-center">
          <span className="text-white">Push to GitHub.</span>
          <br />
          <span className="text-zinc-500">Auto Build.</span>
          <br />
          <span className="text-brand-500">Deployed @ dev.sdc.cpp</span>
        </h1>

        <div className="mt-8 sm:mt-10 w-full max-w-2xl">
          <TerminalDemo />
        </div>
      </main>

      <footer className="relative z-10 px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <span className="text-xs text-zinc-700 font-mono">tbd</span>
          <span className="text-xs text-zinc-700">&copy; {new Date().getFullYear()} SDC</span>
        </div>
      </footer>
    </div>
  );
}
