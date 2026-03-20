import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PDFtoDeck — Convert PDF to Editable PowerPoint",
  description:
    "Free online tool to convert PDF to editable PowerPoint. Preserves layout, extracts icons as editable shapes. No registration required.",
  keywords: [
    "pdf to ppt",
    "pdf to powerpoint",
    "convert pdf to editable ppt",
    "pdf converter",
    "editable powerpoint",
  ],
  openGraph: {
    title: "PDFtoDeck — Convert PDF to Editable PowerPoint",
    description:
      "Convert PDF to editable PPT with smart icon extraction. Free & fast.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
