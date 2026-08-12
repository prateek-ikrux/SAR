"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { SearchResult } from "@/lib/api";

const NAME_KEYS = ["name", "full_name", "fullName", "candidate_name", "candidateName"];
const TITLE_KEYS = ["title", "role", "position", "headline", "job_title", "jobTitle"];
const EMAIL_KEYS = ["email", "email_address", "contact_email"];
const LOCATION_KEYS = ["location", "city", "address"];
const SUMMARY_KEYS = ["summary", "about", "description", "bio", "overview"];
const SKILLS_KEYS = ["skills", "tags", "keywords", "technologies"];

// Resume text extracted into a "document" blob usually has a "Name" label on
// its own line (e.g. "Name :\n\nJohn Smith" or "Name\n\nJohn Smith"), or the
// name as the very first markdown heading. Both are noisy, so we validate
// whatever we find against NON_NAME_WORDS before trusting it.
const NAME_LABEL_LINE = /^[ \t]*(?:full\s+|candidate\s+)?name[ \t]*:?[ \t]*(.*)$/i;
const NON_NAME_WORDS = new Set([
  "resume",
  "curriculum",
  "vitae",
  "profile",
  "detail",
  "details",
  "not",
  "mentioned",
  "na",
  "none",
  "unknown",
  // Common resume section headings, so the bare-heading fallback doesn't
  // mistake e.g. "## Executive Summary" for a person's name.
  "executive",
  "summary",
  "objective",
  "career",
  "personal",
  "professional",
  "contact",
  "education",
  "experience",
  "experiences",
  "skills",
  "employment",
  "declaration",
  "annexure",
  "certificate",
  "certification",
  "certifications",
  "project",
  "projects",
  "reference",
  "references",
  "overview",
  "background",
  "qualification",
  "qualifications",
  "achievement",
  "achievements",
  "interest",
  "interests",
  "hobbies",
  "language",
  "languages",
  "address",
  "information",
  "info",
]);

