"use client";

import React, { useRef, useState } from "react";
import { Upload } from "lucide-react";

export type DropzoneRejection = { file: File; reason: string };

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export function Dropzone({
  accept,
  maxFiles,
  maxBytes,
  hint,
  disabled,
  onFiles,
}: {
  /** Comma-separated extension list for the file input, e.g. ".pdf,.docx". */
  accept: string;
  maxFiles: number;
  maxBytes: number;
  /** Shown inside the zone BEFORE selection — formats and limits. */
  hint: string;
  disabled?: boolean;
  /** Accepted files, plus anything rejected client-side and why. */
  onFiles: (files: File[], rejected: DropzoneRejection[]) => void;
}): React.ReactElement {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragCounter = useRef(0);

  const processFileList = (incomingFiles: FileList | File[]) => {
    const filesArray = Array.from(incomingFiles);
    if (filesArray.length === 0) return;

    const accepted: File[] = [];
    const rejected: DropzoneRejection[] = [];

    const acceptedExts = accept
      .split(",")
      .map((ext) => ext.trim().toLowerCase())
      .filter(Boolean);

    filesArray.forEach((file) => {
      // Check file size
      if (file.size > maxBytes) {
        rejected.push({
          file,
          reason: `larger than ${formatBytes(maxBytes)}`,
        });
        return;
      }

      // Check file extension / accept filter if specified
      if (acceptedExts.length > 0) {
        const fileName = file.name.toLowerCase();
        const matchesExt = acceptedExts.some((ext) => {
          if (ext.startsWith(".")) {
            return fileName.endsWith(ext);
          }
          if (ext.includes("/")) {
            if (ext.endsWith("/*")) {
              return file.type.startsWith(ext.slice(0, -1));
            }
            return file.type.toLowerCase() === ext;
          }
          return false;
        });

        if (!matchesExt) {
          rejected.push({
            file,
            reason: `unsupported format (expected ${accept})`,
          });
          return;
        }
      }

      // Check file count cap
      if (accepted.length >= maxFiles) {
        rejected.push({
          file,
          reason: `exceeds limit of ${maxFiles} file${maxFiles === 1 ? "" : "s"}`,
        });
        return;
      }

      accepted.push(file);
    });

    onFiles(accepted, rejected);
  };

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (disabled) return;
    dragCounter.current += 1;
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (disabled) return;
    dragCounter.current -= 1;
    if (dragCounter.current === 0) {
      setIsDragging(false);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (disabled) return;
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (disabled) return;
    setIsDragging(false);
    dragCounter.current = 0;

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processFileList(e.dataTransfer.files);
    }
  };

  const handleClick = () => {
    if (disabled) return;
    inputRef.current?.click();
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      processFileList(e.target.files);
    }
    // Reset target value so picking the same file twice fires onChange again
    e.target.value = "";
  };

  return (
    <div className="w-full">
      <input
        ref={inputRef}
        type="file"
        multiple={maxFiles > 1}
        accept={accept}
        disabled={disabled}
        onChange={handleInputChange}
        className="hidden"
      />
      <button
        type="button"
        disabled={disabled}
        onClick={handleClick}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`flex w-full flex-col items-center gap-2 rounded-lg border border-dashed p-6 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${
          disabled
            ? "cursor-not-allowed pointer-events-none opacity-50 border-muted-foreground/25 bg-muted/10"
            : isDragging
              ? "border-primary bg-primary/10 ring-2 ring-primary/20"
              : "border-muted-foreground/25 hover:border-muted-foreground/50 bg-transparent hover:bg-muted/20"
        }`}
      >
        <Upload className="size-5 text-muted-foreground" />
        <span className="font-medium">
          {isDragging ? "Drop files here" : "Choose or drop files"}
        </span>
        <span className="text-xs text-muted-foreground">{hint}</span>
      </button>
    </div>
  );
}

export default Dropzone;
