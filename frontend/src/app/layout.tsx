import type { Metadata, Viewport } from "next";
import { Archivo, Newsreader } from "next/font/google";

import "./globals.css";

// Archivo for the interface, condensed (its width axis) for scores, clocks and headlines; Newsreader
// for the cards' prose. Latin Extended for names such as those with a ć.
const archivo = Archivo({ variable: "--font-archivo", subsets: ["latin", "latin-ext"], axes: ["wdth"] });
const newsreader = Newsreader({ variable: "--font-newsreader", subsets: ["latin", "latin-ext"], axes: ["opsz"] });

export const metadata: Metadata = {
  title: "Footnote",
  description: "Explained match intelligence from synthetic football events.",
};

export const viewport: Viewport = {
  themeColor: "#0d141e",
  colorScheme: "dark",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`dark ${archivo.variable} ${newsreader.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
