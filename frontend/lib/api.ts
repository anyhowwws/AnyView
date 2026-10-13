import { idToken } from "@/lib/auth";
import { readSse } from "@/lib/sse";
import type { ProgressFrame } from "@/lib/ingest-progress";
import type {
  Answer,
  Brain,
  BrainEvent,
  EntityKind,
  JobDocument,
  Patch,
  Proposal,
  QuestionReport,
  RawDump,
  Report,
  ResumeOnFile,
  SavedJob,
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

// Cloud Run scales to zero, and a cold start can take over a minute. While the
// new instance boots, requests are refused at once with a 500 that carries no
// CORS headers, so the browser reports a plain network error. A read is safe to
// repeat, so GETs wait it out: about 75 s in total, then give up.
const COLD_START_DELAYS_MS = [1000, 2000, 4000, 8000, 10000, 10000, 10000, 10000, 10000, 10000];

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function request<T>(method: "GET" | "PATCH" | "DELETE", path: string): Promise<T> {
  // Only GET is retried: repeating a DELETE that half-worked is not our call.
  const delays = method === "GET" ? COLD_START_DELAYS_MS : [];
  for (let attempt = 0; ; attempt++) {
    const auth = await authHeaders(); // fresh token each time; also cheap
    let failure: ApiError;
    try {
      const res = await fetch(`${BASE}${path}`, { method, headers: auth });
      if (res.status === 204) return undefined as T; // a DELETE with nothing to say
      if (res.ok) return (await res.json()) as T;
      failure = await toApiError(res);
    } catch {
      failure = new ApiError("Can't reach the server. Check that it's running, then try again.", 0, true);
    }
    // 4xx (other than 429) will not change on a retry.
    const transient = failure.status === 0 || failure.status === 429 || failure.status >= 500;
    if (!transient || attempt >= delays.length) throw failure;
    await sleep(delays[attempt]);
  }
}

// --- The Digital Garden -----------------------------------------------------

export interface EventOut {
  event: BrainEvent;
  brain: Brain;
}

/** Erase everything stored about the signed-in user (ADR 0018). The server
 *  checks the same phrase the user typed. */
export const eraseAccount = () =>
  post<{ files: number; rows: number }>("/account/erase", { confirm: "delete my data" });

export const getBrain = () => request<Brain>("GET", "/brain");
export const listProposals = () => request<Proposal[]>("GET", "/brain/proposals");
export const getDump = (id: string) => request<RawDump>("GET", `/brain/dumps/${id}`);
export const createDump = (text: string) => post<Proposal>("/brain/dumps", { text });
export const createDumpFromUpload = (resumeObject: string) =>
  post<Proposal>("/brain/dumps/from-upload", { resume_object: resumeObject });

/** `createDump`, streamed: reports each step through onProgress (ADR 0019). */
export const streamDump = (text: string, onProgress: (frame: ProgressFrame) => void) =>
  streamProposal("/brain/dumps/stream", { text }, onProgress);

/** `createDumpFromUpload`, streamed. */
export const streamDumpFromUpload = (resumeObject: string, onProgress: (frame: ProgressFrame) => void) =>
  streamProposal("/brain/dumps/from-upload/stream", { resume_object: resumeObject }, onProgress);

async function streamProposal(
  path: string,
  body: unknown,
  onProgress: (frame: ProgressFrame) => void,
): Promise<Proposal> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...auth },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Can't reach the server. Check that it's running, then try again.", 0, true);
  }
  if (!res.ok) throw await toApiError(res);
  if (!res.body) throw new ApiError("Empty response from the API.", 502, true);

  let proposal: Proposal | null = null;
  for await (const { event, data } of readSse(res.body)) {
    if (event === "progress") {
      onProgress(data as ProgressFrame);
    } else if (event === "proposal") {
      proposal = data as Proposal;
    } else if (event === "error") {
      const { message, status, retryable } = data as { message: string; status?: number; retryable: boolean };
      throw new ApiError(message, status ?? 502, retryable);
    } else if (event === "done") {
      if (proposal) return proposal;
      break;
    }
  }
  throw new ApiError("The connection closed before Donna finished. Please try again.", 502, true);
}
export const confirmProposal = (id: string, patch: Patch) =>
  post<EventOut>(`/brain/proposals/${id}/confirm`, { patch });
