export function Footer() {
  return (
    <footer className="border-t border-gray-800 mt-16">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-gray-500 text-sm">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
            </svg>
            <span>PDFtoDeck</span>
          </div>

          <div className="flex items-center gap-6 text-sm text-gray-600">
            <a href="#" className="hover:text-gray-400 transition-colors">
              Privacy Policy
            </a>
            <a href="#" className="hover:text-gray-400 transition-colors">
              Terms of Service
            </a>
            <a
              href="https://github.com/LotusWang0723/PDFtoDeck"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-gray-400 transition-colors"
            >
              GitHub
            </a>
          </div>
        </div>

        <p className="mt-4 text-center text-xs text-gray-700">
          Files are automatically deleted after 1 hour. We do not store any
          personal information.
        </p>
      </div>
    </footer>
  );
}
