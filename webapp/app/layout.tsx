import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Réalisons - Assistant Procédural',
  description: 'Assistant procédural intelligent pour guider vos processus',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  )
}
