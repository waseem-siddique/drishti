import type { Metadata, Viewport } from 'next';
import './globals.css';
import { Providers } from './providers';

export const metadata: Metadata = {
  title: 'DRISHTI - MPLADS Risk and Verification Intelligence',
  description: 'Turning thousands of scheme records into prioritized, explainable verification cases.',
};

export const viewport: Viewport = { width: 'device-width', initialScale: 1, viewportFit: 'cover' };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main-content">Skip to main content</a>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
