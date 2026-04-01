import { AuthButton } from "./AuthButton";

export function Hero() {
  return (
    <section className="relative overflow-hidden pt-20 pb-8 px-4 sm:px-6 lg:px-8">
      {/* Background gradient */}
      <div className="absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-gradient-to-b from-indigo-950/40 via-transparent to-transparent" />
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[600px] bg-indigo-500/10 rounded-full blur-3xl" />
      </div>

      {/* Auth button in top right */}
      <div className="absolute top-6 right-6">
        <AuthButton />
      </div>

      <div className="max-w-4xl mx-auto text-center">
        {/* Logo */}
        <div className="inline-flex items-center gap-2 mb-6 px-4 py-2 rounded-full bg-indigo-500/10 border border-indigo-500/20">
          <svg className="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
          </svg>
          <span className="text-sm text-indigo-300 font-medium">PDFtoDeck</span>
        </div>

        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight">
          Convert PDF to{" "}
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400">
            Editable PowerPoint
          </span>
        </h1>

        <p className="mt-6 text-lg sm:text-xl text-gray-400 max-w-2xl mx-auto leading-relaxed">
          Upload your PDF and get a fully editable .pptx file. Icons become
          editable shapes — change colors, resize, and customize freely.
        </p>
      </div>
    </section>
  );
}
