import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { Message } from "@/components/message";

describe("Message", () => {
  test("renders a user message", () => {
    render(
      <Message
        message={{
          role: "user",
          text: "Hello from the user",
          message_type: "response",
          created_at: "2026-04-01T12:00:00",
        }}
      />
    );

    expect(screen.getByText("User")).toBeInTheDocument();
    expect(screen.getByText("Hello from the user")).toBeInTheDocument();
  });

  test("renders an assistant thinking message", () => {
    render(
      <Message
        message={{
          role: "assistant",
          text: "Working through the answer",
          message_type: "thinking",
          created_at: "2026-04-01T12:05:00",
        }}
      />
    );

    expect(screen.getByText("Assistant")).toBeInTheDocument();
    expect(screen.getByText(/Thinking/i)).toBeInTheDocument();
    expect(screen.getByText("Working through the answer")).toBeInTheDocument();
  });
});
