"use client";

import { useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useAuthStore, LoginRequest, RegisterRequest } from '@/lib/auth';
import { Button, Input, Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui';
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
    <div className="min-h-screen flex items-center justify-center bg-[var(--theme-background)] p-4">
      <NotificationContainer />

      <Card className="w-full max-w-2xl">
        <CardHeader className="text-center pb-4">
          <CardTitle className="text-2xl font-bold">Cauveris</CardTitle>
          <CardDescription className="text-[var(--color-text-muted)]">
            {isRegister ? 'Create your account' : 'Sign in to your account'}
          </CardDescription>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="flex items-center gap-2 p-3 rounded-lg bg-[var(--color-brand-danger)]/10 border border-[var(--color-brand-danger)]/20 text-[var(--color-brand-danger)] text-sm">
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {!isRegister || (isRegister && (
              <>
                <div className="space-y-2">
                  <label htmlFor="full_name" className="text-sm font-medium">
                    Full Name
                  </label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--color-text-muted)]" />
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
              <label htmlFor="email" className="text-sm font-medium">
                Email
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--color-text-muted)]" />
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
                  <label htmlFor="org_name" className="text-sm font-medium">
                    Organization Name
                  </label>
                  <div className="relative">
                    <Input
                      id="org_name"
                      name="org_name"
                      type="text"
                      value={formData.org_name}
                      onChange={handleInputChange}
                      placeholder="Acme Corp"
                      className="pl-10"
                      disabled={isLoading}
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <label htmlFor="org_slug" className="text-sm font-medium">
                    Organization Slug
                  </label>
                  <div className="relative">
                    <Input
                      id="org_slug"
                      name="org_slug"
                      type="text"
                      value={formData.org_slug}
                      onChange={handleInputChange}
                      placeholder="acme-corp"
                      className="pl-10"
                      disabled={isLoading}
                    />
                  </div>
                </div>
              </>
            )}

            <div className="space-y-2">
              <label htmlFor="password" className="text-sm font-medium">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--color-text-muted)]" />
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
                <label htmlFor="mfa_code" className="text-sm font-medium">
                  MFA Code (if enabled)
                </label>
                <div className="relative">
                  <Input
                    id="mfa_code"
                    name="mfa_code"
                    type="text"
                    value={mfaCode}
                    onChange={(e) => setMfaCode(e.target.value)}
                    placeholder="123456"
                    className="pl-10"
                    disabled={isLoading}
                    autoComplete="one-time-code"
                  />
                </div>
              </div>
            )}

            {!isRegister && (
              <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    name="remember_me"
                    checked={formData.remember_me || false}
                    onChange={handleInputChange}
                    className="rounded border-[var(--color-border)] text-[var(--color-brand-primary)] focus:ring-primary"
                  />
                  <span className="text-sm text-[var(--color-text-muted)]">Remember me</span>
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

          <div className="mt-6 text-center text-sm text-[var(--color-text-muted)]">
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
                  className="text-[var(--color-brand-primary)] hover:underline font-medium"
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
                  className="text-[var(--color-brand-primary)] hover:underline font-medium"
                >
                  Create account
                </button>
              </>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-[var(--theme-background)] p-4">
          <Loader2 className="h-8 w-8 animate-spin text-[var(--color-brand-primary)]" />
        </div>
      }
    >
      <LoginForm />
    </Suspense>
  );
}