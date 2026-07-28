"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getCurrentUser, signInWithPassword } from "@/lib/auth";
import { AuthShell } from "@/components/AuthShell";
import { Button, Field, Input, ErrorBox } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getCurrentUser().then((u) => u && router.replace("/dashboard"));
  }, [router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    const { error } = await signInWithPassword(email, password);
    setLoading(false);
    if (error) setError(error);
    else router.replace("/dashboard");
  };

  return (
    <AuthShell
      title="Sign in"
      subtitle="Access the review workbench."
      footer={
        <>
          No account?{" "}
          <Link href="/signup" className="text-accent hover:text-accent-ink font-medium">
            Create one
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4">
        {error && <ErrorBox message={error} />}
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
        <Field label="Password">
          <Input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
          />
        </Field>
        <Button type="submit" loading={loading} className="w-full">
          Sign in
        </Button>
      </form>
    </AuthShell>
  );
}
