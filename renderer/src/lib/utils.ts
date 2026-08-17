/**
 * Adapted from eigent: src/lib/utils.ts (cn only — Karpathy: no unused date helpers).
 */
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
