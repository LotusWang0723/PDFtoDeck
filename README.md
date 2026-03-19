# PDFtoDeck

Convert PDF to editable PowerPoint with smart icon extraction.

## Features

- **PDF → PPTX conversion** with preserved layout
- **Smart icon extraction**: small vector graphics converted to editable PPT shapes
- **Adjustable threshold**: control which elements become editable shapes
- **Freemium model**: free tier with generous limits

## Architecture

```
Browser → Cloudflare Pages (Next.js)
       → Cloudflare Workers (API Gateway)
       → VPS (Python FastAPI converter)
       → Cloudflare R2 (file storage)
```

## Tech Stack

- **Frontend**: Next.js (App Router) + Tailwind CSS
- **Backend**: Python FastAPI + pymupdf + python-pptx
- **Gateway**: Cloudflare Workers
- **Storage**: Cloudflare R2

## Getting Started

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## License

MIT
