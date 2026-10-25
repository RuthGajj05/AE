import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Nearby — Your next good business idea",
  description: "Practical recommendations for your small business, grounded in public sources, with drafts you can make your own.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
