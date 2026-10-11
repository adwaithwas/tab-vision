import { useEffect, useRef, useState } from "react";

export interface VideoMetadata {
  durationSeconds: number | null;
  width: number | null;
  height: number | null;
}

const UNKNOWN: VideoMetadata = { durationSeconds: null, width: null, height: null };

/**
 * Reads duration and resolution from a selected local file by loading its
 * metadata into a temporary `<video>` element.
 *
 * The temporary object URL is revoked both on success and on unmount so the
 * browser does not keep the file open. In environments without media support
 * (e.g. jsdom) metadata stays `null`.
 */
export function useVideoMetadata(file: File | null): VideoMetadata {
  const [metadata, setMetadata] = useState<VideoMetadata>(UNKNOWN);
  const objectUrl = useRef<string | null>(null);

  useEffect(() => {
    if (!file) {
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
      objectUrl.current = null;
      setMetadata(UNKNOWN);
      return;
    }

    let cancelled = false;
    let video: HTMLVideoElement | null = null;
    const url = URL.createObjectURL(file);
    objectUrl.current = url;

    const releaseVideo = () => {
      if (!video) return;
      try {
        video.removeAttribute("src");
        video.load();
      } catch {
        // jsdom and some test environments do not implement media loading.
      }
    };

    video = document.createElement("video");
    video.preload = "metadata";
    video.muted = true;

    const finish = (next: VideoMetadata) => {
      if (!cancelled) setMetadata(next);
      cleanup();
    };

    const cleanup = () => {
      if (objectUrl.current) {
        URL.revokeObjectURL(objectUrl.current);
        objectUrl.current = null;
      }
      releaseVideo();
    };

    video.onloadedmetadata = () => {
      const duration = Number.isFinite(video?.duration) ? video!.duration : null;
      finish({
        durationSeconds: duration,
        width: video?.videoWidth || null,
        height: video?.videoHeight || null,
      });
    };
    video.onerror = () => finish(UNKNOWN);
    video.src = url;

    return () => {
      cancelled = true;
      cleanup();
    };
  }, [file]);

  return metadata;
}