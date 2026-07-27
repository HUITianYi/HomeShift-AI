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
    template: "%s | HomeShift AI",
  },
  description:
    "Turn real household energy data into a traceable savings plan with live specialist agents.",
  openGraph: {
    title: "HomeShift AI | Real data, live agents, traceable plan",
    description:
      "Seven specialist agents turn household energy evidence into a measurable action plan.",
    type: "website",
    images: ["/og-real-data.png"],
  },
  twitter: {
    card: "summary_large_image",
    title: "HomeShift AI | Real data, live agents, traceable plan",
    description:
      "A deterministic and explainable household energy copilot.",
    images: ["/og-real-data.png"],
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
