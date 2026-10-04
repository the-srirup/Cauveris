"use client";

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Menu, X, LogOut, User, Settings, Shield, ChevronDown } from 'lucide-react';
import { useAuthStore } from '@/lib/auth';
import { Badge } from './ui';
import { Tooltip } from './Tooltip';

const userMenuStyles = {
  trigger: `
    flex items-center gap-2 px-3 py-1.5 rounded-lg
    bg-[var(--color-surface)] border border-[var(--color-border)] hover:bg-[var(--color-surface-2)]
    transition-all duration-150
  `,
  dropdown: `
    absolute right-0 top-full mt-2 w-56 origin-top-right
    bg-[var(--theme-background)] border border-[var(--color-border)] rounded-lg shadow-lg
    py-1 z-50 animate-slide-down
  `,
  item: `
    flex items-center gap-2 w-full px-3 py-2 text-sm
    text-[var(--color-text-primary)] hover:bg-[var(--color-surface)]
    transition-colors duration-100
  `,
  divider: 'border-t border-[var(--color-border)] my-1',
};

export function UserMenu() {
  const router = useRouter();
  const { user, logout, isAuthenticated } = useAuthStore();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        triggerRef.current &&
        !triggerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const handleLogout = async () => {
    await logout();
    router.push('/login');
    setIsOpen(false);
  };

  if (!isAuthenticated || !user) {
    return (
      <Tooltip content="Sign in to access your account" position="bottom">
        <button onClick={() => router.push('/login')} className={userMenuStyles.trigger}>
          <span className="text-sm font-medium text-[var(--color-text-muted)]">Sign In</span>
          <ChevronDown className="h-3 w-3" />
        </button>
      </Tooltip>
    );
  }

  const roleColors: Record<string, 'neutral' | 'primary' | 'secondary' | 'amber' | 'danger' | 'success'> = {
    viewer: 'neutral',
    analyst: 'primary',
    engineer: 'amber',
    admin: 'danger',
    super_admin: 'success',
  };

  return (
    <div className="relative">
      <Tooltip content={user.email} position="bottom">
        <button
          ref={triggerRef}
          onClick={() => setIsOpen(!isOpen)}
          className={userMenuStyles.trigger}
          aria-label="User menu"
          aria-expanded={isOpen}
          aria-haspopup="true"
        >
          <div className="h-7 w-7 rounded-full bg-[var(--color-brand-primary)]/20 flex items-center justify-center">
            <User className="h-4 w-4 text-[var(--color-brand-primary)]" />
          </div>
          <span className="text-sm font-medium truncate max-w-[120px] hidden sm:block">
            {user.full_name || user.email}
          </span>
          <ChevronDown className={`h-3 w-3 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
        </button>
      </Tooltip>

      {isOpen && (
        <div
          ref={dropdownRef}
          className={userMenuStyles.dropdown}
          role="menu"
          aria-orientation="vertical"
        >
          <div className="px-3 py-2 border-b border-[var(--color-border)]">
            <p className="text-sm font-medium truncate">{user.full_name || user.email}</p>
            <p className="text-xs text-[var(--color-text-muted)] truncate">{user.email}</p>
            <Badge tone={roleColors[user.role] || 'default'} className="mt-1">
              {user.role.replace('_', ' ')}
            </Badge>
          </div>

          <div className="py-1">
            <a
              href="/settings"
              className={userMenuStyles.item}
              role="menuitem"
              onClick={() => setIsOpen(false)}
            >
              <Settings className="h-4 w-4" />
              Settings
            </a>

            <div className={userMenuStyles.divider} />

            {user.role === 'admin' || user.role === 'super_admin' && (
              <a
                href="/admin"
                className={userMenuStyles.item}
                role="menuitem"
                onClick={() => setIsOpen(false)}
              >
                <Shield className="h-4 w-4" />
                Admin Panel
              </a>
            )}

            <div className={userMenuStyles.divider} />

            <button
              onClick={handleLogout}
              className={`${userMenuStyles.item} text-[var(--color-brand-danger)] hover:bg-[var(--color-brand-danger)]/10`}
              role="menuitem"
            >
              <LogOut className="h-4 w-4" />
              Sign Out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}