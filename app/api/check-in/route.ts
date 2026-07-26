import { getDb } from "@/db";
import { ensureSchema } from "@/db/ensure";
import { checkins } from "@/db/schema";

export async function POST(request: Request) {
  const body = (await request.json()) as Record<string, unknown>;
  if (!body.sessionId) {
    return Response.json({ error: "sessionId is required." }, { status: 400 });
  }

  const id = crypto.randomUUID();

  try {
    await ensureSchema();
    await getDb().insert(checkins).values({
      id,
      sessionId: String(body.sessionId),
      payloadJson: JSON.stringify(body.payload ?? {}),
      resultJson: JSON.stringify(body.result ?? {}),
      createdAt: new Date().toISOString(),
    });

    return Response.json({ id, persisted: true });
  } catch (error) {
    return Response.json(
      {
        id,
        persisted: false,
        mode: "ephemeral-demo",
        message:
          error instanceof Error
            ? error.message
            : "Cloud storage is unavailable.",
      },
      { status: 202 },
    );
  }
}
