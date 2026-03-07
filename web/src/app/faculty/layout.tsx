"use client";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/contexts/auth";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function FacultyLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user) {
      // Only Faculty can access faculty routes
      if (user.role !== "JAS-Faculty") {
        router.replace("/dashboard");
      }
    }
  }, [loading, user, router]);

  if (loading) return null;
  if (!user) return null;
  if (user.role !== "JAS-Faculty") return null;

  return <AppShell>{children}</AppShell>;
}
