import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import { env } from 'cloudflare:workers';
import './globals.css';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  metadataBase: new URL((env as unknown as { SITE_ORIGIN?: string }).SITE_ORIGIN || 'http://localhost:3000'),
  title: 'IDShield AI — Identity & Document Risk Screening',
  description: 'Local, consent-based identity risk screening with five transparent stages, explainable evidence, and human officer decisions. SIH 2026.',
  icons: { icon: '/favicon.svg' },
  openGraph: { title: 'IDShield AI', description: 'Evidence behind every decision. Local screening, session privacy, and human officer oversight.', images: [{url:'/og.png',width:1729,height:910,alt:'IDShield AI — Evidence behind every decision.'}], type:'website' },
  twitter: { card:'summary_large_image', title:'IDShield AI', description:'Evidence behind every decision. Local identity risk screening.', images:['/og.png'] },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
