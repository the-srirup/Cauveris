import './globals.css';
import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import { ShellProvider } from '@/lib/useShell';
import { AuthProvider } from '@/components/AuthProvider';
import ShellLayout from '@/components/ShellLayout';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Cauveris - Where Failures Meet Cause',
  description: 'Autonomous reality debugger for AI-powered robotic systems',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full w-full" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  var raw = localStorage.getItem('cauveris-settings');
                  if (!raw) return;
                  var s = JSON.parse(raw);
                  var root = document.documentElement;
                  var theme = s.theme;
                  if (theme === 'light') {
                    root.classList.add('light');
                    root.classList.remove('dark');
                  } else if (theme === 'dark') {
                    root.classList.add('dark');
                    root.classList.remove('light');
                  } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
                    root.classList.add('light');
                    root.classList.remove('dark');
                  } else {
                    root.classList.add('dark');
                    root.classList.remove('light');
                  }
                  if (s.accentColor) {
                    root.classList.add('accent-' + s.accentColor);
                  }
                  if (s.density) {
                    root.classList.add('density-' + s.density);
                  }
                  if (s.reducedMotion) {
                    root.classList.add('reduced-motion');
                  }
                  if (s.animations === false) {
                    root.classList.add('animations-disabled');
                  }
                } catch (e) {}
              })();
            `,
          }}
        />
      </head>
      <body className={`${inter.className} h-full w-full bg-background text-foreground font-sans antialiased`}>
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