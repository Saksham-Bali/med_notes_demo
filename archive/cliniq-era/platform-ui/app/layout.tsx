import type { Metadata } from 'next';
import './globals.css';
import Nav from '@/components/Nav';

export const metadata: Metadata = {
  title: 'ClinIQ | Quiet Clinical Intelligence',
  description: 'A minimal clinical intelligence interface for review-first medical workflows.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-body text-[15px] antialiased">
        <Nav />
        <main>{children}</main>
      </body>
    </html>
  );
}
