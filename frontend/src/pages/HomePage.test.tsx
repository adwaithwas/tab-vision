import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { HomePage } from "../pages/HomePage";
import * as api from "../services/api";
import * as upload from "../services/upload";
import type { UploadHandle } from "../services/upload";
import type { CapabilitiesResponse, HealthResponse, UploadResponse } from "../types/api";

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return { ...actual, getHealth: vi.fn(), getCapabilities: vi.fn() };
});

vi.mock("../services/upload", () => ({
  uploadVideo: vi.fn(),
}));

const getHealthMock = vi.mocked(api.getHealth);
const getCapabilitiesMock = vi.mocked(api.getCapabilities);
const uploadVideoMock = vi.mocked(upload.uploadVideo);

const HEALTH: HealthResponse = {
  status: "ok",
  service: "GuitarTab AI",
  version: "0.1.0",
  environment: "test",
  time: "2026-01-01T00:00:00Z",
};

const CAPABILITIES: CapabilitiesResponse = {
  service: "GuitarTab AI",
  version: "0.1.0",
  video_upload: {
    supported: true,
    max_file_size_mb: 100,
    allowed_extensions: [".mp4", ".mov", ".webm"],
    allowed_content_types: ["video/mp4", "video/quicktime", "video/webm"],
  },
  cv_pipeline: {
    implemented: false,
    stages: [
      {
        key: "fretboard_detection",
        label: "Fretboard detection",
        implemented: false,
        status: "planned",
        description: "Locate the fretboard and frets in the camera frame.",
      },
      {
        key: "tab_generation",
        label: "Tablature generation",
        implemented: false,
        status: "planned",
        description: "Render note events as six-string guitar tablature.",
      },
    ],
  },
  notes: [],
};

