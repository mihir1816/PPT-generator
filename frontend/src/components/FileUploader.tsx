import { useCallback, useRef, useState } from "react";

interface FileUploaderProps {
  onFilesSelected: (files: File[]) => void;
  disabled?: boolean;
}

const ACCEPTED = ".pdf,.pptx,.docx,.doc,.txt,.png,.jpg,.jpeg,.webp";

export default function FileUploader({ onFilesSelected, disabled }: FileUploaderProps) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    (fileList: FileList | null) => {
      if (fileList && fileList.length > 0) {
        onFilesSelected(Array.from(fileList));
      }
    },
    [onFilesSelected],
  );

  return (
    <div
      className={`relative rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
        dragOver
          ? "border-blue-500 bg-blue-50"
          : "border-gray-300 hover:border-gray-400"
      } ${disabled ? "pointer-events-none opacity-50" : "cursor-pointer"}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        handleFiles(e.dataTransfer.files);
      }}
      onClick={() => inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPTED}
        className="hidden"
        onChange={(e) => {
          handleFiles(e.target.files);
          e.target.value = "";
        }}
      />
      <svg
        className="mx-auto h-12 w-12 text-gray-400"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 48 48"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M24 8v24m-12-12l12-12 12 12"
        />
      </svg>
      <p className="mt-2 text-sm text-gray-600">
        Drag & drop files or <span className="text-blue-600 underline">browse</span>
      </p>
      <p className="mt-1 text-xs text-gray-500">
        PDF, PPTX, DOCX, TXT, Images
      </p>
    </div>
  );
}
