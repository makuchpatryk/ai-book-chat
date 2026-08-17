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

  const handleDrag = (e: React.DragEvent<HTMLButtonElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLButtonElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.currentTarget.files?.[0];
    // Clear the value so picking the same file twice still fires a change.
    e.currentTarget.value = "";
    if (file) handleFile(file);
  };

  return (
    <div className="space-y-3">
      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf"
        onChange={handleInputChange}
        className="hidden"
        disabled={isPending}
      />

      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        disabled={isPending}
        className="relative w-full cursor-pointer rounded-lg border-2 border-dashed border-border p-6 transition-colors hover:border-primary disabled:cursor-not-allowed disabled:opacity-50"
        style={dragActive ? { borderColor: "hsl(var(--primary))" } : {}}
      >
        {/* Ignore pointer events so dragging over the label doesn't fire dragleave. */}
        <div className="pointer-events-none flex flex-col items-center justify-center gap-2">
          <Upload className="size-6 text-muted-foreground" />
          <div className="text-center text-sm">
            <p className="text-foreground font-medium">Drop PDF here</p>
            <p className="text-xs text-primary">or click to upload</p>
          </div>
          <p className="text-xs text-muted-foreground">Max {MAX_SIZE_MB} MB</p>
        </div>
      </button>

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
