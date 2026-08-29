import { FileText, Layers, Loader2, Mail, Phone } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import CopyButton from "@/components/CopyButton";
import { errorMessage } from "@/lib/api";
import { useProfile } from "@/hooks/useSearch";

export default function ProfileSheet({ profileId, onOpenChange, onResume, resumePending }) {
  const { data: profile, isPending, error } = useProfile(profileId);

  return (
    <Sheet open={Boolean(profileId)} onOpenChange={(open) => !open && onOpenChange(null)}>
      <SheetContent side="right" className="w-full gap-0 sm:max-w-2xl">
        <SheetHeader className="border-b">
          <SheetTitle className="pr-8">
            {isPending ? <Skeleton className="h-5 w-48" /> : profile?.headline || "Candidate"}
          </SheetTitle>

          {profile && (
            <>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
                {profile.email && (
                  <span className="inline-flex items-center gap-1">
                    <Mail className="size-3.5" />
                    {profile.email}
                    <CopyButton value={profile.email} label="email" />
                  </span>
                )}
                {profile.phone && (
                  <span className="inline-flex items-center gap-1">
                    <Phone className="size-3.5" />
                    {profile.phone}
                    <CopyButton value={profile.phone} label="phone" />
                  </span>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2 pt-1">
                <Button size="sm" disabled={resumePending} onClick={() => onResume(profile.id)}>
                  {resumePending ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <FileText className="size-4" />
                  )}
                  Open resume PDF
                </Button>
                {profile.duplicate_count > 1 && (
                  <Badge variant="secondary" className="gap-1">
                    <Layers className="size-3" />
                    {profile.duplicate_count} documents for this person
                  </Badge>
                )}
                {profile.file_name && (
                  <span className="truncate font-mono text-xs text-muted-foreground">
                    {profile.file_name}
                  </span>
                )}
              </div>
            </>
          )}
        </SheetHeader>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          {isPending && (
            <div className="space-y-2">
              {Array.from({ length: 12 }).map((_, i) => (
                <Skeleton key={i} className="h-4" style={{ width: `${60 + ((i * 7) % 40)}%` }} />
              ))}
            </div>
          )}

          {error && (
            <p className="text-sm text-destructive">
              {errorMessage(error, "Could not load this profile.")}
            </p>
          )}

          {profile && (
            <>
              {profile.duplicates?.length > 0 && (
                <div className="mb-4 rounded-md border bg-muted/40 p-3">
                  <p className="text-xs font-medium text-muted-foreground">
                    Other documents for this person
                  </p>
                  <ul className="mt-1.5 space-y-1">
                    {profile.duplicates.map((dup) => (
                      <li key={dup.id} className="truncate font-mono text-xs text-muted-foreground">
                        {dup.file_name || dup.id}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <Separator className="mb-4" />
              <pre className="font-sans text-sm leading-relaxed whitespace-pre-wrap">
                {profile.document}
              </pre>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
