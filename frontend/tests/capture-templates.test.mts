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
