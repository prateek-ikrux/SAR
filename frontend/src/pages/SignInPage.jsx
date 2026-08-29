import { useEffect, useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router";
import { ArrowLeft, Loader2, Mail } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import Logo from "@/components/Logo";
import { errorMessage } from "@/lib/api";
import { useMe, useRequestCode, useVerifyCode } from "@/hooks/useAuth";

export default function SignInPage() {
  const { data: user, isPending } = useMe();
  const navigate = useNavigate();

  const [step, setStep] = useState("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [cooldown, setCooldown] = useState(0);
  const codeRef = useRef(null);

  const requestCode = useRequestCode();
  const verifyCode = useVerifyCode();

  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const timer = setTimeout(() => setCooldown((s) => s - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  useEffect(() => {
    if (step === "code") codeRef.current?.focus();
  }, [step]);

  if (isPending) return null;
  if (user) return <Navigate to="/" replace />;

  function sendCode(event) {
    event?.preventDefault();
    setError("");
    requestCode.mutate(email.trim(), {
      onSuccess: (data) => {
        // The API answers identically for unknown addresses, so we always
        // advance - telling the user "no such account" would leak who works here.
        setStep("code");
        setCooldown(data.resend_available_in_seconds ?? 60);
        toast.success(`Code sent. It expires in ${data.expires_in_minutes} minutes.`);
      },
      onError: (err) => setError(errorMessage(err, "Could not send the code.")),
    });
  }

  function submitCode(event) {
    event.preventDefault();
    setError("");
    verifyCode.mutate(
      { email: email.trim(), code: code.trim() },
      {
        onSuccess: () => navigate("/", { replace: true }),
        onError: (err) => {
          setError(errorMessage(err, "That code is not valid."));
          setCode("");
          codeRef.current?.focus();
        },
      },
    );
  }

  return (
    <div className="flex min-h-svh items-center justify-center bg-muted/40 p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex justify-center">
          <Logo />
        </div>

        <Card>
          <CardHeader>
            <CardTitle>{step === "email" ? "Sign in" : "Enter your code"}</CardTitle>
            <CardDescription>
              {step === "email"
                ? "We will email you a one-time code. There is no password."
                : `Sent to ${email}`}
            </CardDescription>
          </CardHeader>

          <CardContent>
            {step === "email" ? (
              <form onSubmit={sendCode} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="email">Work email</Label>
                  <Input
                    id="email"
                    type="email"
                    autoComplete="email"
                    autoFocus
                    required
                    placeholder="you@ikrux.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>
                {error && <p className="text-sm text-destructive">{error}</p>}
                <Button type="submit" className="w-full" disabled={requestCode.isPending}>
                  {requestCode.isPending ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Mail className="size-4" />
                  )}
                  Send code
                </Button>
              </form>
            ) : (
              <form onSubmit={submitCode} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="code">Six-digit code</Label>
                  <Input
                    id="code"
                    ref={codeRef}
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={8}
                    required
                    placeholder="123456"
                    className="text-center font-mono text-lg tracking-[0.4em]"
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                  />
                </div>
                {error && <p className="text-sm text-destructive">{error}</p>}
                <Button type="submit" className="w-full" disabled={verifyCode.isPending}>
                  {verifyCode.isPending && <Loader2 className="size-4 animate-spin" />}
                  Sign in
                </Button>
                <div className="flex items-center justify-between text-sm">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setStep("email");
                      setCode("");
                      setError("");
                    }}
                  >
                    <ArrowLeft className="size-4" />
                    Change email
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={cooldown > 0 || requestCode.isPending}
                    onClick={() => sendCode()}
                  >
                    {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend code"}
                  </Button>
                </div>
              </form>
            )}
          </CardContent>
        </Card>

        <p className="text-center text-xs text-muted-foreground">
          Accounts are created by an administrator. Sessions last 24 hours.
        </p>
      </div>
    </div>
  );
}
