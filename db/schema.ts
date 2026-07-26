import { integer, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const sessions = sqliteTable("sessions", {
  id: text("id").primaryKey(),
  householdName: text("household_name").notNull(),
  profileJson: text("profile_json").notNull(),
  baselineJson: text("baseline_json").notNull(),
  plansJson: text("plans_json").notNull(),
  selectedPlan: text("selected_plan"),
  createdAt: text("created_at").notNull(),
  updatedAt: text("updated_at").notNull(),
});

export const checkins = sqliteTable("checkins", {
  id: text("id").primaryKey(),
  sessionId: text("session_id").notNull(),
  payloadJson: text("payload_json").notNull(),
  resultJson: text("result_json").notNull(),
  createdAt: text("created_at").notNull(),
});

export const uploads = sqliteTable("uploads", {
  id: text("id").primaryKey(),
  sessionId: text("session_id").notNull(),
  objectKey: text("object_key").notNull(),
  kind: text("kind").notNull(),
  fileName: text("file_name").notNull(),
  contentType: text("content_type").notNull(),
  sizeBytes: integer("size_bytes").notNull(),
  createdAt: text("created_at").notNull(),
});
