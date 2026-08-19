import { describe, expect, it } from "vitest";
import { parseSse } from "@/api/sse";

function streamFromString(str: string): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(str));
      controller.close();
    },
  });
}

describe("parseSse", () => {
  it("parses a single frame", async () => {
    const stream = streamFromString("event: token\ndata: hello\n\n");
    const frames: { event: string; data: string }[] = [];

    for await (const frame of parseSse(stream)) {
      frames.push(frame);
    }

    expect(frames).toEqual([{ event: "token", data: "hello" }]);
  });

  it("parses multiple frames", async () => {
    const stream = streamFromString("event: token\ndata: hello\n\nevent: token\ndata: world\n\n");
    const frames: { event: string; data: string }[] = [];

    for await (const frame of parseSse(stream)) {
      frames.push(frame);
    }

    expect(frames).toHaveLength(2);
    expect(frames[0]).toEqual({ event: "token", data: "hello" });
    expect(frames[1]).toEqual({ event: "token", data: "world" });
  });

  it("handles multi-byte UTF-8 split across chunks", async () => {
    const encoder = new TextEncoder();
    const text = "event: token\ndata: café\n\n";
    const bytes = encoder.encode(text);

    let stream: ReadableStream<Uint8Array> | null = null;
    stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, 15));
        controller.enqueue(bytes.slice(15));
        controller.close();
      },
    });

    const frames: { event: string; data: string }[] = [];
    for await (const frame of parseSse(stream)) {
      frames.push(frame);
    }

    expect(frames[0]?.data).toEqual("café");
  });

  it("handles multiple data: lines per frame", async () => {
    const stream = streamFromString("event: sources\ndata: line1\ndata: line2\n\n");
    const frames: { event: string; data: string }[] = [];

    for await (const frame of parseSse(stream)) {
      frames.push(frame);
    }

    expect(frames[0]?.data).toEqual("line1\nline2");
  });

  it("tolerates leading space after colon", async () => {
    const stream = streamFromString("event: token\ndata:  hello with space\n\n");
    const frames: { event: string; data: string }[] = [];

    for await (const frame of parseSse(stream)) {
      frames.push(frame);
    }

    expect(frames[0]?.data).toEqual("hello with space");
  });

  it("handles trailing data without terminating blank line", async () => {
    const stream = streamFromString("event: token\ndata: final");
    const frames: { event: string; data: string }[] = [];

    for await (const frame of parseSse(stream)) {
      frames.push(frame);
    }

    expect(frames).toEqual([{ event: "token", data: "final" }]);
  });

  it("ignores frames without event field", async () => {
    const stream = streamFromString("data: orphan\n\nevent: token\ndata: valid\n\n");
    const frames: { event: string; data: string }[] = [];

    for await (const frame of parseSse(stream)) {
      frames.push(frame);
    }

    expect(frames).toEqual([{ event: "token", data: "valid" }]);
  });

  it("handles JSON data in frames", async () => {
    const json = JSON.stringify({ pages: [1, 2, 3] });
    const stream = streamFromString(`event: sources\ndata: ${json}\n\n`);
    const frames: { event: string; data: string }[] = [];

    for await (const frame of parseSse(stream)) {
      frames.push(frame);
    }

    expect(frames[0]?.data).toEqual(json);
    expect(JSON.parse(frames[0]?.data || "")).toEqual({ pages: [1, 2, 3] });
  });
});
