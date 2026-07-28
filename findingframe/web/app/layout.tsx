import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "FindingFrame — audit-grade oncology review",
  description:
    "Turn longitudinal radiology reports into an auditable, evidence-anchored finding record with deterministic RECIST 1.1 progression.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
