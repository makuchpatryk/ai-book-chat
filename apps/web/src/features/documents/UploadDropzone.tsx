import { useRef, useState } from "react";
import { Upload, AlertCircle } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useUploadDocument } from "@/features/documents/useUploadDocument";

const MAX_SIZE_MB = 50;
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;

export function UploadDropzone() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { mutate, isPending } = useUploadDocument();

  const handleFile = (file: File) => {
    setError(null);

    if (!file.name.endsWith(".pdf")) {
      setError("Only PDF files are supported");
      return;
    }

    if (file.size > MAX_SIZE_BYTES) {
      setError(`File must be smaller than ${MAX_SIZE_MB} MB`);
      return;
    }

    mutate(file);
  };

  const handleDrag = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.currentTarget.files?.[0];
    if (file) handleFile(file);
  };

  return (
    <div className="space-y-3">
      <div
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        className="relative rounded-lg border-2 border-dashed border-border p-6 transition-colors hover:border-primary"
        style={dragActive ? { borderColor: "hsl(var(--primary))" } : {}}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf"
          onChange={handleInputChange}
          className="hidden"
          disabled={isPending}
        />

        <div className="flex flex-col items-center justify-center gap-2">
          <Upload className="size-6 text-muted-foreground" />
          <div className="text-center text-sm">
            <p className="text-foreground font-medium">Drop PDF here or</p>
            <button
              type="button"
              className="text-xs text-primary hover:underline disabled:opacity-50 disabled:cursor-not-allowed p-0 h-auto"
              onClick={() => fileInputRef.current?.click()}
              disabled={isPending}
            >
              click to upload
            </button>
          </div>
          <p className="text-xs text-muted-foreground">Max {MAX_SIZE_MB} MB</p>
        </div>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="size-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {isPending && <p className="text-sm text-muted-foreground text-center">Uploading...</p>}
    </div>
  );
}
