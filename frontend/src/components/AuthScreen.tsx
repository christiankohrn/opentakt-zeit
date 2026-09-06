import type { ReactNode } from "react";
import { useAuth } from "../auth";
import { PRODUCT_NAME } from "../brand";
import { IconMoon, IconSun } from "./Icons";
import { useTheme } from "../theme";

export default function AuthScreen({
  title,
  lead,
  children,
}: {
  title: string;
  lead: string;
  children: ReactNode;
}) {
  const { orgName } = useAuth();
  const { dark, cycle, theme } = useTheme();
  return (
    <div className="relative mx-auto flex min-h-dvh max-w-lg flex-col justify-center px-6 lg:max-w-4xl lg:flex-row lg:items-center lg:gap-16">
      <button
        type="button"
        onClick={cycle}
        className="absolute right-6 top-[max(1.25rem,env(safe-area-inset-top))] rounded-full border border-line p-2 text-present"
        title={theme === "system" ? "System" : theme === "light" ? "Hell" : "Dunkel"}
      >
        {dark ? <IconSun className="h-5 w-5" /> : <IconMoon className="h-5 w-5" />}
      </button>
      <div className="lg:flex-1">
        <p className="text-sm font-medium text-present">{orgName}</p>
        {orgName !== PRODUCT_NAME ? <p className="mt-0.5 text-xs text-muted">{PRODUCT_NAME}</p> : null}
        <h1 className="mt-2 text-4xl font-semibold tracking-tight lg:text-5xl">{title}</h1>
        <p className="mt-3 max-w-sm text-muted">{lead}</p>
      </div>
      <div className="mt-10 lg:mt-0 lg:w-[22rem] lg:shrink-0">{children}</div>
    </div>
  );
}
