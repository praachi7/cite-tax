"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// SRS/SDS 3.5 navigation flow, then the question screen.
const STEPS: [string, string][] = [
  ["/", "1 · Persona & upload"],
  ["/review", "2 · Classification review"],
  ["/summary", "3 · Tax summary"],
  ["/compliance", "4 · Compliance checklist"],
  ["/audit", "5 · Audit-risk report"],
  ["/ask", "Ask a question"],
];

export function Nav() {
  const path = usePathname();
  return (
    <nav className="steps" aria-label="Screens">
      {STEPS.map(([href, label]) => (
        <Link key={href} href={href} className={path === href ? "step current" : "step"} aria-current={path === href ? "page" : undefined}>
          {label}
        </Link>
      ))}
    </nav>
  );
}
