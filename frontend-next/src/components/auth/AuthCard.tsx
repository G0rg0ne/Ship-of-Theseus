"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { LoginForm } from "./LoginForm";
import { RegisterForm } from "./RegisterForm";

export function AuthCard() {
  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-xl font-semibold tracking-tight text-foreground">
          Welcome
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Sign in or create an account to build your knowledge brain.
        </p>
      </div>
      <Tabs defaultValue="signin" className="w-full">
        <TabsList className="inline-flex h-11 w-full rounded-full bg-white/5 p-1 backdrop-blur-sm">
          <TabsTrigger
            value="signin"
            className="flex-1 rounded-full data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-[0_0_14px_-4px_hsl(var(--primary)_/_0.5)]"
          >
            Sign in
          </TabsTrigger>
          <TabsTrigger
            value="register"
            className="flex-1 rounded-full data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-[0_0_14px_-4px_hsl(var(--primary)_/_0.5)]"
          >
            Create account
          </TabsTrigger>
        </TabsList>
        <TabsContent value="signin" className="mt-6">
          <LoginForm />
        </TabsContent>
        <TabsContent value="register" className="mt-6">
          <RegisterForm />
        </TabsContent>
      </Tabs>
    </div>
  );
}
