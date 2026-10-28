"use client";

import { useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuthStore, LoginRequest, RegisterRequest } from '@/lib/auth';
import { Button, Input, Card } from '@/components/ui';
import { Mail, Lock, User, AlertCircle, Loader2, Eye, EyeOff } from 'lucide-react';
import { NotificationContainer } from '@/components/Notification';

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, register, isLoading, error, clearError } = useAuthStore();
  const [isRegister, setIsRegister] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  interface FormDataState {
    email: string;
    password: string;
    confirm_password?: string;
    remember_me: boolean;
    full_name: string;
    org_name: string;
    org_slug: string;
    mfa_code: string;
  }

  const [formData, setFormData] = useState<FormDataState>({
    email: '',
    password: '',
    confirm_password: '',
    remember_me: true,
    full_name: '',
    org_name: '',
    org_slug: '',
    mfa_code: '',
  });

  const redirectTo = searchParams.get('redirect') || '/';

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, type } = e.target;
    if (type === 'checkbox') {
      setFormData(prev => ({ ...prev, [name]: e.target.checked }));
    } else {
      setFormData(prev => ({ ...prev, [name]: value }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearError();

    if (isRegister && formData.confirm_password && formData.password !== formData.confirm_password) {
      alert("Passwords do not match");
      return;
    }

    try {
      if (isRegister) {
        await register({
          email: formData.email,
          password: formData.password,
          full_name: formData.full_name,
          org_name: formData.org_name || undefined,
          org_slug: formData.org_slug || undefined,
        });
      } else {
        const loginData: LoginRequest = {
          email: formData.email,
          password: formData.password,
          remember_me: formData.remember_me || false,
          mfa_code: formData.mfa_code || undefined,
        };
        await login(loginData);
      }
      router.push(redirectTo);
      router.refresh();
    } catch {
      // Error handled in auth store
    }
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center p-4 bg-[var(--color-canvas)] font-sans">
      <NotificationContainer />

      <div className="w-full max-w-md space-y-4">
        {/* Brand Header */}
        <div className="flex flex-col items-center text-center space-y-1">
          <div className="flex h-11 w-11 items-center justify-center rounded-[var(--radius-lg,8px)] bg-[var(--color-accent-emphasis,#1f6feb)] text-white shadow-xs">
            <svg className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth={2.4} viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7Z" />
            </svg>
          </div>
          <h1 className="text-xl font-bold tracking-tight text-[var(--color-fg-default)] pt-2">
            Cauveris
          </h1>
          <p className="text-xs text-[var(--color-fg-muted)]">
            Incident Engineering & Autonomous System Repair
          </p>
        </div>

        <Card className="border border-[var(--color-border-default)] shadow-md bg-[var(--color-canvas-inset)]">
          <div className="pb-3 border-b border-[var(--color-border-default)] mb-4">
            <h2 className="text-base font-semibold text-[var(--color-fg-default)]">
              {isRegister ? "Create an Operator Account" : "Operator Sign In"}
            </h2>
            <p className="text-xs text-[var(--color-fg-muted)] mt-0.5">
              {isRegister
                ? "Enter your details to create an engineering workstation account"
                : "Enter your registered credentials to access the workbench"}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3.5">
            {error && (
              <div className="flex items-center gap-2 p-2.5 rounded-[var(--radius-md,6px)] bg-[var(--color-danger-muted)] border border-[var(--color-danger-emphasis)]/30 text-[var(--color-danger-fg)] text-xs">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {isRegister && (
              <div className="space-y-1">
                <label htmlFor="full_name" className="block text-xs font-medium text-[var(--color-fg-default)]">
                  Full Name
                </label>
                <div className="relative">
                  <User className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--color-fg-muted)]" />
                  <Input
                    id="full_name"
                    name="full_name"
                    type="text"
                    value={formData.full_name}
                    onChange={handleInputChange}
                    placeholder="Engineering Specialist"
                    className="pl-8 text-xs h-8"
                    required={isRegister}
                    disabled={isLoading}
                    autoComplete="name"
                  />
                </div>
              </div>
            )}

            <div className="space-y-1">
              <label htmlFor="email" className="block text-xs font-medium text-[var(--color-fg-default)]">
                Email Address
              </label>
              <div className="relative">
                <Mail className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--color-fg-muted)]" />
                <Input
                  id="email"
                  name="email"
                  type="email"
                  value={formData.email}
                  onChange={handleInputChange}
                  placeholder="operator@organization.com"
                  className="pl-8 text-xs h-8 font-mono"
                  required
                  disabled={isLoading}
                  autoComplete="email"
                />
              </div>
            </div>

            {isRegister && (
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <label htmlFor="org_name" className="block text-xs font-medium text-[var(--color-fg-default)]">
                    Organization
                  </label>
                  <Input
                    id="org_name"
                    name="org_name"
                    type="text"
                    value={formData.org_name}
                    onChange={handleInputChange}
                    placeholder="Robotics Division"
                    className="text-xs h-8"
                    disabled={isLoading}
                  />
                </div>

                <div className="space-y-1">
                  <label htmlFor="org_slug" className="block text-xs font-medium text-[var(--color-fg-default)]">
                    Org Slug (optional)
                  </label>
                  <Input
                    id="org_slug"
                    name="org_slug"
                    type="text"
                    value={formData.org_slug}
                    onChange={handleInputChange}
                    placeholder="robotics-div"
                    className="text-xs h-8 font-mono"
                    disabled={isLoading}
                  />
                </div>
              </div>
            )}

            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <label htmlFor="password" className="block text-xs font-medium text-[var(--color-fg-default)]">
                  Password
                </label>
                {isRegister && (
                  <span className="text-[10px] text-[var(--color-attention-fg)] font-mono">
                    min 12 characters
                  </span>
                )}
              </div>
              <div className="relative">
                <Lock className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--color-fg-muted)]" />
                <Input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  value={formData.password}
                  onChange={handleInputChange}
                  placeholder="••••••••••••"
                  className="pl-8 pr-8 text-xs h-8"
                  required
                  disabled={isLoading}
                  autoComplete={isRegister ? 'new-password' : 'current-password'}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)]"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>

            {isRegister && (
              <div className="space-y-1">
                <label htmlFor="confirm_password" className="block text-xs font-medium text-[var(--color-fg-default)]">
                  Confirm Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--color-fg-muted)]" />
                  <Input
                    id="confirm_password"
                    name="confirm_password"
                    type={showPassword ? "text" : "password"}
                    value={formData.confirm_password || ""}
                    onChange={handleInputChange}
                    placeholder="••••••••••••"
                    className="pl-8 text-xs h-8"
                    required={isRegister}
                    disabled={isLoading}
                    autoComplete="new-password"
                  />
                </div>
              </div>
            )}

            {!isRegister && (
              <div className="flex items-center pt-1">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    name="remember_me"
                    checked={formData.remember_me || false}
                    onChange={handleInputChange}
                    className="rounded-[var(--radius-sm,4px)] border-[var(--color-border-default)] text-[var(--color-accent-emphasis)] focus:ring-[var(--color-accent-fg)] h-3.5 w-3.5"
                  />
                  <span className="text-xs text-[var(--color-fg-muted)]">Remember session on this device</span>
                </label>
              </div>
            )}

            <Button
              type="submit"
              variant="primary"
              className="w-full h-8.5 text-xs font-semibold mt-2"
              disabled={isLoading}
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  {isRegister ? 'Creating account...' : 'Signing in...'}
                </>
              ) : (
                isRegister ? 'Create Account' : 'Sign In'
              )}
            </Button>
          </form>

          <div className="mt-4 pt-3 border-t border-[var(--color-border-default)] text-center text-xs text-[var(--color-fg-muted)]">
            {isRegister ? (
              <span>
                Already have an account?{' '}
                <button
                  type="button"
                  onClick={() => {
                    setIsRegister(false);
                    clearError();
                    setFormData({ email: '', password: '', confirm_password: '', remember_me: true, full_name: '', org_name: '', org_slug: '', mfa_code: '' });
                  }}
                  className="text-[var(--color-accent-fg)] hover:underline font-semibold"
                >
                  Sign in
                </button>
              </span>
            ) : (
              <span>
                Need an engineering account?{' '}
                <button
                  type="button"
                  onClick={() => {
                    setIsRegister(true);
                    clearError();
                    setFormData({ email: '', password: '', confirm_password: '', remember_me: true, full_name: '', org_name: '', org_slug: '', mfa_code: '' });
                  }}
                  className="text-[var(--color-accent-fg)] hover:underline font-semibold"
                >
                  Register here
                </button>
              </span>
            )}
          </div>
        </Card>

        <div className="flex items-center justify-between text-[11px] text-[var(--color-fg-subtle)] px-2">
          <span>Cauveris v2.4.0 (Production Authentication)</span>
          <div className="flex items-center gap-3">
            <span className="cursor-default hover:text-[var(--color-fg-muted)]">Server Session</span>
            <span>·</span>
            <span className="cursor-default hover:text-[var(--color-fg-muted)]">Bcrypt Verified</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-[var(--color-canvas)] p-4">
          <Loader2 className="h-6 w-6 animate-spin text-[var(--color-accent-fg)]" />
        </div>
      }
    >
      <LoginForm />
    </Suspense>
  );
}
