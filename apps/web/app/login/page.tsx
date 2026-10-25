"use client";

import { useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useAuthStore, LoginRequest, RegisterRequest } from '@/lib/auth';
import { Button, Input, Card, PageHeader } from '@/components/ui';
import { Mail, Lock, User, AlertCircle, Loader2 } from 'lucide-react';
import { NotificationContainer } from '@/components/Notification';

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, register, isLoading, error, clearError } = useAuthStore();
  const [isRegister, setIsRegister] = useState(false);
  interface FormDataState {
    email: string;
    password: string;
    remember_me: boolean;
    full_name: string;
    org_name: string;
    org_slug: string;
    mfa_code: string;
  }
  const [formData, setFormData] = useState<FormDataState>({
    email: '',
    password: '',
    remember_me: false,
    full_name: '',
    org_name: '',
    org_slug: '',
    mfa_code: '',
  });
  const [mfaCode, setMfaCode] = useState('');

  // Check for redirect param
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

    try {
      if (isRegister) {
        await register(formData as RegisterRequest);
      } else {
        const loginData: LoginRequest = {
          email: formData.email,
          password: formData.password,
          remember_me: formData.remember_me || false,
          mfa_code: mfaCode || undefined,
        };
        await login(loginData);
      }
      router.push(redirectTo);
      router.refresh();
    } catch (err: any) {
      // Error is already set in store
    }
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center p-4 bg-[var(--color-canvas)]">
      <NotificationContainer />

      <div className="w-full max-w-md">
        {/* Brand Header */}
        <div className="text-center mb-8">
          <span className="inline-flex items-center justify-center w-12 h-12 rounded-[var(--radius-lg)] bg-[var(--color-accent-emphasis)] text-white font-bold text-xl mr-2">
            C
          </span>
          <span className="font-bold text-xl text-[var(--color-fg-default)]">Cauveris</span>
        </div>

        <Card>
          <PageHeader
            title={isRegister ? "Create your account" : "Sign in to your account"}
            subtitle={isRegister ? "Get started with Cauveris incident investigation" : "Access your mission control dashboard"}
            className="text-center pb-4"
          />

          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="flex items-center gap-2 p-3 rounded-[var(--radius-md)] bg-[var(--color-danger-muted)] border border-[var(--color-danger-muted)]/30 text-[var(--color-danger-fg)] text-sm">
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {!isRegister || (isRegister && (
              <>
                <div className="space-y-2">
                  <label htmlFor="full_name" className="block text-sm font-medium text-[var(--color-fg-default)]">
                    Full Name
                  </label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--color-fg-muted)]" />
                    <Input
                      id="full_name"
                      name="full_name"
                      type="text"
                      value={formData.full_name}
                      onChange={handleInputChange}
                      placeholder="John Doe"
                      className="pl-10"
                      required={isRegister}
                      disabled={isLoading}
                    />
                  </div>
                </div>
              </>
            ))}

            <div className="space-y-2">
              <label htmlFor="email" className="block text-sm font-medium text-[var(--color-fg-default)]">
                Email
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--color-fg-muted)]" />
                <Input
                  id="email"
                  name="email"
                  type="email"
                  value={formData.email}
                  onChange={handleInputChange}
                  placeholder="you@example.com"
                  className="pl-10"
                  required
                  disabled={isLoading}
                  autoComplete="email"
                />
              </div>
            </div>

            {isRegister && (
              <>
                <div className="space-y-2">
                  <label htmlFor="org_name" className="block text-sm font-medium text-[var(--color-fg-default)]">
                    Organization Name
                  </label>
                  <Input
                    id="org_name"
                    name="org_name"
                    type="text"
                    value={formData.org_name}
                    onChange={handleInputChange}
                    placeholder="Acme Corp"
                    disabled={isLoading}
                  />
                </div>

                <div className="space-y-2">
                  <label htmlFor="org_slug" className="block text-sm font-medium text-[var(--color-fg-default)]">
                    Organization Slug
                  </label>
                  <Input
                    id="org_slug"
                    name="org_slug"
                    type="text"
                    value={formData.org_slug}
                    onChange={handleInputChange}
                    placeholder="acme-corp"
                    disabled={isLoading}
                  />
                </div>
              </>
            )}

            <div className="space-y-2">
              <label htmlFor="password" className="block text-sm font-medium text-[var(--color-fg-default)]">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--color-fg-muted)]" />
                <Input
                  id="password"
                  name="password"
                  type="password"
                  value={formData.password}
                  onChange={handleInputChange}
                  placeholder="••••••••"
                  className="pl-10"
                  required
                  disabled={isLoading}
                  autoComplete={isRegister ? 'new-password' : 'current-password'}
                />
              </div>
            </div>

            {!isRegister && (
              <div className="space-y-2">
                <label htmlFor="mfa_code" className="block text-sm font-medium text-[var(--color-fg-default)]">
                  MFA Code (if enabled)
                </label>
                <Input
                  id="mfa_code"
                  name="mfa_code"
                  type="text"
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value)}
                  placeholder="123456"
                  disabled={isLoading}
                  autoComplete="one-time-code"
                />
              </div>
            )}

            {!isRegister && (
              <div className="flex items-center">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    name="remember_me"
                    checked={formData.remember_me || false}
                    onChange={handleInputChange}
                    className="rounded-[var(--radius-sm)] border-[var(--color-border-default)] text-[var(--color-accent-fg)] focus:ring-[var(--color-accent-fg)] focus:ring-offset-[var(--color-canvas)] h-4 w-4"
                  />
                  <span className="text-sm text-[var(--color-fg-muted)]">Remember me</span>
                </label>
              </div>
            )}

            <Button
              type="submit"
              className="w-full"
              disabled={isLoading}
              size="lg"
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {isRegister ? 'Creating account...' : 'Signing in...'}
                </>
              ) : (
                isRegister ? 'Create Account' : 'Sign In'
              )}
            </Button>
          </form>

          <div className="mt-6 text-center text-sm text-[var(--color-fg-muted)]">
            {isRegister ? (
              <>
                Already have an account?{' '}
                <button
                  type="button"
                  onClick={() => {
                    setIsRegister(false);
                    clearError();
                    setFormData({ email: '', password: '', remember_me: false, full_name: '', org_name: '', org_slug: '', mfa_code: '' });
                    setMfaCode('');
                  }}
                  className="text-[var(--color-accent-fg)] hover:underline font-medium"
                >
                  Sign in
                </button>
              </>
            ) : (
              <>
                Don't have an account?{' '}
                <button
                  type="button"
                  onClick={() => {
                    setIsRegister(true);
                    clearError();
                    setFormData({ email: '', password: '', remember_me: false, full_name: '', org_name: '', org_slug: '', mfa_code: '' });
                    setMfaCode('');
                  }}
                  className="text-[var(--color-accent-fg)] hover:underline font-medium"
                >
                  Create account
                </button>
              </>
            )}
          </div>
        </Card>

        <p className="mt-6 text-center text-xs text-[var(--color-fg-subtle)]">
          By continuing, you agree to our <Link href="/terms" className="text-[var(--color-accent-fg)] hover:underline">Terms of Service</Link> and <Link href="/privacy" className="text-[var(--color-accent-fg)] hover:underline">Privacy Policy</Link>.
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-[var(--color-canvas)] p-4">
          <Loader2 className="h-8 w-8 animate-spin text-[var(--color-accent-fg)]" />
        </div>
      }
    >
      <LoginForm />
    </Suspense>
  );
}