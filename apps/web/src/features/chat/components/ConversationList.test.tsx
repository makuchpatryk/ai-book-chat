import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renameConversation } from "@libs/api/conversations/api";
import type { Conversation } from "@libs/types";
import { ConversationList } from "./ConversationList";

vi.mock("@libs/api/conversations/api", () => ({
  createConversation: vi.fn(),
  deleteConversation: vi.fn(),
  renameConversation: vi.fn(),
}));

const CONVERSATIONS: Conversation[] = [
  { id: "c1", title: "Old title", created_at: "2026-09-01T10:00:00Z" },
];

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

function startRename() {
  render(<ConversationList documentId="d1" conversations={CONVERSATIONS} />, { wrapper });
  fireEvent.click(screen.getByRole("button", { name: "Rename conversation" }));
  return screen.getByLabelText("Conversation title") as HTMLInputElement;
}

describe("ConversationList rename", () => {
  beforeEach(() => {
    vi.mocked(renameConversation).mockReset();
    vi.mocked(renameConversation).mockResolvedValue({ ...CONVERSATIONS[0], title: "x" });
  });

  it("prefills the input and saves the trimmed title on Enter", async () => {
    const input = startRename();
    expect(input.value).toBe("Old title");

    fireEvent.change(input, { target: { value: "  New title  " } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => expect(renameConversation).toHaveBeenCalledWith("c1", "New title"));
    expect(renameConversation).toHaveBeenCalledTimes(1);
    expect(screen.queryByLabelText("Conversation title")).toBeNull();
  });

  it("cancels on Escape without saving, even though unmount may blur", () => {
    const input = startRename();

    fireEvent.change(input, { target: { value: "Changed" } });
    fireEvent.keyDown(input, { key: "Escape" });
    fireEvent.blur(input);

    expect(renameConversation).not.toHaveBeenCalled();
    expect(screen.getByText("Old title")).toBeTruthy();
  });

  it("skips the request when the title is blank", () => {
    const input = startRename();

    fireEvent.change(input, { target: { value: "   " } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(renameConversation).not.toHaveBeenCalled();
  });

  it("skips the request when the title is unchanged", () => {
    const input = startRename();

    fireEvent.keyDown(input, { key: "Enter" });

    expect(renameConversation).not.toHaveBeenCalled();
  });

  it("saves on blur", async () => {
    const input = startRename();

    fireEvent.change(input, { target: { value: "Blurred" } });
    fireEvent.blur(input);

    await waitFor(() => expect(renameConversation).toHaveBeenCalledWith("c1", "Blurred"));
  });
});
