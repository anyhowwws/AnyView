import assert from "node:assert/strict";
import { test } from "node:test";
import {
  formatCapture,
  formattedCaptureIsValid,
} from "../lib/capture-templates.ts";

test("formats certification fields into evidence-friendly source text", () => {
  assert.equal(
    formatCapture(
      "certification",
      {
        title: "Professional Cloud Architect",
        issuer: "Google Cloud",
        achieved_on: "2026-09-22",
      },
      "Renewed after the beta exam.",
    ),
    "Certification entry:\n" +
      "Certification title: Professional Cloud Architect\n" +
      "Issuer: Google Cloud\n" +
      "Date earned: 2026-09-22\n" +
      "Additional context: Renewed after the beta exam.",
  );
});

test("requires only the identifying fields in formatted mode", () => {
  assert.equal(formattedCaptureIsValid("certification", {}), false);
  assert.equal(
    formattedCaptureIsValid("certification", { title: "Professional Cloud Architect" }),
    true,
  );
  assert.equal(formattedCaptureIsValid("role", { company: "Example" }), false);
  assert.equal(
    formattedCaptureIsValid("role", { company: "Example", title: "Architect" }),
    true,
  );
});

test("formats feedback fields into evidence-friendly source text", () => {
  assert.equal(
    formatCapture(
      "feedback",
      {
        given_by: "Manager, 2024 review",
        content: "You owned that migration end to end.",
        received_on: "2024-11-01",
      },
      "",
    ),
    "Feedback entry:\n" +
      "Who said it: Manager, 2024 review\n" +
      "What they said: You owned that migration end to end.\n" +
      "When: 2024-11-01",
  );
});

test("feedback requires who said it and what they said", () => {
  assert.equal(formattedCaptureIsValid("feedback", {}), false);
  assert.equal(
    formattedCaptureIsValid("feedback", { given_by: "Manager" }),
    false,
  );
  assert.equal(
    formattedCaptureIsValid("feedback", {
      given_by: "Manager",
      content: "Great work.",
    }),
    true,
  );
});
