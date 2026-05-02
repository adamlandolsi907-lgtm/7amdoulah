"use client";
import React from "react";

interface ImageViewerProps {
  content?: string;
  fileUrl?: string;
  alt?: string;
}

export function ImageViewer({ content, fileUrl, alt = "Document" }: ImageViewerProps) {
  const src = content
    ? content.startsWith("data:") ? content : `data:image/jpeg;base64,${content}`
    : fileUrl ?? "";

  return (
    <div className="flex h-full items-center justify-center bg-gray-950 p-4">
      {src ? (
        <img
          src={src}
          alt={alt}
          className="max-h-full max-w-full rounded-lg object-contain shadow-lg"
        />
      ) : (
        <div className="text-center text-gray-500">
          <p className="text-sm">Aucune image disponible</p>
          <p className="text-xs mt-1 opacity-60">Le contenu de l'image sera chargé par le pipeline d'extraction.</p>
        </div>
      )}
    </div>
  );
}
