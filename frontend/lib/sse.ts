// A minimal server-sent-events reader over fetch (ADR 0005, 0006).
// EventSource can't POST, and every interview turn posts the session, so we
// read the response body ourselves and split it into frames.

export interface SseEvent {
  event: string;
  data: unknown;
}

export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let event = "message";
  let data = "";

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let newline: number;
    while ((newline = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, newline).replace(/\r$/, "");
      buffer = buffer.slice(newline + 1);

      if (line === "") {
        // Blank line ends a frame. Comment-only frames (": ping") have no data.
        if (data !== "") {
          yield { event, data: JSON.parse(data) };
        }
        event = "message";
        data = "";
      } else if (line.startsWith(":")) {
        // comment / heartbeat — ignore
      } else if (line.startsWith("event:")) {
        event = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        data += line.slice(5).trim();
      }
    }
  }
}
