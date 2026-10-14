import type { Metadata } from "next";
import "./globals.css";
import { Geist } from "next/font/google";
import { cn } from "@/lib/utils";

const geist = Geist({subsets:['latin'],variable:'--font-sans'});

const DESCRIPTION = "Grow your career into a Digital Garden, then practise interviews against it.";

// Link previews (Open Graph, X/Twitter). metadataBase makes the image URLs absolute,
// which crawlers need; the image itself is app/opengraph-image.png, picked up by name.
export const metadata: Metadata = {
  metadataBase: new URL("https://anyview.anyapps.cloud"),
  title: "AnyView",
  description: DESCRIPTION,
  openGraph: {
    type: "website",
    siteName: "AnyView",
    title: "AnyView",
    description: DESCRIPTION,
    url: "/",
  },
  twitter: {
    card: "summary_large_image",
    title: "AnyView",
    description: DESCRIPTION,
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={cn("font-sans", geist.variable)}>
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
