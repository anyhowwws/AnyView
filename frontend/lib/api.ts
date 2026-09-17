import { idToken } from "@/lib/auth";
import { readSse } from "@/lib/sse";
import type {
  Answer,
  Brain,
  BrainEvent,
  EntityKind,
  Patch,
  Proposal,
  RawDump,
  Report,
  Session,
  SetupInput,
} from "@/lib/types";

// Baked in at build time (static export). See frontend/.env.example.
const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8080";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public retryable = false,
  ) {
    super(message);
  }
}

/** Every API call carries the signed-in user's Firebase ID token (ADR 0009). */
async function authHeaders(): Promise<Record<string, string>> {
  const token = await idToken();
  if (!token) throw new ApiError("Sign in to continue.", 401);
  return { Authorization: `Bearer ${token}` };
}

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...auth },
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError("Can't reach the server. Check that it's running, then try again.", 0, true);
  }
  if (!res.ok) throw await toApiError(res);
  return (await res.json()) as T;
}

async function toApiError(res: Response): Promise<ApiError> {
  let detail = `Request failed (${res.status})`;
  let retryable = res.status >= 500;
  try {
    const json = await res.json();
    if (typeof json.detail === "string") detail = json.detail;
    if (typeof json.retryable === "boolean") retryable = json.retryable;
  } catch {
    // non-JSON error body; keep the default message
  }
  return new ApiError(detail, res.status, retryable);
}

async function request<T>(method: "GET" | "PATCH" | "DELETE", path: string): Promise<T> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { method, headers: auth });
  } catch {
    throw new ApiError("Can't reach the server. Check that it's running, then try again.", 0, true);
  }
  if (!res.ok) throw await toApiError(res);
  return (await res.json()) as T;
}

// --- The second brain -------------------------------------------------------

export interface EventOut {
  event: BrainEvent;
  brain: Brain;
}

export const getBrain = () => request<Brain>("GET", "/brain");
export const listProposals = () => request<Proposal[]>("GET", "/brain/proposals");
export const getDump = (id: string) => request<RawDump>("GET", `/brain/dumps/${id}`);
export const createDump = (text: string) => post<Proposal>("/brain/dumps", { text });
export const createDumpFromUpload = (resumeObject: string) =>
  post<Proposal>("/brain/dumps/from-upload", { resume_object: resumeObject });
export const confirmProposal = (id: string, patch: Patch) =>
  post<EventOut>(`/brain/proposals/${id}/confirm`, { patch });
export const discardProposal = (id: string) => post<Brain>(`/brain/proposals/${id}/discard`, {});
export const editEntity = (kind: EntityKind, id: string, fields: Record<string, unknown>) =>
  patchJson<EventOut>(`/brain/entities/${kind}/${id}`, { fields });
export const retireEntity = (kind: EntityKind, id: string) =>
  request<EventOut>("DELETE", `/brain/entities/${kind}/${id}`);

async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...auth },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Can't reach the server. Check that it's running, then try again.", 0, true);
  }
  if (!res.ok) throw await toApiError(res);
  return (await res.json()) as T;
}

export function startInterview(sessionId: string, setup: SetupInput): Promise<Session> {
  return post<Session>("/interview/start", { session_id: sessionId, setup });
}

interface UploadTicket {
  object_name: string;
  upload_url: string;
  expires_in_seconds: number;
}

/** Uploads a resume straight to Cloud Storage via a signed URL (ADR 0010) and
 *  returns the object name to pass as `resume_object`. The API never sees the bytes. */
export async function uploadResume(file: File): Promise<string> {
  const ticket = await post<UploadTicket>("/uploads", {
    filename: file.name,
    content_type: file.type,
    size_bytes: file.size,
  });
  let res: Response;
  try {
    res = await fetch(ticket.upload_url, {
      method: "PUT",
      headers: { "Content-Type": file.type },
      body: file,
    });
  } catch {
    throw new ApiError("The upload didn't go through. Check your connection and try again.", 0, true);
  }
  if (!res.ok) throw new ApiError(`The upload was rejected (${res.status}).`, res.status, true);
  return ticket.object_name;
}

export function submitAnswer(session: Session, answer: Answer): Promise<Session> {
  return post<Session>("/interview/answer", { session, answer });
}

export function getReport(session: Session): Promise<Report> {
  return post<Report>("/interview/report", session);
}

/** Streams the interviewer's words for the current question. Calls onToken per
 *  delta; resolves when the server sends `done`; rejects with ApiError on an
 *  `error` event or a non-200 status. */
export async function askQuestion(
  session: Session,
  onToken: (text: string) => void,
  signal: AbortSignal,
): Promise<void> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetch(`${BASE}/interview/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...auth },
      body: JSON.stringify(session),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError("Can't reach the server. Check that it's running, then try again.", 0, true);
  }
  if (!res.ok) throw await toApiError(res);
  if (!res.body) throw new ApiError("Empty response from the API.", 502, true);

  for await (const { event, data } of readSse(res.body)) {
    if (event === "token") {
      onToken((data as { text: string }).text);
    } else if (event === "error") {
      const { message, retryable } = data as { message: string; retryable: boolean };
      throw new ApiError(message, 502, retryable);
    } else if (event === "done") {
      return;
    }
  }
  throw new ApiError("The stream ended before the interviewer finished.", 502, true);
}
