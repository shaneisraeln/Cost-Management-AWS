"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/costs", label: "Costs" },
  { href: "/resources", label: "Resources" },
  { href: "/people", label: "People" },
  { href: "/projects", label: "Projects" },
  { href: "/alerts", label: "Alerts" },
  { href: "/timeline", label: "Timeline" },
  { href: "/recommendations", label: "Recommendations" },
  { href: "/github", label: "GitHub" },
  { href: "/bedrock", label: "Bedrock" },
  { href: "/settings/aws", label: "Settings" },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <nav className="w-56 shrink-0 border-r border-white/10 p-4">
      <div className="mb-6 px-2 text-sm font-semibold tracking-wide text-white/70">
        Cloud Cost Control
      </div>
      <ul className="space-y-1">
        {NAV.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                className={`block rounded px-3 py-2 text-sm ${
                  active
                    ? "bg-white/10 text-white"
                    : "text-white/60 hover:bg-white/5 hover:text-white"
                }`}
              >
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
