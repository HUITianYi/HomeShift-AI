import { env } from "cloudflare:workers";
import { getDb } from "@/db";
import { ensureSchema } from "@/db/ensure";
import { uploads } from "@/db/schema";

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

export async function POST(request: Request) {
  const form = await request.formData();
  const file = form.get("file");
  const sessionId = String(form.get("sessionId") || "unassigned");
  const kind = String(form.get("kind") || "evidence");

  if (!(file instanceof File)) {
    return Response.json({ error: "A file is required." }, { status: 400 });
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return Response.json(
      { error: "Files must be smaller than 10 MB." },
      { status: 413 },
    );
  }

  const binding = (env as unknown as { UPLOADS?: R2Bucket }).UPLOADS;
  if (!binding) {
    return Response.json(
      {
        stored: false,
        mode: "ephemeral-demo",
        message: "R2 binding UPLOADS is not available.",
      },
      { status: 202 },
    );
  }

  const id = crypto.randomUUID();
  const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, "_");
  const objectKey = `${sessionId}/${id}-${safeName}`;

  await binding.put(objectKey, await file.arrayBuffer(), {
    httpMetadata: { contentType: file.type || "application/octet-stream" },
    customMetadata: { sessionId, kind, originalName: file.name },
  });

  try {
    await ensureSchema();
    await getDb().insert(uploads).values({
      id,
      sessionId,
      objectKey,
      kind,
      fileName: file.name,
      contentType: file.type || "application/octet-stream",
      sizeBytes: file.size,
      createdAt: new Date().toISOString(),
    });
  } catch {
    // The R2 object is the durable source of truth; metadata can be reconciled.
  }

  return Response.json({ id, objectKey, stored: true });
}
