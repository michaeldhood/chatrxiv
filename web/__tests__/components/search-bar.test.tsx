import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { SearchBar } from "@/components/search-bar";
import { ToastProvider } from "@/components/toast";

vi.mock("@/lib/api", () => ({
  instantSearch: vi.fn(async (query: string) => ({
    query,
    count: 1,
    results: [
      {
        id: 1,
        title: "Python search chat",
        mode: "chat",
        created_at: "2026-04-01T12:00:00",
        messages_count: 2,
        snippet: "Python result",
        tags: [],
      },
    ],
  })),
}));

function renderSearchBar() {
  return render(
    <ToastProvider>
      <SearchBar />
    </ToastProvider>
  );
}

describe("SearchBar", () => {
  test("renders and accepts input", () => {
    renderSearchBar();

    const input = screen.getByPlaceholderText(/search chats/i);
    fireEvent.change(input, { target: { value: "py" } });

    expect(input).toHaveValue("py");
  });

  test("triggers instant search and shows results", async () => {
    renderSearchBar();

    const input = screen.getByPlaceholderText(/search chats/i);
    fireEvent.change(input, { target: { value: "py" } });

    await waitFor(() => {
      expect(screen.getByText("Python search chat")).toBeInTheDocument();
    });
  });
});
