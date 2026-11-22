import { render, screen } from "@testing-library/react";
import { EmptyState } from "@/components/ui/EmptyState";
import { StatusPill } from "@/components/ui/StatusPill";
import { NAV_ITEMS } from "@/components/layout/nav";
import { canAct, hasRole, humanize } from "@/lib/format";

describe("StatusPill", () => {
  it("humanizes the value", () => {
    render(<StatusPill value="waiting_on_approval" />);
    expect(screen.getByTestId("status-pill")).toHaveTextContent("Waiting on approval");
  });
  it("renders a dash for null and stays neutral for unknown values", () => {
    render(<StatusPill value={null} />);
    expect(screen.getByTestId("status-pill")).toHaveTextContent("-");
  });
  it("colours critical red", () => {
    render(<StatusPill value="critical" />);
    expect(screen.getByTestId("status-pill").className).toContain("bg-red-100");
  });
});

describe("EmptyState", () => {
  it("shows title, description and action", () => {
    render(<EmptyState title="No tickets" description="Try again" action={<button>Reset</button>} />);
    expect(screen.getByText("No tickets")).toBeInTheDocument();
    expect(screen.getByText("Try again")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reset" })).toBeInTheDocument();
  });
});

describe("role-aware helpers", () => {
  it("viewer cannot act; agent and admin can", () => {
    expect(canAct("viewer")).toBe(false);
    expect(canAct("agent")).toBe(true);
    expect(canAct("admin")).toBe(true);
    expect(canAct(undefined)).toBe(false);
  });
  it("orders roles viewer < agent < admin", () => {
    expect(hasRole("agent", "viewer")).toBe(true);
    expect(hasRole("agent", "admin")).toBe(false);
  });
  it("settings is the only admin-only nav link", () => {
    const adminOnly = NAV_ITEMS.filter((n) => n.minRole === "admin").map((n) => n.href);
    expect(adminOnly).toEqual(["/settings"]);
  });
  it("humanize handles empty", () => {
    expect(humanize(undefined)).toBe("-");
  });
});
