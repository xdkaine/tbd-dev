import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Your Name — Portfolio",
  description: "Developer portfolio built with Next.js. Scaffolded from a TBD template.",
  openGraph: {
    title: "Your Name — Portfolio",
    description: "Developer portfolio built with Next.js.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="scroll-smooth">
      <head>
        {/* Google Fonts – Inter for body, JetBrains Mono for code */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-zinc-950 text-zinc-100 antialiased">{children}</body>
    </html>
  );
}
