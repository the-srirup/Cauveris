"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  {
    href: "/",
    label: "Mission Control",
    icon: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9.75 17 9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2Z"
      />
    ),
  },
  {
    href: "/reality-rewind",
    label: "Reality Rewind",
    icon: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 8v4l3 3m6-3a9 9 0 1 1-2.64-6.36M17.25 2h.01"
      />
    ),
  },
  {
    href: "/causal-constellation",
    label: "Causal Constellation",
    icon: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M6 6h.01M6 18h.01M18 6h.01M18 18h.01M12 12l-3.5-6M12 12 8.5 18M12 12h6M12 12H6"
      />
    ),
  },
  {
    href: "/ghost-lab",
    label: "Ghost Lab",
    icon: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9.75 3.104A6.75 6.75 0 0 1 21.75 9.9M21.75 21v-2.25M3.75 21v-2.25M12 21v-3a3 3 0 0 0-3-3h-1.5a3 3 0 0 1-3-3V8.25A6.75 6.75 0 0 1 11.25 1.5h1.5"
      />
    ),
  },
  {
    href: "/patch-forge",
    label: "Patch Forge",
    icon: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 0 0 4.486-6.336l-3.276 3.277a3 3 0 0 1-2.25.881l-2.85-.475m2.34-2.346.475 2.85M11.42 15.17l6.155-5.024"
      />
    ),
  },
  {
    href: "/victory-replay",
    label: "Victory Replay",
    icon: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10"
      />
    ),
  },
  {
    href: "/evidence-vault",
    label: "Evidence Vault",
    icon: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M16.5 10.5V7.5a4.5 4.5 0 1 0-9 0v3m-3-3h15v12a.75.75 0 0 1-.75.75h-13.5a.75.75 0 0 1-.75-.75v-12Z"
      />
    ),
  },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-white/5 bg-surface/60 backdrop-blur-xl">
      {/* Brand */}
      <div className="flex items-center gap-3 px-6 py-6">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/15 ring-1 ring-primary/30">
          <svg
            className="h-5 w-5 text-primary"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M13 10V3L4 14h7v7l9-11h-7Z"
            />
          </svg>
        </div>
        <div className="leading-tight">
          <div className="text-sm font-bold tracking-wide text-white">
            Cauveris
          </div>
          <div className="text-[10px] uppercase tracking-widest text-muted">
            Reality Debugger
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-3 py-2">
        <div className="mb-3 px-3 text-[10px] font-medium uppercase tracking-widest text-muted">
          Investigation
        </div>
        <ul className="space-y-1">
          {NAV.map((item) => {
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname?.startsWith(item.href);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={`group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all ${
                    active
                      ? "bg-primary/10 text-primary"
                      : "text-muted hover:bg-white/5 hover:text-white"
                  }`}
                >
                  {active && (
                    <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r bg-primary" />
                  )}
                  <svg
                    className={`h-5 w-5 transition-colors ${
                      active ? "text-primary" : "text-muted group-hover:text-white"
                    }`}
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={1.5}
                    viewBox="0 0 24 24"
                  >
                    {item.icon}
                  </svg>
                  <span>{item.label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Footer */}
      <div className="border-t border-white/5 px-6 py-4">
        <div className="flex items-center gap-2 text-xs text-muted">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-success" />
          </span>
          Systems Nominal
        </div>
      </div>
    </aside>
  );
}