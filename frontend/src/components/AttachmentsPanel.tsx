import { FileText, Paperclip } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  apiErrorMessage,
  listAttachments,
  listDoctorAttachments,
  uploadAttachment,
} from "../api/client";
import type { Attachment } from "../api/types";

const ACCEPT = "image/jpeg,image/png,image/webp,application/pdf";
const MAX_BYTES = 10 * 1024 * 1024;

/** Photos and PDFs on a patient, stored in S3. Nurses on the patient can add them. */
export default function AttachmentsPanel({
  patientId,
  audience,
  canUpload,
}: {
  patientId: string;
  audience: "nurse" | "doctor";
  canUpload: boolean;
}) {
  const [items, setItems] = useState<Attachment[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const { attachments } =
        audience === "doctor"
          ? await listDoctorAttachments(patientId)
          : await listAttachments(patientId);
      setItems(attachments);
    } catch {
      // attachments are extra context; the patient screen works without them
    }
  }, [audience, patientId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onPick(file: File | undefined) {
    if (!file) return;
    if (file.size > MAX_BYTES) {
      setError("That file is over 10 MB.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const added = await uploadAttachment(patientId, file);
      setItems((current) => [added, ...current]);
    } catch (err) {
      setError(apiErrorMessage(err, "Couldn't attach that file."));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  if (!canUpload && items.length === 0) return null;

  return (
    <section className="mb-5">
      <div className="mb-2 flex items-center justify-between">
        <p className="section-title">Attachments</p>
        {canUpload && (
          <>
            <button
              type="button"
              className="flex items-center gap-1 text-[0.72rem] font-bold"
              style={{ color: "var(--primary-contrast)" }}
              disabled={busy}
              onClick={() => input.current?.click()}
            >
              <Paperclip size={13} strokeWidth={2.4} />
              {busy ? "Uploading…" : "Attach photo"}
            </button>
            <input
              ref={input}
              type="file"
              accept={ACCEPT}
              capture="environment"
              className="hidden"
              onChange={(event) => void onPick(event.target.files?.[0])}
            />
          </>
        )}
      </div>

      {error && <p className="form-error mb-2">{error}</p>}

      {items.length === 0 ? (
        <p className="text-[0.78rem] text-[var(--text-muted)]">
          No photos or documents yet.
        </p>
      ) : (
        <div className="grid grid-cols-3 gap-2">
          {items.map((item) => (
            <a
              key={item.id}
              href={item.url}
              target="_blank"
              rel="noreferrer"
              className="card flex aspect-square items-center justify-center overflow-hidden"
              title={item.file_name}
            >
              {item.content_type.startsWith("image/") ? (
                <img src={item.url} alt={item.file_name} className="h-full w-full object-cover" />
              ) : (
                <span className="flex flex-col items-center gap-1 p-2 text-center text-[0.65rem] text-[var(--text-muted)]">
                  <FileText size={20} strokeWidth={2} />
                  {item.file_name}
                </span>
              )}
            </a>
          ))}
        </div>
      )}
    </section>
  );
}
