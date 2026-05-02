"use client";

import React, { useEffect, useRef, useState } from "react";
import { X, Minimize2, Maximize2, Move } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface FloatingWindowProps {
  id: string;
  title: string;
  children: React.ReactNode;
  position: { x: number; y: number };
  size: { width: number; height: number };
  minimized?: boolean;
  onClose: () => void;
  onPositionChange: (pos: { x: number; y: number }) => void;
  onSizeChange: (size: { width: number; height: number }) => void;
  onMinimize: () => void;
  onRestore: () => void;
  className?: string;
  minimizedIndex?: number;
}

export function FloatingWindow({
  id,
  title,
  children,
  position,
  size,
  minimized = false,
  onClose,
  onPositionChange,
  onSizeChange,
  onMinimize,
  onRestore,
  className,
  minimizedIndex = 0,
}: FloatingWindowProps) {
  const windowRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isDragging) {
        onPositionChange({ x: e.clientX - dragOffset.x, y: e.clientY - dragOffset.y });
      }
      if (isResizing && windowRef.current) {
        const rect = windowRef.current.getBoundingClientRect();
        onSizeChange({
          width: Math.max(400, e.clientX - rect.left),
          height: Math.max(300, e.clientY - rect.top),
        });
      }
    };
    const handleMouseUp = () => { setIsDragging(false); setIsResizing(false); };

    if (isDragging || isResizing) {
      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
    }
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isDragging, isResizing, dragOffset, onPositionChange, onSizeChange]);

  const handleDragStart = (e: React.MouseEvent) => {
    if (windowRef.current) {
      const rect = windowRef.current.getBoundingClientRect();
      setDragOffset({ x: e.clientX - rect.left, y: e.clientY - rect.top });
      setIsDragging(true);
    }
  };

  if (minimized) {
    return (
      <div
        className="fixed bottom-4 z-50 flex items-center gap-2 rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 shadow-lg"
        style={{ right: `${16 + minimizedIndex * 200}px` }}
      >
        <span className="max-w-[130px] truncate text-sm font-medium text-green-100">{title}</span>
        <Button size="icon" variant="ghost" className="h-6 w-6 text-gray-400 hover:bg-gray-800" onClick={onRestore}>
          <Maximize2 className="h-3 w-3" />
        </Button>
        <Button size="icon" variant="ghost" className="h-6 w-6 text-gray-400 hover:bg-gray-800" onClick={onClose}>
          <X className="h-3 w-3" />
        </Button>
      </div>
    );
  }

  return (
    <div
      ref={windowRef}
      className={cn(
        "fixed z-50 flex flex-col overflow-hidden rounded-lg border border-gray-700 bg-gray-900 shadow-2xl",
        isDragging && "cursor-grabbing select-none",
        className
      )}
      style={{ left: position.x, top: position.y, width: size.width, height: size.height }}
    >
      {/* Header */}
      <div
        className="flex cursor-grab items-center justify-between border-b border-gray-800 bg-gray-800 px-3 py-2 active:cursor-grabbing"
        onMouseDown={handleDragStart}
      >
        <div className="flex items-center gap-2 min-w-0">
          <Move className="h-3 w-3 shrink-0 text-gray-500" />
          <span className="truncate text-sm font-medium text-green-100">{title}</span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <Button size="icon" variant="ghost" className="h-6 w-6 text-gray-400 hover:bg-gray-700" onClick={onMinimize}>
            <Minimize2 className="h-3 w-3" />
          </Button>
          <Button size="icon" variant="ghost" className="h-6 w-6 text-gray-400 hover:bg-gray-700" onClick={onClose}>
            <X className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto bg-gray-950">{children}</div>

      {/* Resize handle */}
      <div
        className="absolute bottom-0 right-0 h-5 w-5 cursor-se-resize"
        onMouseDown={(e) => { e.stopPropagation(); setIsResizing(true); }}
      >
        <svg className="absolute bottom-1 right-1 h-3 w-3 text-gray-600" fill="currentColor" viewBox="0 0 8 8">
          <path d="M6 0v2H4v2H2v2H0v2h2V6h2V4h2V2h2V0H6z" />
        </svg>
      </div>
    </div>
  );
}
