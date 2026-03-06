export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="max-w-2xl text-center">
        <h1 className="text-5xl font-bold tracking-tight">
          Welcome to <span className="text-emerald-400">Your App</span>
        </h1>
        <p className="mt-4 text-lg text-zinc-400">
          This project was scaffolded from a TBD template. Start editing{" "}
          <code className="rounded bg-zinc-800 px-1.5 py-0.5 text-sm text-emerald-400">
            src/app/page.tsx
          </code>{" "}
          to get started.
        </p>
        <div className="mt-8 flex justify-center gap-4">
          <a
            href="https://nextjs.org/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg bg-emerald-500 px-5 py-2.5 text-sm font-medium text-black hover:bg-emerald-400 transition-colors"
          >
            Next.js Docs
          </a>
          <a
            href="https://tailwindcss.com/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg border border-zinc-700 px-5 py-2.5 text-sm font-medium text-zinc-300 hover:bg-zinc-800 transition-colors"
          >
            Tailwind Docs
          </a>
        </div>
      </div>
    </main>
  );
}
