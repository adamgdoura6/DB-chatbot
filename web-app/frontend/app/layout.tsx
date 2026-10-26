import type { Metadata } from "next";
import "./globals.css";

// No title on purpose: the page should not announce what it is.
export const metadata: Metadata = { title: "" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
