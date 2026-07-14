import { pgTable, serial, varchar, text, boolean, real, timestamp, jsonb } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

// Правило ФЛК (tech_flk_config_table)
export const flkRules = pgTable("tech_flk_config_table", {
  id: serial("id").primaryKey(),
  indicator: varchar("indicator", { length: 255 }).notNull(),
  description: text("description"),
  incident_id: varchar("incident_id", { length: 255 }).notNull(),
  incident_id_from_pm: varchar("incident_id_from_pm", { length: 255 }).notNull(),
  product_type: varchar("product_type", { length: 255 }).notNull(),
  product_name: varchar("product_name", { length: 255 }).notNull(),
  indicator_category: varchar("indicator_category", { length: 255 }).notNull(),
  check_type: varchar("check_type", { length: 255 }).notNull(),

  // Целевая таблица
  target_schema: varchar("target_schema", { length: 255 }).notNull(),
  target_table: varchar("target_table", { length: 255 }).notNull(),

  // Логика проверки
  check_mode: varchar("check_mode", { length: 50 }).notNull().default("SIMPLE"),
  is_aggregated: boolean("is_aggregated").notNull().default(false),
  rule_payload: jsonb("rule_payload"),
  raw_sql_template: text("raw_sql_template"),

  // Критерии
  evaluation: varchar("evaluation", { length: 255 }).notNull(),
  passing_criteria: real("passing_criteria").notNull(),
  is_actual: boolean("is_actual").notNull().default(true),

  // Старое (совместимость)
  is_custom: boolean("is_custom").notNull().default(false),
  custom_function: varchar("custom_function", { length: 255 }),

  // Ответственные
  pm_responsible_id: varchar("pm_responsible_id", { length: 255 }),
  pm_accomplices_ids: varchar("pm_accomplices_ids", { length: 1000 }),

  // Статус (для UI)
  status: varchar("status", { length: 50 }).notNull().default("DRAFT"),

  update_timestamp: timestamp("update_timestamp").defaultNow().notNull(),
});

// Zod
export const insertFlkRuleSchema = createInsertSchema(flkRules).omit({
  id: true,
  update_timestamp: true,
});

export const rulePayloadSchema = z.object({
  column: z.string().optional(),
  operator: z.string().optional(),
  value: z.string().optional(),
  where_clause: z.string().optional(),
});

export type InsertFlkRule = z.infer<typeof insertFlkRuleSchema>;
export type FlkRule = typeof flkRules.$inferSelect;
export type RulePayload = z.infer<typeof rulePayloadSchema>;

// Метаданные таблиц (sidebar)
export interface TableMetadata {
  schema: string;
  tables: { name: string; columns: string[] }[];
}
