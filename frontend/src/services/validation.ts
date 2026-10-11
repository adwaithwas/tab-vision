/**
 * Client-side video validation.
 *
 * Mirrors the backend rules (extension allow-list, size limit) so invalid
 * files are rejected before any network request is made. The backend still
 * re-validates every upload.
 */

export interface VideoValidationRules {
  maxBytes: number;
  allowedExtensions: string[];
}

export const DEFAULT_MAX_BYTES = 100 * 1024 * 1024;
export const DEFAULT_ALLOWED_EXTENSIONS = [".mp4", ".mov", ".webm"];

const ALLOWED_CONTENT_TYPES = [
  "video/mp4",
  "video/quicktime",
  "video/webm",
  "application/octet-stream",
];

export function fileExtension(name: string): string {
  const match = /\.[^.\\/]+$/.exec(name);
  return match ? match[0].toLowerCase() : "";
}

export function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  const value = bytes / 1024 ** exponent;
  const decimals = value >= 10 || exponent === 0 ? 0 : 1;
  return `${value.toFixed(decimals)} ${units[exponent]}`;
}

/**
 * Returns a user-presentable error message, or `null` when the file is valid.
 */
export function validateVideoFile(
  file: File,
  rules: VideoValidationRules,
): string | null {
  const ext = fileExtension(file.name);
  const allowed = rules.allowedExtensions.map((e) => e.toLowerCase());

  if (!ext) {
    return `“${file.name}” has no file extension. Please choose an ${allowed.join(", ")} video.`;
  }
  if (!allowed.includes(ext)) {
    return `“${ext}” files are not supported. Accepted formats: ${allowed.join(", ")}.`;
  }
  if (file.type && !ALLOWED_CONTENT_TYPES.includes(file.type) && !file.type.startsWith("video/")) {
    return `The file “${file.name}” does not look like a video (reported type “${file.type}”).`;
  }
  if (file.size === 0) {
    return `“${file.name}” is empty. Please choose a non-empty video.`;
  }
  if (file.size > rules.maxBytes) {
    const limitMb = Math.round(rules.maxBytes / (1024 * 1024));
    return `“${file.name}” is ${formatBytes(file.size)} — larger than the ${limitMb} MB limit.`;
  }
  return null;
}