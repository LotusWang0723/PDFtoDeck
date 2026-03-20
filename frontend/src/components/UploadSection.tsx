"use client";

import { useState, useCallback, useRef } from "react";
import {
  uploadPDF,
  startConvert,
  getStatus,
  getDownloadUrl,
  type UploadResponse,
  type StatusResponse,
} from "@/lib/api";

type Stage = "idle" | "uploading" | "uploaded" | "converting" | "done" | "error";

export function UploadSection() {
  const [stage, setStage] = useState<Stage>("idle");
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [uploadInfo, setUploadInfo] = useState<UploadResponse | null>(null);
  const [progress, setProgress] = useState(0);
  const [errorMsg, setErrorMsg] = useState("");
  const [iconThreshold, setIconThreshold] = useState(5); // percentage
  const fileInputRef = useRef<HTMLInputElement>(null);

  const reset = useCallback(() => {
    setStage("idle");
    setFile(null);
    setUploadInfo(null);
    setProgress(0);
    setErrorMsg("");
    setIconThreshold(5);
  }, []);

  const handleFile = useCallback(async (f: File) => {
    if (!f.name.toLowerCase().endsWith(".pdf")) {
      setErrorMsg("Please select a PDF file");
      setStage("error");
      return;
    }
    if (f.size > 20 * 1024 * 1024) {
      setErrorMsg("File too large. Maximum 20MB for free tier.");
      setStage("error");
      return;
    }

    setFile(f);
    setStage("uploading");
    setErrorMsg("");

    try {
      const res = await uploadPDF(f);
      setUploadInfo(res);
      setStage("uploaded");
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : "Upload failed");
      setStage("error");
    }
  }, []);

  const handleConvert = useCallback(async () => {
    if (!uploadInfo) return;

    setStage("converting");
    setProgress(0);

    try {
      await startConvert(uploadInfo.task_id, iconThreshold / 100);

      // Poll for progress
      const poll = async () => {
        const status: StatusResponse = await getStatus(uploadInfo.task_id);

        if (status.status === "done") {
          setProgress(100);
          setStage("done");
          return;
        }

        if (status.status === "error") {
          setErrorMsg(status.error || "Conversion failed");
          setStage("error");
          return;
        }

        setProgress(status.progress);
        setTimeout(poll, 800);
      };

      poll();
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : "Conversion failed");
      setStage("error");
    }
  }, [uploadInfo, iconThreshold]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const f = e.dataTransfer.files[0];
      if (f) handleFile(f);
    },
    [handleFile]
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const f = e.target.files?.[0];
      if (f) handleFile(f);
    },
    [handleFile]
  );

  return (
    <section className="px-4 sm:px-6 lg:px-8 py-8">
      <div className="max-w-2xl mx-auto">
        {/* Upload zone - only show when idle or error */}
        {(stage === "idle" || stage === "error") && (
          <div
            className={`upload-zone relative border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer transition-all ${
              dragging
                ? "dragging border-indigo-500 bg-indigo-500/5"
                : "border-gray-700 hover:border-gray-500 bg-gray-900/50"
            }`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={handleInputChange}
            />

            {/* Upload icon */}
            <div className="mx-auto w-16 h-16 rounded-2xl bg-indigo-500/10 flex items-center justify-center mb-4">
              <svg
                className="w-8 h-8 text-indigo-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1.5}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
                />
              </svg>
            </div>

            <p className="text-lg font-medium text-gray-200">
              Drop your PDF here
            </p>
            <p className="mt-2 text-sm text-gray-500">
              or click to browse · Max 20MB, 10 pages
            </p>

            {/* Error message */}
            {stage === "error" && errorMsg && (
              <div className="mt-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20">
                <p className="text-sm text-red-400">{errorMsg}</p>
              </div>
            )}
          </div>
        )}

        {/* Uploading state */}
        {stage === "uploading" && (
          <div className="rounded-2xl border border-gray-700 bg-gray-900/50 p-8 text-center fade-in">
            <div className="mx-auto w-12 h-12 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin mb-4" />
            <p className="text-gray-300">Uploading {file?.name}...</p>
          </div>
        )}

        {/* Uploaded - show file info + settings */}
        {stage === "uploaded" && uploadInfo && (
          <div className="rounded-2xl border border-gray-700 bg-gray-900/50 p-8 fade-in">
            {/* File info */}
            <div className="flex items-center gap-4 mb-6">
              <div className="w-12 h-12 rounded-xl bg-indigo-500/10 flex items-center justify-center shrink-0">
                <svg className="w-6 h-6 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                </svg>
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-gray-200 truncate">
                  {file?.name}
                </p>
                <p className="text-xs text-gray-500">
                  {uploadInfo.pages} pages · {uploadInfo.size_mb} MB
                </p>
              </div>
              <button
                onClick={reset}
                className="text-gray-500 hover:text-gray-300 transition-colors"
                title="Remove file"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Icon threshold slider */}
            <div className="mb-6">
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium text-gray-300">
                  Icon Detection Threshold
                </label>
                <span className="text-sm text-indigo-400 font-mono">
                  {iconThreshold}%
                </span>
              </div>
              <input
                type="range"
                min={1}
                max={20}
                value={iconThreshold}
                onChange={(e) => setIconThreshold(Number(e.target.value))}
                className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-indigo-500"
              />
              <p className="mt-2 text-xs text-gray-500">
                Elements smaller than {iconThreshold}% of the page will be
                converted to editable shapes
              </p>
            </div>

            {/* Convert button */}
            <button
              onClick={handleConvert}
              className="w-full py-3 px-6 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition-colors flex items-center justify-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12h15m0 0l-6.75-6.75M19.5 12l-6.75 6.75" />
              </svg>
              Convert to PowerPoint
            </button>
          </div>
        )}

        {/* Converting state */}
        {stage === "converting" && (
          <div className="rounded-2xl border border-indigo-500/30 bg-gray-900/50 p-8 fade-in pulse-glow">
            <div className="flex items-center gap-4 mb-4">
              <div className="w-10 h-10 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin shrink-0" />
              <div>
                <p className="text-gray-200 font-medium">Converting...</p>
                <p className="text-sm text-gray-500">{file?.name}</p>
              </div>
            </div>

            {/* Progress bar */}
            <div className="w-full bg-gray-800 rounded-full h-2.5 overflow-hidden">
              <div
                className="progress-bar bg-gradient-to-r from-indigo-500 to-purple-500 h-full rounded-full"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-gray-500 text-right">{progress}%</p>
          </div>
        )}

        {/* Done - download */}
        {stage === "done" && uploadInfo && (
          <div className="rounded-2xl border border-green-500/30 bg-gray-900/50 p-8 text-center fade-in">
            <div className="mx-auto w-16 h-16 rounded-full bg-green-500/10 flex items-center justify-center mb-4">
              <svg className="w-8 h-8 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
            </div>

            <p className="text-lg font-medium text-gray-200 mb-1">
              Conversion Complete!
            </p>
            <p className="text-sm text-gray-500 mb-6">
              Your PowerPoint file is ready to download
            </p>

            <a
              href={getDownloadUrl(uploadInfo.task_id)}
              className="inline-flex items-center gap-2 py-3 px-8 rounded-xl bg-green-600 hover:bg-green-500 text-white font-medium transition-colors"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
              </svg>
              Download .pptx
            </a>

            <button
              onClick={reset}
              className="mt-4 block mx-auto text-sm text-gray-500 hover:text-gray-300 transition-colors"
            >
              Convert another file
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
