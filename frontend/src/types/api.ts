/**
 * API contracts shared with the FastAPI backend.
 *
 * Keep this file in sync with `docs/api.md` — the CV pipeline will extend
 * these types rather than rewrite them.
 */

export type JobStatus =
  | "received"
  | "queued"
  | "analyzing"
  | "completed"
  | "failed";

export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
  environment: string;
  /** ISO-8601 timestamp. */
  time: string;
}

export interface UploadCapability {
  supported: boolean;
  max_file_size_mb: number;
  allowed_extensions: string[];
  allowed_content_types: string[];
}

export interface CapabilityStage {
  key: string;
  label: string;
  implemented: boolean;
  status: "implemented" | "planned" | "in_progress";
  description: string;
}

export interface CapabilitiesResponse {
  service: string;
  version: string;
  video_upload: UploadCapability;
  cv_pipeline: {
    implemented: boolean;
    stages: CapabilityStage[];
  };
  notes: string[];
}

export interface UploadResponse {
  job_id: string;
  status: JobStatus;
  original_name: string;
  extension: string;
  size_bytes: number;
  content_type: string;
  /** ISO-8601 timestamp. */
  uploaded_at: string;
  retention_note: string;
  analysis?: any;
}

/** A single detected note — populated by the CV pipeline in a later milestone. */
export interface NoteEvent {
  /** 1 = high E, 6 = low E (standard tuning order used by the tablature view). */
  string: number;
  fret: number;
  /** Seconds from the start of the clip. */
  start_s: number;
  end_s: number;
  /** 0–1, when the pipeline can produce one. */
  confidence: number | null;
}

export interface AnalysisResult {
  events: NoteEvent[];
}

export interface JobResponse {
  job_id: string;
  status: JobStatus;
  original_name: string;
  extension: string;
  size_bytes: number;
  content_type: string;
  created_at: string;
  updated_at: string | null;
  /** Always null until the CV pipeline is implemented. */
  analysis: AnalysisResult | null;
  error: string | null;
}