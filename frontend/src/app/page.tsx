import { Hero } from "@/components/Hero";
import { UploadSection } from "@/components/UploadSection";
import { Features } from "@/components/Features";
import { Footer } from "@/components/Footer";

export default function Home() {
  return (
    <main className="min-h-screen">
      <Hero />
      <UploadSection />
      <Features />
      <Footer />
    </main>
  );
}
