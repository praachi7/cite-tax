import type { Metadata } from "next";
import Link from "next/link";
import { Nav } from "@/components/Nav";
import { DISCLAIMER, ERROR_RATES } from "@/lib/disclaimer";
import "./globals.css";

export const metadata: Metadata = {
  title: "CiteTax prototype",
  description: "Educational prototype: Indian and US tax position for India-resident IT freelancers, with a citation on every figure.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <div className="disclaimer" role="note">
          <strong>Prototype.</strong> {DISCLAIMER} {ERROR_RATES}
        </div>
        <header className="site-header">
          <Link href="/" className="brand">CiteTax</Link>
          <span className="muted">Deterministic engine · every figure cited</span>
        </header>
        <Nav />
        <main>{children}</main>
        <footer className="site-footer">
          <strong>Prototype.</strong> {DISCLAIMER} {ERROR_RATES}
        </footer>
      </body>
    </html>
  );
}
