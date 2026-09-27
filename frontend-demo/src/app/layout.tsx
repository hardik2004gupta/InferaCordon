import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { Geist_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://inferacordon.vercel.app"),
  title: {
    default: "InferaCordon - Govern Reasoning Compute",
    template: "%s - InferaCordon",
  },
  description:
    "A governed AI inference control plane that makes reasoning compute schedulable, policy-bounded, cost-attributed, and quality-guaranteed.",
  openGraph: {
    title: "InferaCordon - Govern Reasoning Compute",
    description:
      "A governed AI inference control plane that makes reasoning compute schedulable, policy-bounded, cost-attributed, and quality-guaranteed.",
    type: "website",
    siteName: "InferaCordon",
  },
  twitter: {
    card: "summary",
    title: "InferaCordon - Govern Reasoning Compute",
    description:
      "A governed AI inference control plane that makes reasoning compute schedulable, policy-bounded, cost-attributed, and quality-guaranteed.",
  },
  robots: { index: true, follow: true },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${geistMono.variable}`}>
      <body className="min-h-dvh bg-background text-foreground antialiased">
        {children}
      </body>
    </html>
  );
}
