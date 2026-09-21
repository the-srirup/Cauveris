import './globals.css';
import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import Sidebar from '@/components/Sidebar';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Cauveris - Where Failures Meet Their Cause',
  description: 'Autonomous reality debugger for AI-powered robotic systems',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full w-full">
      <body className="h-full w-full bg-background text-foreground font-sans antialiased relative">
        <div className="fixed inset-y-0 left-0 z-30 w-60">
          <Sidebar />
        </div>
        <main className="flex-1 pl-64 pt-8 pb-12 bg-background min-h-screen">
          {children}
        </main>
      </body>
    </html>
  );
}