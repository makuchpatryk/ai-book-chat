import { describe, expect, it } from "vitest";
import { parseAnswer } from "./parseAnswer";

describe("parseAnswer", () => {
  it("returns the whole content when there is no marker", () => {
    expect(parseAnswer("Just an answer [p.3].")).toEqual({
      body: "Just an answer [p.3].",
      followUps: [],
    });
  });

  it("splits follow-up questions off the body", () => {
    const content = "## Cel\n\nOdpowiedź.\n\n---\nFOLLOW-UPS:\n- Pytanie jeden?\n- Pytanie dwa?\n";
    expect(parseAnswer(content)).toEqual({
      body: "## Cel\n\nOdpowiedź.",
      followUps: ["Pytanie jeden?", "Pytanie dwa?"],
    });
  });

  it("tolerates a bold or heading marker and numbered items", () => {
    const content = "Body.\n\n**Follow-ups:**\n1. **First?**\n2) Second?";
    expect(parseAnswer(content).followUps).toEqual(["First?", "Second?"]);
    expect(parseAnswer("Body.\n### Follow-up questions\n- A?").followUps).toEqual(["A?"]);
  });

  it("hides a marker that is still streaming in", () => {
    expect(parseAnswer("Body.\n\nFOLLOW-UPS:\n- Half a qu")).toEqual({
      body: "Body.",
      followUps: ["Half a qu"],
    });
  });
});
