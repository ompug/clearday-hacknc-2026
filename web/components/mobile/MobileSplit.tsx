"use client";

import { useState } from "react";
import type { CreateExpenseResult } from "@/lib/api";
import { PlusIcon } from "../icons";
import { SplitAssistant } from "../assistant/SplitAssistant";
import { NewExpenseDialog } from "../split/NewExpenseDialog";
import { useMobileSession } from "./MobileShell";

/** Split tab: a new shared expense (with receipt scan inside) and the "split with words" assistant. */
export function MobileSplit() {
  const { me, announce } = useMobileSession();
  const [open, setOpen] = useState(false);

  function handleCreated(result: CreateExpenseResult, names: string[]) {
    setOpen(false);
    const who = names.length <= 2 ? names.join(" and ") : `${names.length} roommates`;
    announce(`${result.label} split with ${who}. It's in their sky now.`);
  }

  return (
    <div className="flex flex-col gap-4">
      <section aria-labelledby="m-new" className="glass rounded-[1.75rem] p-5">
        <h2 id="m-new" className="text-xl font-bold text-navy-950">
          Paid for something shared?
        </h2>
        <p className="mt-1 text-navy-800">
          Split it evenly, by custom amounts, or item by item. Scan a receipt to fill the items in.
        </p>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="m-press m-cta mt-4 inline-flex min-h-14 w-full items-center justify-center gap-2 rounded-full px-6 text-lg font-bold text-white"
        >
          <PlusIcon aria-hidden="true" className="size-6" />
          New shared expense
        </button>
      </section>

      <div className="m-assistant">
        <SplitAssistant disabled={false} onCreated={handleCreated} />
      </div>

      <NewExpenseDialog
        open={open}
        meId={me.user.user_id}
        onClose={() => setOpen(false)}
        onCreated={handleCreated}
      />
    </div>
  );
}
