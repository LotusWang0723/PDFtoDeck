import type { Metadata } from "next";
import { UploadSection } from "@/components/UploadSection";

export const metadata: Metadata = {
  title: "Convert — PDFtoDeck",
  description: "Upload and convert your PDF to editable PowerPoint.",
};

export default function ConvertPage() {
  return (
    <main className="min-h-screen">
      <div className="pt-12 pb-4 px-4 text-center">
        <a href="/" className="inline-flex items-center gap-2 text-gray-500 hover:text-gray-300 transition-colors text-sm mb-8">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
          </svg>
          Back to home
        </a>
        <h1 className="text-3xl font-bold text-gray-100 mt-4">Convert Your PDF</h1>
        <p className="text-gray-500 mt-2">Upload, adjust settings, and download your editable PowerPoint</p>
      </div>
      <UploadSection />
    </main>
  );
}