export const discardProposal = (id: string) => post<Brain>(`/brain/proposals/${id}/discard`, {});
/** An entry typed into a form: confirmed at once, no model, no review (ADR 0022). */
export const addEntity = (kind: EntityKind, fields: Record<string, unknown>) =>
  post<EventOut>(`/brain/entities/${kind}`, { fields });
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

/** The resume an interviewer would have received, if we already have one
 *  (ADR 0014). `dump_id === null` means the form must ask for it. */
export const getResumeOnFile = () => request<ResumeOnFile>("GET", "/interview/resume");

/** Reads an uploaded job description and hands back its text plus the fields
 *  it suggests for the form. Nothing here is used until you confirm it. */
export const parseJob = (objectName: string) =>
  post<JobDocument>("/interview/job/parse", { object_name: objectName });

/** The same, for a posting at a link: the API fetches the page (ADR 0027). */
export const parseJobLink = (url: string) =>
  post<JobDocument>("/interview/job/parse-link", { url });

/** The jobs you have practised for, most recently used first (ADR 0025). */
export const getSavedJobs = () => request<SavedJob[]>("GET", "/interview/jobs");

export const deleteSavedJob = (id: string) =>
  request<void>("DELETE", `/interview/jobs/${encodeURIComponent(id)}`);

interface UploadTicket {
  object_name: string;
  upload_url: string;
  expires_in_seconds: number;
}

/** PUTs bytes to the URL a ticket handed back. Normally that is a signed
 *  Cloud Storage URL and the API never sees the bytes (ADR 0010). In local
 *  fake mode it is a relative path back to the API, which needs the usual
 *  auth header; a signed URL carries its own credentials and must not. */
async function putTicket(ticket: UploadTicket, body: Blob, contentType: string): Promise<string> {
  const relative = ticket.upload_url.startsWith("/");
  const headers: Record<string, string> = { "Content-Type": contentType };
  let res: Response;
  try {
    res = await fetch(relative ? `${BASE}${ticket.upload_url}` : ticket.upload_url, {
      method: "PUT",
      headers: relative ? { ...headers, ...(await authHeaders()) } : headers,
      body,
    });
  } catch {
    throw new ApiError("The upload didn't go through. Check your connection and try again.", 0, true);
  }
  if (!res.ok) throw new ApiError(`The upload was rejected (${res.status}).`, res.status, true);
  return ticket.object_name;
}

/** Uploads a resume straight to Cloud Storage via a signed URL (ADR 0010) and
 *  returns the object name to pass as `resume_object`. */
export async function uploadResume(file: File): Promise<string> {
  const ticket = await post<UploadTicket>("/uploads", {
    filename: file.name,
    content_type: file.type,
    size_bytes: file.size,
  });
  return putTicket(ticket, file, file.type);
}

/** Uploads a recorded answer the same way, under the user's `audio/` prefix
 *  (ADR 0013), and returns the object name to transcribe. */
export async function uploadAnswerAudio(blob: Blob, contentType: string): Promise<string> {
  const ticket = await post<UploadTicket>("/uploads", {
    filename: "answer",
    content_type: contentType,
    size_bytes: blob.size,
  });
  return putTicket(ticket, blob, contentType);
}

/** Harvey's fixed interjections, fetched once and reused for the whole run: the
 *  same "let's move on" is needed up to five times in an interview and the
 *  words never change. The line is a key, not text — the server owns the
 *  words. A failing voice here must not stop the interview, so a failure is
 *  silence rather than an error. */
const clips = new Map<string, string>();

export async function interjection(
  sessionId: string,
  line: "time_up" | "stalled" | "hello",
): Promise<string | null> {
  const cached = clips.get(line);
  if (cached !== undefined) return cached;
  try {
    const { b64 } = await post<{ b64: string }>("/interview/say", {
      session_id: sessionId,
      line,
    });
    clips.set(line, b64);
    return b64;
  } catch {
    return null;
  }
}

/** Turns an uploaded recording into the words that were said. */
export async function transcribeAnswer(sessionId: string, objectName: string): Promise<string> {
  const { text } = await post<{ text: string }>("/interview/transcribe", {
    session_id: sessionId,
    object_name: objectName,
  });
  return text;
}

export function submitAnswer(session: Session, answer: Answer): Promise<Session> {
  return post<Session>("/interview/answer", { session, answer });
}

export function getReport(session: Session): Promise<Report> {
  return post<Report>("/interview/report", session);
}

