export interface SseFrame {
  event: string;
  data: string;
}

export async function* parseSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseFrame> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (value) {
        buffer += decoder.decode(value, { stream: true });
      }

      if (done) {
        buffer += decoder.decode();
        if (buffer.trim()) {
          const frame = parseFrame(buffer);
          if (frame) yield frame;
        }
        break;
      }

      const parts = buffer.split("\n\n");
      buffer = parts[parts.length - 1];

      for (let i = 0; i < parts.length - 1; i++) {
        const frame = parseFrame(parts[i]);
        if (frame) yield frame;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseFrame(frameStr: string): SseFrame | null {
  const lines = frameStr.trim().split("\n");
  let event = "";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (!event || dataLines.length === 0) return null;

  return {
    event,
    data: dataLines.join("\n"),
  };
}
