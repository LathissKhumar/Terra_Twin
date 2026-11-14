"use client";
import { Button } from "@/components/ui/button";
export default function ErrorBoundary({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <section role="alert"><h1 className="text-xl">This view could not be loaded.</h1>
    <p className="my-4">Try again to reload the view.</p><Button onClick={reset}>Try again</Button></section>;
}

