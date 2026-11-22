import type { ReactNode } from "react";
import { AuthProvider } from "@/components/layout/AuthProvider";
import { Shell } from "@/components/layout/Shell";

export default function ConsoleLayout({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <Shell>{children}</Shell>
    </AuthProvider>
  );
}
