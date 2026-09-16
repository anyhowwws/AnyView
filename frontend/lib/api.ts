import { readSse } from "@/lib/sse";
import type { Answer, Report, Session, Setup } from "@/lib/types";

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

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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

export function startInterview(sessionId: string, setup: Setup): Promise<Session> {
  return post<Session>("/interview/start", { session_id: sessionId, setup });
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
  let res: Response;
  try {
    res = await fetch(`${BASE}/interview/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
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
