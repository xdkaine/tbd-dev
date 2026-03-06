function App() {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">
      <div className="max-w-xl text-center px-6">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
          Welcome to <span className="text-cyan-400">Your App</span>
        </h1>
        <p className="mt-6 text-lg text-zinc-400">
          Scaffolded from a TBD template. Start building by editing{" "}
          <code className="rounded bg-zinc-800 px-2 py-0.5 text-sm text-zinc-200">
            src/App.tsx
          </code>
        </p>
        <div className="mt-8 flex items-center justify-center gap-6">
          <a
            href="https://react.dev"
            target="_blank"
            rel="noopener noreferrer"
            className="text-cyan-400 hover:text-cyan-300 underline underline-offset-4"
          >
            React Docs
          </a>
          <a
            href="https://vite.dev"
            target="_blank"
            rel="noopener noreferrer"
            className="text-cyan-400 hover:text-cyan-300 underline underline-offset-4"
          >
            Vite Docs
          </a>
        </div>
      </div>
    </div>
  );
}

export default App;
