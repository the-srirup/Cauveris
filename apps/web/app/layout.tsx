import './globals.css';
import '@fontsource/geist-sans';
import '@fontsource/geist-mono';
import type { Metadata } from 'next';
import { ShellProvider } from '@/lib/useShell';
import { AuthProvider } from '@/components/AuthProvider';
import ShellLayout from '@/components/ShellLayout';

export const metadata: Metadata = {
  title: 'Cauveris - Autonomous Systems Incident Analysis & Repair',
  description: 'Evidence-based root cause analysis, digital twin simulation, and verified repairs for complex autonomous system failures.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full w-full dark" data-theme="dark" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  var raw = localStorage.getItem('cauveris-settings');
                  var theme = 'dark';
                  if (raw) {
                    var s = JSON.parse(raw);
                    if (s.theme) theme = s.theme;
                  }
                  var root = document.documentElement;
                  if (theme === 'light') {
                    root.classList.add('light');
                    root.classList.remove('dark');
                    root.setAttribute('data-theme', 'light');
                  } else {
                    root.classList.add('dark');
                    root.classList.remove('light');
                    root.setAttribute('data-theme', 'dark');
                  }
                  if (raw) {
                    var s = JSON.parse(raw);
                    if (s.accentColor) root.classList.add('accent-' + s.accentColor);
                    if (s.density) root.classList.add('density-' + s.density);
                    if (s.reducedMotion) root.classList.add('reduced-motion');
                    if (s.animations === false) root.classList.add('animations-disabled');
                  }
                } catch (e) {}
              })();
            `,
          }}
        />
      </head>
      <body className="h-full w-full bg-[var(--color-canvas)] text-[var(--color-fg-default)] font-sans antialiased">
        <AuthProvider>
          <ShellProvider>
            <ShellLayout>
              {children}
            </ShellLayout>
          </ShellProvider>
        </AuthProvider>
      </body>
    </html>
  );
}