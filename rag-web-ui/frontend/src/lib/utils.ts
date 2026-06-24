import { type ClassValue, clsx } from "clsx"
import { formatDistanceToNow } from "date-fns"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** API datetimes from the backend are UTC but often omit the Z suffix. */
export function parseApiUtcDate(value: string): Date {
  const trimmed = value.trim()
  if (/[zZ]|[+-]\d{2}:\d{2}$/.test(trimmed)) {
    return new Date(trimmed)
  }
  return new Date(`${trimmed}Z`)
}

const INDIA_TZ = "Asia/Kolkata"

export function formatIndiaDateTime(value: string): string {
  const date = parseApiUtcDate(value)
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: INDIA_TZ,
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(date)
}

export function formatIndiaRelativeTime(value: string): string {
  return formatDistanceToNow(parseApiUtcDate(value), { addSuffix: true })
}