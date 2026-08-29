import { FileText, Layers, Mail, Phone } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import CopyButton from "@/components/CopyButton";
import { useUiStore } from "@/stores/uiStore";

export default function ResultCard({ hit, onOpen, onResume, onPrefetch, resumePending }) {
  const showScores = useUiStore((s) => s.showScores);

  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={() => onOpen(hit.id)}
      onMouseEnter={() => onPrefetch?.(hit.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen(hit.id);
        }
      }}
      className="cursor-pointer gap-0 p-4 transition-colors hover:border-foreground/25 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h3 className="font-medium">{hit.headline || "Name not found in resume"}</h3>

        {showScores && (
          <Tooltip>
            <TooltipTrigger render={<span className="font-mono text-xs text-muted-foreground" />}>
              {hit.score.toFixed(4)}
            </TooltipTrigger>
            <TooltipContent>Cosine similarity to your query</TooltipContent>
          </Tooltip>
        )}

        {hit.collapsed && (
          <Badge variant="secondary" className="gap-1">
            <Layers className="size-3" />
            {hit.duplicate_count} copies
          </Badge>
        )}
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
        {hit.email && (
          <span className="inline-flex items-center gap-1">
            <Mail className="size-3.5 shrink-0" />
            <span className="truncate">{hit.email}</span>
            <CopyButton value={hit.email} label="email" />
          </span>
        )}
        {hit.phone && (
          <span className="inline-flex items-center gap-1">
            <Phone className="size-3.5 shrink-0" />
            {hit.phone}
            <CopyButton value={hit.phone} label="phone" />
          </span>
        )}
      </div>

      <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">{hit.snippet}</p>

      <div className="mt-3 flex gap-2">
        <Button
          size="sm"
          variant="secondary"
          onClick={(e) => {
            e.stopPropagation();
            onOpen(hit.id);
          }}
        >
          Open profile
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={resumePending}
          onClick={(e) => {
            e.stopPropagation();
            onResume(hit.id);
          }}
        >
          <FileText className="size-4" />
          Resume PDF
        </Button>
      </div>
    </Card>
  );
}