function isPlausibleNameToken(word: string): boolean {
  return (
    /^[A-Za-z][A-Za-z.'-]*$/.test(word) &&
    !NON_NAME_WORDS.has(word.toLowerCase().replace(/[^a-z]/g, ""))
  );
}

// Values sitting next to an explicit "Name" label are trustworthy even as a
// single token (e.g. "CH.R.KARTEEK"), since the label itself is the signal.
function looksLikeLabeledName(candidate: string): boolean {
  const trimmed = candidate.trim();
  if (trimmed.length < 2 || trimmed.length > 60) return false;
  const words = trimmed.split(/\s+/);
  return words.length <= 6 && words.every(isPlausibleNameToken);
}

// A bare heading has no such label, so require at least two words to cut
// down on false positives like "## Summary" or "## Objective".
function looksLikeHeadingName(candidate: string): boolean {
  const trimmed = candidate.trim();
  return trimmed.split(/\s+/).length >= 2 && looksLikeLabeledName(trimmed);
}

function extractNameFromDocument(document: string): string | null {
  const lines = document.replace(/\t/g, " ").split(/\r?\n/);

  for (let i = 0; i < lines.length; i++) {
    const match = lines[i].match(NAME_LABEL_LINE);
    if (!match) continue;

    const sameLineValue = match[1].replace(/\s+/g, " ").trim();
    if (sameLineValue && looksLikeLabeledName(sameLineValue)) return sameLineValue;
    if (sameLineValue) continue; // labeled line already had a value, just not a valid name

    for (let j = i + 1; j < Math.min(i + 4, lines.length); j++) {
      const candidate = lines[j].replace(/\s+/g, " ").trim();
      if (!candidate) continue;
      if (looksLikeLabeledName(candidate)) return candidate;
      break;
    }
  }

  const heading = document.match(/^#+\s*(.+)$/m);
  if (heading) {
    const candidate = heading[1].replace(/\s+/g, " ").trim();
    if (looksLikeHeadingName(candidate)) return candidate;
  }

  return null;
}

// Generic "Label: value" extraction for the structured cover-page fields
// these resume exports tend to share (Current Designation, Key Skills,
// Total Experience, ...). A value can wrap onto the following lines (PDF
// extraction often breaks long lists mid-line), so we keep consuming lines
// until a blank line or the next "Label:" line ends the field.
const LABEL_LINE = /^[ \t]*([A-Za-z][A-Za-z .()/&-]{1,40}?)[ \t]*:[ \t]*(.*)$/;
const NOT_MEANINGFUL_VALUE = /^(not\s*(applicable|mentioned)|n\.?\/?a\.?|none|nil|-+)$/i;

function isMeaningfulValue(value: string): boolean {
  return value.length > 0 && !NOT_MEANINGFUL_VALUE.test(value);
}

function extractLabeledField(document: string, label: string): string | null {
  const lines = document.replace(/\t/g, " ").split(/\r?\n/);
  const wanted = label.toLowerCase();

  for (let i = 0; i < lines.length; i++) {
    const match = lines[i].match(LABEL_LINE);
    if (!match || match[1].trim().toLowerCase() !== wanted) continue;

    const parts = [match[2].trim()];
    for (let j = i + 1; j < Math.min(i + 6, lines.length); j++) {
      const line = lines[j].trim();
      if (!line || LABEL_LINE.test(lines[j])) break;
      parts.push(line);
    }

    const value = parts.join(" ").replace(/\s+/g, " ").trim();
    if (isMeaningfulValue(value)) return value;
  }
  return null;
}

function extractSkillsFromDocument(document: string): string[] | null {
  const raw = extractLabeledField(document, "key skills");
  if (!raw) return null;
  const skills = raw
    .split(",")
    .map((skill) => skill.trim())
    .filter((skill) => skill.length > 0 && skill.length <= 40);
  return skills.length > 0 ? skills.slice(0, 15) : null;
}

function pickString(profile: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = profile[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

function pickStringArray(profile: Record<string, unknown>, keys: string[]): string[] | null {
  for (const key of keys) {
    const value = profile[key];
    if (Array.isArray(value) && value.every((item) => typeof item === "string")) {
      return value as string[];
    }
  }
  return null;
}

export function ProfileCard({ result }: { result: SearchResult }) {
  const [showRaw, setShowRaw] = useState(false);
  const { profile } = result;

  const documentText = typeof profile.document === "string" ? profile.document : null;

  const name =
    pickString(profile, NAME_KEYS) ?? (documentText ? extractNameFromDocument(documentText) : null);
  const title =
    pickString(profile, TITLE_KEYS) ??
    (documentText &&
      (extractLabeledField(documentText, "current designation") ??
        extractLabeledField(documentText, "role")));
  const email = pickString(profile, EMAIL_KEYS);
  const location =
    pickString(profile, LOCATION_KEYS) ??
    (documentText ? extractLabeledField(documentText, "current location") : null);
  const summary = pickString(profile, SUMMARY_KEYS);
  const skills =
    pickStringArray(profile, SKILLS_KEYS) ??
    (documentText ? extractSkillsFromDocument(documentText) : null);
  const experience = documentText ? extractLabeledField(documentText, "total experience") : null;

  const usedKeys = new Set(
    [
      name && NAME_KEYS,
      title && TITLE_KEYS,
      email && EMAIL_KEYS,
      location && LOCATION_KEYS,
      summary && SUMMARY_KEYS,
      skills && SKILLS_KEYS,
    ]
      .filter(Boolean)
      .flat() as string[],
  );
  const remainingEntries = Object.entries(profile).filter(([key]) => !usedKeys.has(key));

  const matchPct = Math.max(0, Math.min(100, result.score * 100));

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
        <div className="min-w-0">
          <div className="truncate font-semibold leading-tight">
            {name ?? title ?? "Untitled profile"}
          </div>
          {name && title && (
            <div className="truncate text-sm text-muted-foreground">{title}</div>
          )}
          {(email || location || experience) && (
            <div className="mt-1 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
              {email && <span>{email}</span>}
              {location && <span>{location}</span>}
              {experience && <span>{experience} experience</span>}
            </div>
          )}
        </div>
        <Badge variant="secondary" className="shrink-0">
          {matchPct.toFixed(1)}% match
        </Badge>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {summary && <p className="text-sm text-foreground/90">{summary}</p>}
        {skills && skills.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {skills.map((skill) => (
              <Badge key={skill} variant="outline">
                {skill}
              </Badge>
            ))}
          </div>
        )}

        <button
          type="button"
          onClick={() => setShowRaw((current) => !current)}
          className="flex items-center gap-1 self-start text-xs text-muted-foreground hover:text-foreground"
        >
          {showRaw ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
          {showRaw ? "Hide full profile" : "View full profile"}
        </button>

        {showRaw && remainingEntries.length > 0 && (
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 rounded-md bg-muted p-3 text-xs">
            {remainingEntries.map(([key, value]) => (
              <div key={key} className="contents">
                <dt className="font-medium text-muted-foreground">{key}</dt>
                <dd className="break-words">
                  {typeof value === "string" || typeof value === "number"
                    ? String(value)
                    : JSON.stringify(value)}
                </dd>
              </div>
            ))}
          </dl>
        )}
        {showRaw && remainingEntries.length === 0 && (
          <p className="rounded-md bg-muted p-3 text-xs text-muted-foreground">
            No additional fields on this profile.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
