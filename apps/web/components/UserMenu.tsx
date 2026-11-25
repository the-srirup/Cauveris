"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { LogOut, User, Settings } from "lucide-react";
import { useAuthStore } from "@/lib/auth";
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
          inline-flex items-center justify-center px-3 h-8.5
          rounded-[var(--radius-sm,4px)]
          bg-[var(--color-canvas-muted)]/65 dark:bg-[var(--color-canvas-muted)]
          hover:bg-[var(--color-canvas-muted)] dark:hover:bg-[var(--color-border-default)]
          text-xs font-medium text-[var(--color-fg-default)]
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
        <span>Sign In</span>
      </button>
    );
  }

  const displayName = user.full_name || user.email || "Operator";

  const items: DropdownItem[] = [
    {
      key: "identity",
      label: displayName,
      description: user.email && user.email !== displayName ? user.email : user.role,
      disabled: true,
    },
    { divider: true },
    {
      key: "settings",
      label: "Settings",
      leadingIcon: <Settings className="h-4 w-4" aria-hidden="true" />,
      onClick: () => router.push("/settings"),
    },
    { divider: true },
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
          title={`${displayName}${user.role ? ` • ${user.role}` : ""}`}
          className={`
            inline-flex items-center justify-center h-8.5 w-8.5
            rounded-[var(--radius-sm,4px)]
            bg-[var(--color-canvas-muted)]/65 dark:bg-[var(--color-canvas-muted)]
            hover:bg-[var(--color-canvas-muted)] dark:hover:bg-[var(--color-border-default)]
            transition-colors duration-100
            focus-visible:outline-none
            focus-visible:ring-2
            focus-visible:ring-[var(--color-accent)]
            focus-visible:ring-offset-2
            focus-visible:ring-offset-[var(--color-canvas)]
            shrink-0 select-none
            ${open ? "ring-2 ring-[var(--color-accent)]/60" : ""}
          `}
          aria-label="User menu"
          aria-expanded={open}
          aria-haspopup="true"
        >
          <User className="h-4.5 w-4.5 text-[var(--color-fg-default)]" aria-hidden="true" />
        </button>
      )}
    </Dropdown>
  );
}
