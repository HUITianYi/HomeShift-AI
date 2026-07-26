import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL("https://homeshift.ai"),
  title: {
    default: "HomeShift AI",
    template: "%s · HomeShift AI",
  },
  description:
    "Agentic household energy management that cuts bills without sacrificing comfort.",
  openGraph: {
    title: "HomeShift AI — Cut bills, not comfort",
    description:
      "Seven specialist agents turn household energy evidence into a measurable seven-day plan.",
    type: "website",
    images: ["/og.png"],
  },
  twitter: {
    card: "summary_large_image",
    title: "HomeShift AI — Cut bills, not comfort",
    description:
      "An explainable, adaptive household energy copilot.",
    images: ["/og.png"],
  },
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
