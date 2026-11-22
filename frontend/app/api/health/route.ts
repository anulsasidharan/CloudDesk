import { NextResponse } from "next/server";

// Container HEALTHCHECK target (Phase 14). No backend call: it only proves Next.js is serving.
export const dynamic = "force-dynamic";

export function GET() {
  return NextResponse.json({ status: "ok", service: "clouddesk-console" });
}
