import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "My App",
  description: "Deployed on TBD",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-zinc-950 text-zinc-100 antialiased">{children}</body>
    </html>
  );
}
