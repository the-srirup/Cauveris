"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { LogOut, User, Settings, Shield, ChevronDown } from "lucide-react";
import { useAuthStore } from "@/lib/auth";
import { Badge } from "./ui";
import { Dropdown, type DropdownItem } from "./ui/Dropdown";

export function UserMenu() {
  const router = useRouter();
  const { user, logout, isAuthenticated } = useAuthStore();
  const [isOpen, setIsOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    router.push("/login");
    setIsOpen(false);
  };

  if (!isAuthenticated || !user) {
    return (
      <button
        onClick={() => router.push("/login")}
        className="
          inline-flex items-center gap-1.5 px-2.5 h-7
          rounded-[var(--radius-sm)]
          bg-[var(--color-canvas-subtle)]
          border border-[var(--color-border-default)]
          hover:bg-[var(--color-border-default)]
          transition-colors duration-100
          focus-visible:outline-none
          focus-visible:ring-2
          focus-visible:ring-[var(--color-accent)]
          focus-visible:ring-offset-2
          focus-visible:ring-offset-[var(--color-canvas)]
          shrink-0 select-none
        "
        aria-label="Sign In"
      >
        <span className="text-xs font-medium text-[var(--color-fg-muted)] hidden sm:inline-flex items-center leading-none">Sign In</span>
        <ChevronDown className="h-3 w-3 text-[var(--color-fg-muted)] shrink-0" aria-hidden="true" />
      </button>
    );
  }

  const roleColors: Record<string, "default" | "primary" | "success" | "danger" | "warning" | "done" | "muted"> = {
    viewer: "muted",
    analyst: "primary",
    engineer: "warning",
    admin: "danger",
    super_admin: "success",
  };

  const items: DropdownItem[] = [
    {
      key: "settings",
      label: "Settings",
      leadingIcon: <Settings className="h-4 w-4" aria-hidden="true" />,
      onClick: () => router.push("/settings"),
    },
    { divider: true },
    ...(user.role === "admin" || user.role === "super_admin"
      ? [
          {
            key: "admin",
            label: "Admin Panel",
            leadingIcon: <Shield className="h-4 w-4" aria-hidden="true" />,
            onClick: () => router.push("/admin"),
          },
          { divider: true },
        ]
      : []),
    {
      key: "logout",
      label: "Sign Out",
      leadingIcon: <LogOut className="h-4 w-4" aria-hidden="true" />,
      danger: true,
      onClick: handleLogout,
    },
  ];

  return (
    <Dropdown
      items={items}
      onSelect={(key, item) => item.onClick?.()}
      align="right"
      open={isOpen}
      onOpenChange={setIsOpen}
      aria-label="User menu"
    >
      {({ open, onClick }: { open: boolean; onClick: () => void }) => (
        <button
          onClick={onClick}
          className="
            inline-flex items-center gap-2 px-2.5 h-7 max-w-[180px]
            rounded-[var(--radius-sm)]
            bg-[var(--color-canvas-subtle)]
            border border-[var(--color-border-default)]
            hover:bg-[var(--color-border-default)]
            transition-colors duration-100
            focus-visible:outline-none
            focus-visible:ring-2
            focus-visible:ring-[var(--color-accent)]
            focus-visible:ring-offset-2
            focus-visible:ring-offset-[var(--color-canvas)]
            shrink-0 select-none
          "
          aria-label="User menu"
          aria-expanded={open}
          aria-haspopup="true"
        >
          <div className="h-4.5 w-4.5 rounded-full bg-[var(--color-accent-muted)] flex items-center justify-center shrink-0">
            <User className="h-3 w-3 text-[var(--color-accent-fg)]" aria-hidden="true" />
          </div>
          <span className="text-xs font-medium truncate max-w-[100px] xl:max-w-[130px] whitespace-nowrap text-[var(--color-fg-default)] hidden sm:inline-flex items-center leading-none">
            {user.full_name || user.email}
          </span>
          <ChevronDown className={`h-3 w-3 text-[var(--color-fg-muted)] shrink-0 transition-transform duration-150 ${open ? "rotate-180" : ""}`} aria-hidden="true" />
        </button>
      )}
    </Dropdown>
  );
}