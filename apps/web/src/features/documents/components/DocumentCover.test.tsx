import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { DocumentCover } from "./DocumentCover";

it("renders the cover image from the API when the document has one", () => {
  render(<DocumentCover documentId="doc-1" hasCover alt="Cover of A Book" />);

  const img = screen.getByAltText("Cover of A Book");
  expect(img).toHaveAttribute("src", "/api/documents/doc-1/cover");
  expect(img).toHaveAttribute("loading", "lazy");
});

it("shows a placeholder instead of an image when there is no cover", () => {
  render(<DocumentCover documentId="doc-1" hasCover={false} alt="Cover of A Book" />);

  expect(screen.queryByAltText("Cover of A Book")).not.toBeInTheDocument();
  expect(screen.getByLabelText("No cover")).toBeInTheDocument();
});

it("falls back to the placeholder when the image fails to load", () => {
  render(<DocumentCover documentId="doc-1" hasCover alt="Cover of A Book" />);

  fireEvent.error(screen.getByAltText("Cover of A Book"));

  expect(screen.queryByAltText("Cover of A Book")).not.toBeInTheDocument();
  expect(screen.getByLabelText("No cover")).toBeInTheDocument();
});
