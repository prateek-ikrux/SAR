"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import { ApiError, requestOtp, verifyOtp } from "@/lib/api";
import { RedirectIfAuthed } from "@/components/auth/require-auth";

const RESEND_COOLDOWN_SECONDS = 60;

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();

  const [step, setStep] = useState<"email" | "code">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [codeError, setCodeError] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);

  const cooldownInterval = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (cooldownInterval.current) clearInterval(cooldownInterval.current);
    };
  }, []);

  function startCooldown() {
    setCooldown(RESEND_COOLDOWN_SECONDS);
    if (cooldownInterval.current) clearInterval(cooldownInterval.current);
    cooldownInterval.current = setInterval(() => {
      setCooldown((current) => {
        if (current <= 1) {
          if (cooldownInterval.current) clearInterval(cooldownInterval.current);
          return 0;
        }
        return current - 1;
      });
    }, 1000);
  }

  async function sendOtp() {
    setIsSubmitting(true);
    try {
      await requestOtp(email.trim().toLowerCase());
      setStep("code");
      setCode("");
      setCodeError(null);
      startCooldown();
      toast.info("If that email is registered, a 6-digit code is on its way.");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Something went wrong.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleEmailSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!email.trim() || isSubmitting) return;
    await sendOtp();
  }

  async function handleCodeSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (code.length !== 6 || isSubmitting) return;

    setIsSubmitting(true);
    setCodeError(null);
    try {
      const token = await verifyOtp(email.trim().toLowerCase(), code);
      login(token.access_token);
      router.replace("/");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setCodeError("Invalid or expired code. Try again or resend.");
        setCode("");
      } else {
        toast.error(error instanceof ApiError ? error.message : "Something went wrong.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <RedirectIfAuthed>
      <div className="flex flex-1 items-center justify-center bg-muted/40 p-4">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle>SAR Profile Search</CardTitle>
            <CardDescription>
              {step === "email"
                ? "Sign in with your work email to get a one-time code."
                : `Enter the 6-digit code sent to ${email.trim()}.`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {step === "email" ? (
              <form onSubmit={handleEmailSubmit} className="flex flex-col gap-4">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    autoComplete="email"
                    autoFocus
                    placeholder="you@ikrux.com"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    required
                  />
                </div>
                <Button type="submit" disabled={isSubmitting || !email.trim()}>
                  {isSubmitting ? "Sending code…" : "Send code"}
                </Button>
              </form>
            ) : (
              <form onSubmit={handleCodeSubmit} className="flex flex-col gap-4">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="code">6-digit code</Label>
                  <Input
                    id="code"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    autoFocus
                    maxLength={6}
                    placeholder="123456"
                    className="text-center text-lg tracking-[0.5em]"
                    value={code}
                    onChange={(event) => {
                      setCode(event.target.value.replace(/\D/g, "").slice(0, 6));
                      setCodeError(null);
                    }}
                    required
                  />
                  {codeError && <p className="text-sm text-destructive">{codeError}</p>}
                </div>
                <Button type="submit" disabled={isSubmitting || code.length !== 6}>
                  {isSubmitting ? "Verifying…" : "Verify & sign in"}
                </Button>
                <div className="flex items-center justify-between text-sm">
                  <button
                    type="button"
                    className="text-muted-foreground underline-offset-4 hover:underline"
                    onClick={() => {
                      setStep("email");
                      setCode("");
                      setCodeError(null);
                    }}
                  >
                    Use a different email
                  </button>
                  <button
                    type="button"
                    className="text-muted-foreground underline-offset-4 hover:underline disabled:opacity-50 disabled:no-underline"
                    disabled={cooldown > 0 || isSubmitting}
                    onClick={sendOtp}
                  >
                    {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend code"}
                  </button>
                </div>
              </form>
            )}
          </CardContent>
        </Card>
      </div>
    </RedirectIfAuthed>
  );
}
