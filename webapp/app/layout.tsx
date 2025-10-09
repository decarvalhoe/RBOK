import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Réalisons - Assistant Procédural',
  description: 'Assistant procédural intelligent pour guider vos processus',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body className="min-h-screen bg-slate-50 text-gray-900 antialiased">{children}</body>
    </html>
  );
}