function validVideo(): File {
  return new File([new Uint8Array(64)], "scale.mp4", { type: "video/mp4" });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function pickFile(file: File) {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  expect(input).toBeTruthy();
  fireEvent.change(input!, { target: { files: [file] } });
}

beforeEach(() => {
  getHealthMock.mockReset();
  getCapabilitiesMock.mockReset();
  uploadVideoMock.mockReset();
  getHealthMock.mockResolvedValue(HEALTH);
  getCapabilitiesMock.mockResolvedValue(CAPABILITIES);
});

describe("HomePage — structure and backend state", () => {
  it("renders header, upload zone and an empty results section", async () => {
    render(<HomePage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Turn a performance into tablature.",
    );
    expect(screen.getByText("Drop a video here")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Results" })).toBeInTheDocument();
    await screen.findByText("Fretboard detection");
  });

  it("shows the live backend status once health responds", async () => {
    render(<HomePage />);
    await screen.findByText(/Backend online/);
  });

  it("reports the backend as offline when health fails", async () => {
    getHealthMock.mockRejectedValue(
      new api.ApiError("network_error", "could not reach the backend"),
    );
    render(<HomePage />);
    await screen.findByText(/Backend offline/);
  });

  it("lists pipeline stages as planned, never implemented", async () => {
    render(<HomePage />);
    await screen.findByText("CV pipeline: not implemented");
    await screen.findByText("Fretboard detection");
    const chips = screen.getAllByText("planned");
    expect(chips.length).toBeGreaterThan(0);
    expect(screen.queryByText("implemented")).not.toBeInTheDocument();
  });
});

describe("HomePage — file validation", () => {
  it("rejects an unsupported extension with an actionable error", async () => {
    render(<HomePage />);
    await screen.findByText(/Backend online/);
    await pickFile(new File(["x"], "notes.txt", { type: "text/plain" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/files are not supported/);
    expect(screen.getByRole("button", { name: /Analyze Video/ })).toBeDisabled();
  });

  it("rejects a file larger than the configured limit", async () => {
    render(<HomePage />);
    await screen.findByText(/Backend online/);
    const big = new File([new Uint8Array(8)], "huge.mp4", { type: "video/mp4" });
    Object.defineProperty(big, "size", { value: 150 * 1024 * 1024 });

    await pickFile(big);
    expect(await screen.findByRole("alert")).toHaveTextContent(/100 MB limit/);
    expect(screen.getByRole("button", { name: /Analyze Video/ })).toBeDisabled();
  });

  it("accepts a valid video and enables the analyze button", async () => {
    render(<HomePage />);
    await screen.findByText(/Backend online/);
    await pickFile(validVideo());

    expect(screen.getByText("scale.mp4")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Analyze Video/ })).toBeEnabled(),
    );
  });

  it("start button stays disabled while the backend is offline", async () => {
    getHealthMock.mockRejectedValue(
      new api.ApiError("network_error", "offline"),
    );
    render(<HomePage />);
    await screen.findByText(/Backend offline/);
    await pickFile(validVideo());
    expect(screen.getByRole("button", { name: /Analyze Video/ })).toBeDisabled();
  });
});

describe("HomePage — upload lifecycle", () => {
  it("uploads the file and reports the real job id without invented analysis", async () => {
    const user = userEvent.setup();
    render(<HomePage />);
    await screen.findByText(/Backend online/);
    await pickFile(validVideo());

    const d = deferred<UploadResponse>();
    const abort = vi.fn();
    uploadVideoMock.mockReturnValue({ promise: d.promise, abort } as UploadHandle);

    await user.click(screen.getByRole("button", { name: /Analyze Video/ }));

    // Duplicate submissions are blocked while in flight.
    expect(uploadVideoMock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: /Uploading/ })).toBeDisabled();

    d.resolve({
      job_id: "abc123job",
      status: "received",
      original_name: "scale.mp4",
      extension: "mp4",
      size_bytes: 64,
      content_type: "video/mp4",
      uploaded_at: "2026-01-01T00:00:00Z",
      retention_note: "Retained for up to 30 days.",
    });

    await screen.findByText("Video received and registered");
    expect(screen.getByText("abc123job")).toBeInTheDocument();
    expect(screen.getByText(/no notes can be produced yet/i)).toBeInTheDocument();
  });

  it("surfaces upload errors as useful messages", async () => {
    const user = userEvent.setup();
    render(<HomePage />);
    await screen.findByText(/Backend online/);
    await pickFile(validVideo());

    const d = deferred<UploadResponse>();
    uploadVideoMock.mockReturnValue({ promise: d.promise, abort: vi.fn() } as UploadHandle);
    await user.click(screen.getByRole("button", { name: /Analyze Video/ }));

    d.reject(new api.ApiError("file_too_large", "The file exceeds the configured maximum of 100 MB."));
    expect(await screen.findByText(/exceeds the configured maximum/)).toBeInTheDocument();
  });

  it("supports cancelling an in-flight upload", async () => {
    const user = userEvent.setup();
    render(<HomePage />);
    await screen.findByText(/Backend online/);
    await pickFile(validVideo());

    const d = deferred<UploadResponse>();
    const abort = vi.fn();
    uploadVideoMock.mockReturnValue({ promise: d.promise, abort } as UploadHandle);
    await user.click(screen.getByRole("button", { name: /Analyze Video/ }));

    await user.click(screen.getByRole("button", { name: /Cancel upload/ }));
    expect(abort).toHaveBeenCalledTimes(1);

    d.reject(new api.ApiError("cancelled", "Upload cancelled."));
    expect(await screen.findByText(/Upload cancelled/)).toBeInTheDocument();
  });

  it("prevents upload when health is still resolving", async () => {
    getHealthMock.mockReturnValue(new Promise(() => {}));
    render(<HomePage />);
    // Health stays pending: button must remain inert.
    await pickFile(validVideo());
    expect(screen.getByRole("button", { name: /Analyze Video/ })).toBeDisabled();
  });
});

describe("HomePage — accessibility basics", () => {
  it("exposes a labelled file input and busy states", async () => {
    render(<HomePage />);
    await screen.findByText(/Backend online/);
    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();
    expect(input!.getAttribute("accept")).toContain("video/");
    expect(input!.disabled).toBe(false);

    const analyze = screen.getByRole("button", { name: /Analyze Video/ });
    expect(analyze).toBeDisabled();
  });
});