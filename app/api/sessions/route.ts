import { eq } from "drizzle-orm";
import { getDb } from "@/db";
import { ensureSchema } from "@/db/ensure";
import { sessions } from "@/db/schema";

export async function GET(request: Request) {
  const id = new URL(request.url).searchParams.get("id");
  if (!id) {
    return Response.json({ error: "A session id is required." }, { status: 400 });
  }

  try {
    await ensureSchema();
    const [session] = await getDb()
      .select()
      .from(sessions)
      .where(eq(sessions.id, id))
      .limit(1);

    if (!session) {
      return Response.json({ error: "Session not found." }, { status: 404 });
    }

    return Response.json({
      ...session,
      profile: JSON.parse(session.profileJson),
      baseline: JSON.parse(session.baselineJson),
      plans: JSON.parse(session.plansJson),
    });
  } catch (error) {
    return storageUnavailable(error);
  }
}

export async function POST(request: Request) {
  const body = (await request.json()) as Record<string, unknown>;
  const id = String(body.id || crypto.randomUUID());
  const now = new Date().toISOString();

  try {
    await ensureSchema();
    await getDb()
      .insert(sessions)
      .values({
        id,
        householdName: String(body.householdName || "HomeShift household"),
        profileJson: JSON.stringify(body.profile ?? {}),
        baselineJson: JSON.stringify(body.baseline ?? {}),
        plansJson: JSON.stringify(body.plans ?? []),
        selectedPlan: body.selectedPlan ? String(body.selectedPlan) : null,
        createdAt: now,
        updatedAt: now,
      })
      .onConflictDoUpdate({
        target: sessions.id,
        set: {
          householdName: String(body.householdName || "HomeShift household"),
          profileJson: JSON.stringify(body.profile ?? {}),
          baselineJson: JSON.stringify(body.baseline ?? {}),
          plansJson: JSON.stringify(body.plans ?? []),
          selectedPlan: body.selectedPlan ? String(body.selectedPlan) : null,
          updatedAt: now,
        },
      });

    return Response.json({ id, persisted: true });
  } catch (error) {
    return storageUnavailable(error, id);
  }
}

function storageUnavailable(error: unknown, id?: string) {
  return Response.json(
    {
      id,
      persisted: false,
      mode: "ephemeral-demo",
      message:
        error instanceof Error ? error.message : "Cloud storage is unavailable.",
    },
    { status: 202 },
  );
}
