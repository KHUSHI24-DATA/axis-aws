import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

interface PageLoadingProps {
  message?: string;
  className?: string;
}

export function PageLoading({
  message = "Loading...",
  className,
}: PageLoadingProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 py-12",
        className
      )}
    >
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  );
}

interface FormLoadingOverlayProps {
  message: string;
  className?: string;
}

export function FormLoadingOverlay({
  message,
  className,
}: FormLoadingOverlayProps) {
  return (
    <div
      className={cn(
        "absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-background/60 backdrop-blur-[1px]",
        className
      )}
    >
      <div className="flex items-center gap-2 rounded-md border bg-card px-4 py-3 text-sm shadow-sm">
        <Loader2 className="h-4 w-4 animate-spin text-primary" />
        {message}
      </div>
    </div>
  );
}
