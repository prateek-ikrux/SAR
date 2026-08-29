import logoDark from "@/assets/ikrux-logo-dark.png";
import logoLight from "@/assets/ikrux-logo.png";
import { cn } from "@/lib/utils";

/**
 * The ikrux wordmark.
 *
 * Two files rather than a CSS filter: the mark is near-black with a teal accent,
 * so `invert()` would turn the teal pink. The dark variant lifts only the black
 * strokes to near-white and leaves the accent alone.
 *
 * Swapped on the `.dark` class, not `prefers-color-scheme`, because the theme
 * can be set manually and must not follow the OS when it has been.
 *
 * Both files are cropped to the mark itself - the source is a 500x500 canvas
 * with the wordmark in a 254x50 band, which renders tiny at any header height.
 */
export default function Logo({ className, showProduct = true }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <img src={logoLight} alt="ikrux" className="block h-5 w-auto shrink-0 dark:hidden" />
      <img
        src={logoDark}
        alt="ikrux"
        className="hidden h-5 w-auto shrink-0 dark:block"
        aria-hidden="true"
      />
      {showProduct && (
        <span className="border-l pl-2.5 text-sm text-muted-foreground">Candidate Search</span>
      )}
    </div>
  );
}
