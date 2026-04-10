import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { Markdown } from "@/components/markdown";

describe("Markdown", () => {
  test("renders markdown content", () => {
    render(<Markdown content={"# Heading\n\n**Bold** text with `code`"} />);

    expect(screen.getByRole("heading", { name: "Heading" })).toBeInTheDocument();
    expect(screen.getByText("Bold")).toBeInTheDocument();
    expect(screen.getByText("code")).toBeInTheDocument();
  });
});
