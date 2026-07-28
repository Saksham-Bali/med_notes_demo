"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { signUpWithPassword } from "@/lib/auth";
import { AuthShell } from "@/components/AuthShell";
import { Button, Field, Input, ErrorBox } from "@/components/ui";

export default function SignupPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setLoading(true);
    const { error, needsConfirmation } = await signUpWithPassword(email, password, fullName);
    setLoading(false);
    if (error) {
      setError(error);
    } else if (needsConfirmation) {
      setNotice("Check your email to confirm your account, then sign in.");
    } else {
      router.replace("/dashboard");
    }
  };

  return (
    <AuthShell
      title="Create account"
      subtitle="Set up your reviewer login."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="text-accent hover:text-accent-ink font-medium">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4">
        {error && <ErrorBox message={error} />}
        {notice && (
          <div className="rounded-lg border border-good/30 bg-good-soft px-4 py-3 text-sm text-good-ink">
            {notice}
          </div>
        )}
        <Field label="Full name">
          <Input
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Dr. A. Radiologist"
            required
          />
        </Field>
        <Field label="Email">
          <Input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="reviewer@hospital.org"
            required
          />
        </Field>
        <Field label="Password" hint="At least 8 characters.">
          <Input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            minLength={8}
            required
          />
        </Field>
        <Button type="submit" loading={loading} className="w-full">
          Create account
        </Button>
      </form>
    </AuthShell>
  );
}
