import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export default function CopyButton({ value, label = "value", className }) {
  const [copied, setCopied] = useState(false);
  if (!value) return null;

  async function copy(event) {
    event.stopPropagation();
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      toast.error("Your browser blocked clipboard access.");
    }
  }

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className={className ?? "size-6 text-muted-foreground"}
            onClick={copy}
            aria-label={`Copy ${label}`}
          />
        }
      >
        {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      </TooltipTrigger>
      <TooltipContent>{copied ? "Copied" : `Copy ${label}`}</TooltipContent>
    </Tooltip>
  );
}
