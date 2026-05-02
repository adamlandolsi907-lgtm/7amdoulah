import * as React from "react";
import { cn } from "@/lib/utils";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "destructive" | "outline" | "secondary" | "ghost" | "link";
  size?: "default" | "sm" | "lg" | "icon";
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", ...props }, ref) => (
    <button
      className={cn(
        "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-green-500 disabled:pointer-events-none disabled:opacity-50",
        {
          "bg-green-600 text-gray-900 shadow hover:bg-green-500": variant === "default",
          "bg-red-600 text-white shadow-sm hover:bg-red-500": variant === "destructive",
          "border border-green-700 bg-transparent text-green-400 shadow-sm hover:bg-green-900/30": variant === "outline",
          "bg-gray-800 text-green-400 shadow-sm hover:bg-gray-700": variant === "secondary",
          "text-green-400 hover:bg-gray-800 hover:text-green-300": variant === "ghost",
          "text-green-400 underline-offset-4 hover:underline": variant === "link",
        },
        {
          "h-9 px-4 py-2": size === "default",
          "h-8 rounded-md px-3 text-xs": size === "sm",
          "h-10 rounded-md px-8": size === "lg",
          "h-9 w-9": size === "icon",
        },
        className
      )}
      ref={ref}
      {...props}
    />
  )
);
Button.displayName = "Button";
export { Button };
