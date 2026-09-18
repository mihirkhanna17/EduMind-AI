import type { Metadata } from "next";
import "katex/dist/katex.min.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Edumind",
  description: "An AI teaching operating system that learns how you learn.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      {/* suppressHydrationWarning: browser extensions (Grammarly etc.) inject
          body attributes before React hydrates — harmless, don't warn */}
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
