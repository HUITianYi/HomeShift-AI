CREATE TABLE `checkins` (
	`id` text PRIMARY KEY NOT NULL,
	`session_id` text NOT NULL,
	`payload_json` text NOT NULL,
	`result_json` text NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `sessions` (
	`id` text PRIMARY KEY NOT NULL,
	`household_name` text NOT NULL,
	`profile_json` text NOT NULL,
	`baseline_json` text NOT NULL,
	`plans_json` text NOT NULL,
	`selected_plan` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `uploads` (
	`id` text PRIMARY KEY NOT NULL,
	`session_id` text NOT NULL,
	`object_key` text NOT NULL,
	`kind` text NOT NULL,
	`file_name` text NOT NULL,
	`content_type` text NOT NULL,
	`size_bytes` integer NOT NULL,
	`created_at` text NOT NULL
);
