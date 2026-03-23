"use client";

import Link from "next/link";
import { Anchor, LogOut, Shield } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";

export interface DashboardHeaderProps {
  displayName: string;
  greeting: string;
  email?: string | null;
  initials: string;
  isAdmin?: boolean;
  /** Second segment of breadcrumb, e.g. "Brain graph" */
  centerViewLabel: string;
  onLogout: () => void;
}

export function DashboardHeader({
  displayName,
  greeting,
  email,
  initials,
  isAdmin,
  centerViewLabel,
  onLogout,
}: DashboardHeaderProps) {
  return (
    <header className="sticky top-0 z-30 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div
        className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-primary/45 to-transparent"
        aria-hidden
      />
      <div className="relative flex h-14 items-center justify-between gap-4 px-4 sm:px-6">
        <div className="flex min-w-0 flex-1 items-center gap-4">
          <Link
            href="/dashboard"
            className="flex shrink-0 items-center gap-2.5 font-heading font-semibold text-foreground transition-opacity hover:opacity-90"
          >
            <Anchor className="h-6 w-6 text-primary" aria-hidden />
            <span className="hidden sm:inline">Ship of Theseus</span>
          </Link>
          <Separator orientation="vertical" className="hidden h-6 md:block" />
          <div className="hidden min-w-0 flex-col md:flex">
            <p className="truncate text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              {greeting}
            </p>
            <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <span className="font-medium text-foreground/80">Dashboard</span>
              <span className="text-muted-foreground/60" aria-hidden>
                /
              </span>
              <span className="truncate font-medium text-foreground">{centerViewLabel}</span>
            </nav>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2 sm:gap-3">
          <Link
            href="/how-it-works"
            className="hidden text-sm font-medium text-muted-foreground hover:text-foreground sm:inline"
          >
            How it works?
          </Link>
          {isAdmin && (
            <Link
              href="/admin"
              className="hidden text-sm font-medium text-muted-foreground hover:text-foreground md:inline"
            >
              Admin
            </Link>
          )}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                className="relative h-9 gap-2 rounded-full border border-border bg-secondary/60 px-2 pr-3 hover:bg-secondary"
              >
                <Avatar className="h-7 w-7 border-0">
                  <AvatarFallback className="text-[10px]">{initials}</AvatarFallback>
                </Avatar>
                <span className="hidden max-w-[120px] truncate text-sm font-medium text-foreground sm:inline">
                  {displayName}
                </span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel className="font-normal">
                <div className="flex flex-col space-y-1">
                  <p className="text-sm font-medium leading-none">{displayName}</p>
                  {email ? (
                    <p className="text-xs leading-none text-muted-foreground">{email}</p>
                  ) : null}
                </div>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <Link href="/how-it-works" className="flex cursor-pointer items-center">
                  How it works?
                </Link>
              </DropdownMenuItem>
              {isAdmin ? (
                <DropdownMenuItem asChild>
                  <Link href="/admin" className="flex cursor-pointer items-center">
                    <Shield className="mr-2 h-4 w-4" />
                    Admin
                  </Link>
                </DropdownMenuItem>
              ) : null}
              <DropdownMenuSeparator />
              <DropdownMenuItem
                className="cursor-pointer text-destructive focus:text-destructive"
                onClick={() => void onLogout()}
              >
                <LogOut className="mr-2 h-4 w-4" />
                Log out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
}