export interface ReportHandlers {
  /** The report's header (company, room, garden_used), sent at once with no items. */
  onHeader?: (header: Report) => void;
  /** One scored question, in finishing order; `index` is its position. */
  onItem: (index: number, item: QuestionReport) => void;
}

/** `getReport`, streamed: each question arrives as soon as it is scored, so the
 *  report fills in while you read it. Resolves with the whole report in
 *  question order. */
export async function streamReport(session: Session, handlers: ReportHandlers): Promise<Report> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetch(`${BASE}/interview/report/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...auth },
      body: JSON.stringify(session),
    });
  } catch {
    throw new ApiError("Can't reach the server. Check that it's running, then try again.", 0, true);
  }
  if (!res.ok) throw await toApiError(res);
  if (!res.body) throw new ApiError("Empty response from the API.", 502, true);

  let header: Report | null = null;
  const items: (QuestionReport | null)[] = session.questions.map(() => null);
  for await (const { event, data } of readSse(res.body)) {
    if (event === "report") {
      header = data as Report;
      handlers.onHeader?.(header);
    } else if (event === "item") {
      const { index, item } = data as { index: number; item: QuestionReport };
      items[index] = item;
      handlers.onItem(index, item);
    } else if (event === "error") {
      const { message, retryable } = data as { message: string; retryable: boolean };
      throw new ApiError(message, 502, retryable);
    } else if (event === "done") {
      if (header && items.every((item) => item !== null)) {
        return { ...header, items: items as QuestionReport[] };
      }
      break;
    }
  }
  throw new ApiError("The connection closed before scoring finished. Please try again.", 502, true);
}

export interface AskHandlers {
  onToken: (text: string) => void;
  /** Voice mode only: one base64 WAV clip per sentence, in speaking order. */
  onAudio?: (b64: string) => void;
  /** Voice mode only: synthesis failed, so no audio is coming. */
  onVoiceOff?: (message: string) => void;
}

/** Streams the interviewer's words for the current question. Calls onToken per
 *  delta; resolves when the server sends `done`; rejects with ApiError on an
 *  `error` event or a non-200 status. With `voice`, the same stream also
 *  carries Harvey's spoken audio (ADR 0013). */
export async function askQuestion(
  session: Session,
  handlers: AskHandlers,
  signal: AbortSignal,
  voice = false,
): Promise<void> {
  const { onToken, onAudio, onVoiceOff } = handlers;
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetch(`${BASE}/interview/ask${voice ? "?voice=true" : ""}`, {
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
    } else if (event === "audio") {
      onAudio?.((data as { b64: string }).b64);
    } else if (event === "voice_off") {
      onVoiceOff?.((data as { message: string }).message);
    } else if (event === "error") {
      const { message, retryable } = data as { message: string; retryable: boolean };
      throw new ApiError(message, 502, retryable);
    } else if (event === "done") {
      return;
    }
  }
  throw new ApiError("The stream ended before the interviewer finished.", 502, true);
}

export interface DiscoverTurn {
  role: "user" | "donna";
  text: string;
}

/** An entry Donna's answer cites, resolved by the server (ADR 0017). */
export interface Citation {
  label: string;
  id: string;
  kind: EntityKind;
}

/** Asks Donna about the confirmed garden. Streams her words through onToken;
 *  resolves with the entries the answer cites once the server sends `done`. */
export async function askDonna(
  conversationId: string,
  question: string,
  history: DiscoverTurn[],
  onToken: (text: string) => void,
  signal: AbortSignal,
): Promise<Citation[]> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetch(`${BASE}/brain/discover`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...auth },
      body: JSON.stringify({ conversation_id: conversationId, question, history }),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError("Can't reach the server. Check that it's running, then try again.", 0, true);
  }
  if (!res.ok) throw await toApiError(res);
  if (!res.body) throw new ApiError("Empty response from the API.", 502, true);

  let citations: Citation[] = [];
  for await (const { event, data } of readSse(res.body)) {
    if (event === "token") {
      onToken((data as { text: string }).text);
    } else if (event === "citations") {
      citations = (data as { entities: Citation[] }).entities;
    } else if (event === "error") {
      const { message, retryable } = data as { message: string; retryable: boolean };
      throw new ApiError(message, 502, retryable);
    } else if (event === "done") {
      return citations;
    }
  }
  throw new ApiError("The stream ended before Donna finished.", 502, true);
}
