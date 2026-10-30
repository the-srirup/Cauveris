import React, { useState } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Dialog } from "@/components/ui/Dialog";

function FormInDialog() {
  const [title, setTitle] = useState("");
  const [system, setSystem] = useState("default-system");
  const [description, setDescription] = useState("");

  return (
    <Dialog open={true} onClose={() => {}} title="Create Incident">
      <div>
        <label htmlFor="test-title">Title</label>
        <input
          id="test-title"
          data-testid="input-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />

        <label htmlFor="test-system">System</label>
        <input
          id="test-system"
          data-testid="input-system"
          value={system}
          onChange={(e) => setSystem(e.target.value)}
        />

        <label htmlFor="test-desc">Description</label>
        <textarea
          id="test-desc"
          data-testid="input-desc"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
    </Dialog>
  );
}

describe("Dialog Focus Stability Regression Tests", () => {
  it("does not shift or steal focus while typing into inputs inside Dialog", () => {
    render(<FormInDialog />);

    const titleInput = screen.getByTestId("input-title") as HTMLInputElement;
    const systemInput = screen.getByTestId("input-system") as HTMLInputElement;
    const descInput = screen.getByTestId("input-desc") as HTMLTextAreaElement;

    // Focus on title input
    titleInput.focus();
    expect(document.activeElement).toBe(titleInput);

    // Simulate typing sequential characters: each change triggers state update and re-render
    for (const char of "Navigation Failure") {
      fireEvent.change(titleInput, { target: { value: titleInput.value + char } });
      // Crucial: focus must remain on titleInput and NOT be stolen by the close button or first element
      expect(document.activeElement).toBe(titleInput);
    }
    expect(titleInput.value).toBe("Navigation Failure");

    // Focus on second input (system identifier)
    systemInput.focus();
    expect(document.activeElement).toBe(systemInput);

    // Simulate typing into second input: focus must stay on systemInput, NOT jump to title or close button
    for (const char of "-AMR-02") {
      fireEvent.change(systemInput, { target: { value: systemInput.value + char } });
      expect(document.activeElement).toBe(systemInput);
    }
    expect(systemInput.value).toBe("default-system-AMR-02");

    // Focus on description textarea
    descInput.focus();
    expect(document.activeElement).toBe(descInput);

    // Simulate typing into textarea
    for (const char of "Worker OOM") {
      fireEvent.change(descInput, { target: { value: descInput.value + char } });
      expect(document.activeElement).toBe(descInput);
    }
    expect(descInput.value).toBe("Worker OOM");
  });
});
