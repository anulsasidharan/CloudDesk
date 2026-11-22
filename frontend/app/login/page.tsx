"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ApiError, NetworkError, api, setToken } from "@/lib/api";
import { Button } from "@/components/ui/Button";

const DEMO_USERS = [
  { email: "sam.agent@clouddesk.demo", label: "Sign in as Agent (Sam)", note: "can run, approve, reply" },
  { email: "vic.viewer@clouddesk.demo", label: "Sign in as Viewer (Vic)", note: "read-only" },
  { email: "admin@clouddesk.demo", label: "Sign in as Admin", note: "everything, plus settings" },
];

const REASONS: Record<string, string> = {
  expired: "Your session expired. Please sign in again.",
  signin: "Please sign in to continue.",
  signed_out: "You have been signed out.",
};

function LoginForm() {
  const reason = useSearchParams().get("reason");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function signIn(email: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await api.login({ email });
      setToken(res.access_token);
      window.location.assign("/dashboard");
    } catch (err) {
      setBusy(false);
      if (err instanceof NetworkError) setError("Cannot reach the API. Is the backend running on port 8000?");
      else if (err instanceof ApiError) setError(err.detail);
      else setError("Sign-in failed");
    }
  }

  return (
    <div className="mx-auto mt-24 max-w-md rounded-lg border border-slate-200 bg-white p-8">
      <h1 className="text-xl font-bold text-brand">CloudDesk</h1>
      <p className="mt-1 text-sm text-slate-500">Support console. Demo mode: pick a user.</p>
      {reason && REASONS[reason] && (
        <p role="status" className="mt-4 rounded bg-amber-50 p-2 text-sm text-amber-800">
          {REASONS[reason]}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-4 rounded bg-red-50 p-2 text-sm text-red-800">
          {error}
        </p>
      )}
      <div className="mt-6 space-y-3">
        {DEMO_USERS.map((u) => (
          <div key={u.email}>
            <Button className="w-full" disabled={busy} onClick={() => signIn(u.email)}>
              {u.label}
            </Button>
            <p className="mt-1 text-center text-xs text-slate-500">{u.note}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
