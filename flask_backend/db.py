"""
Модуль работы с PostgreSQL через psycopg2.
Подключение настраивается через переменные окружения.
"""

import os
import json
import psycopg2
import psycopg2.extras
from contextlib import contextmanager

# Параметры подключения из .env
DB_CONFIG = {
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "dbname": os.getenv("PG_DBNAME", "postgres"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", ""),
}


@contextmanager
def get_connection():
    """Контекстный менеджер для соединения с БД."""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_cursor(conn=None):
    """Контекстный менеджер для курсора. Если conn не передан — создаёт новое соединение."""
    if conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield cur
        finally:
            cur.close()
    else:
        with get_connection() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                yield cur
            finally:
                cur.close()


def init_db():
    """Применяет DDL-скрипт к базе данных (идемпотентно)."""
    ddl_path = os.path.join(os.path.dirname(__file__), "ddl.sql")
    with open(ddl_path, "r", encoding="utf-8") as f:
        ddl_sql = f.read()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl_sql)
    print("[db] DDL applied successfully")


# --- CRUD: tech_flk_config_table ---

def get_rules(filters: dict = None) -> list:
    """Получение списка правил с фильтрами."""
    query = """
        SELECT id, indicator, description, incident_id, incident_id_from_pm,
               product_type, product_name, indicator_category, check_type,
               target_schema, target_table, check_mode, is_aggregated,
               rule_payload, raw_sql_template, evaluation, passing_criteria,
               is_actual, is_custom, custom_function, pm_responsible_id,
               pm_accomplices_ids, status, update_timestamp
        FROM tech_data.tech_flk_config_table
        WHERE 1=1
    """
    params = []

    if filters:
        if filters.get("owner_id"):
            query += " AND (pm_responsible_id = %s OR pm_accomplices_ids LIKE %s)"
            params.extend([filters["owner_id"], f"%{filters['owner_id']}%"])
        if filters.get("incident_id"):
            query += " AND incident_id = %s"
            params.append(filters["incident_id"])
        if filters.get("status"):
            query += " AND status = %s"
            params.append(filters["status"])
        if filters.get("search"):
            query += " AND (indicator ILIKE %s OR description ILIKE %s)"
            search_pattern = f"%{filters['search']}%"
            params.extend([search_pattern, search_pattern])

    query += " ORDER BY update_timestamp DESC"

    with get_connection() as conn:
        with get_cursor(conn) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    return [_serialize_rule(row) for row in rows]


def get_rule(rule_id: int) -> dict | None:
    """Получение одного правила по ID."""
    query = """
        SELECT * FROM tech_data.tech_flk_config_table WHERE id = %s
    """
    with get_connection() as conn:
        with get_cursor(conn) as cur:
            cur.execute(query, (rule_id,))
            row = cur.fetchone()

    return _serialize_rule(row) if row else None


def upsert_rule(data: dict) -> dict:
    """
    Создание или обновление правила (UPSERT).
    INSERT ... ON CONFLICT (id) DO UPDATE
    """
    rule_id = data.get("id")

    # Подготовка rule_payload как JSON
    rule_payload = data.get("rule_payload")
    if rule_payload and isinstance(rule_payload, dict):
        rule_payload = json.dumps(rule_payload)
    elif rule_payload is None:
        rule_payload = None

    params = (
        data.get("indicator", ""),
        data.get("description"),
        data.get("incident_id", ""),
        data.get("incident_id_from_pm", ""),
        data.get("product_type", ""),
        data.get("product_name", ""),
        data.get("indicator_category", ""),
        data.get("check_type", ""),
        data.get("target_schema", ""),
        data.get("target_table", ""),
        data.get("check_mode", "SIMPLE"),
        data.get("is_aggregated", False),
        rule_payload,
        data.get("raw_sql_template"),
        data.get("evaluation", "PERCENTAGE"),
        data.get("passing_criteria", 0.95),
        data.get("is_actual", True),
        data.get("is_custom", False),
        data.get("custom_function"),
        data.get("pm_responsible_id"),
        data.get("pm_accomplices_ids"),
        data.get("status", "DRAFT"),
    )

    if rule_id:
        # UPDATE существующего правила
        query = """
            UPDATE tech_data.tech_flk_config_table SET
                indicator = %s, description = %s, incident_id = %s,
                incident_id_from_pm = %s, product_type = %s, product_name = %s,
                indicator_category = %s, check_type = %s,
                target_schema = %s, target_table = %s,
                check_mode = %s, is_aggregated = %s, rule_payload = %s,
                raw_sql_template = %s, evaluation = %s, passing_criteria = %s,
                is_actual = %s, is_custom = %s, custom_function = %s,
                pm_responsible_id = %s, pm_accomplices_ids = %s,
                status = %s, update_timestamp = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING *
        """
        all_params = params + (rule_id,)
    else:
        # INSERT нового правила
        query = """
            INSERT INTO tech_data.tech_flk_config_table
                (indicator, description, incident_id, incident_id_from_pm,
                 product_type, product_name, indicator_category, check_type,
                 target_schema, target_table, check_mode, is_aggregated,
                 rule_payload, raw_sql_template, evaluation, passing_criteria,
                 is_actual, is_custom, custom_function,
                 pm_responsible_id, pm_accomplices_ids, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """
        all_params = params

    with get_connection() as conn:
        with get_cursor(conn) as cur:
            cur.execute(query, all_params)
            row = cur.fetchone()

    return _serialize_rule(row)


def delete_rule(rule_id: int) -> bool:
    """Удаление правила по ID."""
    query = "DELETE FROM tech_data.tech_flk_config_table WHERE id = %s"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (rule_id,))
            return cur.rowcount > 0


def test_rule(data: dict) -> dict:
    """
    Тестовый прогон правила. Генерирует SQL и выполняет его.
    Если целевая таблица не существует — возвращает ошибку.
    """
    check_mode = data.get("check_mode", "SIMPLE")
    target_schema = data.get("target_schema", "")
    target_table = data.get("target_table", "")
    is_aggregated = data.get("is_aggregated", False)
    passing_criteria = float(data.get("passing_criteria", 0.95))

    # Генерация SQL
    if check_mode == "RAW_SQL":
        raw_sql = data.get("raw_sql_template", "")
        final_query = raw_sql.replace("{schema}", target_schema).replace("{table}", target_table)
    else:
        payload = data.get("rule_payload", {})
        if isinstance(payload, str):
            payload = json.loads(payload)
        col = payload.get("column", "")
        op = payload.get("operator", "=")
        val = payload.get("value", "")
        where = payload.get("where_clause", "")

        final_query = f"SELECT CASE WHEN {col} {op} {val} THEN true ELSE false END AS res FROM {target_schema}.{target_table}"
        if where and where.strip():
            final_query += f" WHERE {where}"

    # Выполнение
    try:
        with get_connection() as conn:
            with get_cursor(conn) as cur:
                if is_aggregated:
                    cur.execute(final_query)
                    row = cur.fetchone()
                    passed = bool(row.get("res", False)) if row else False
                    return {
                        "passed": passed,
                        "rows_checked": 1,
                        "rows_passed": 1 if passed else 0,
                        "percentage": 1.0 if passed else 0.0,
                        "executed_query": final_query,
                    }
                else:
                    cur.execute(final_query)
                    rows = cur.fetchall()
                    cnt_all = len(rows)
                    cnt_true = sum(1 for r in rows if r.get("res"))
                    pct = cnt_true / cnt_all if cnt_all > 0 else 1.0
                    passed = pct >= passing_criteria

                    return {
                        "passed": passed,
                        "rows_checked": cnt_all,
                        "rows_passed": cnt_true,
                        "percentage": round(pct, 4),
                        "executed_query": final_query,
                    }
    except Exception as e:
        return {
            "passed": False,
            "rows_checked": 0,
            "rows_passed": 0,
            "percentage": 0.0,
            "executed_query": final_query,
            "error": str(e),
        }


def get_table_metadata() -> list:
    """
    Получение дерева схем и таблиц из information_schema.
    Фильтруем только нужные схемы.
    """
    query = """
        SELECT table_schema, table_name, column_name
        FROM information_schema.columns
        WHERE table_schema IN ('dal_data', 'btl_data', 'qhl_data', 'tech_data', 'public')
          AND table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema, table_name, ordinal_position
    """
    try:
        with get_connection() as conn:
            with get_cursor(conn) as cur:
                cur.execute(query)
                rows = cur.fetchall()

        # Группировка: schema → table → columns
        schemas = {}
        for row in rows:
            schema = row["table_schema"]
            table = row["table_name"]
            col = row["column_name"]

            if schema not in schemas:
                schemas[schema] = {}
            if table not in schemas[schema]:
                schemas[schema][table] = []
            schemas[schema][table].append(col)

        result = []
        for schema_name, tables in sorted(schemas.items()):
            result.append({
                "schema": schema_name,
                "tables": [
                    {"name": t, "columns": cols}
                    for t, cols in sorted(tables.items())
                ],
            })

        return result
    except Exception as e:
        print(f"[db] Error fetching metadata: {e}")
        # Fallback: статические данные
        return _fallback_metadata()


def _fallback_metadata() -> list:
    """Статические метаданные, если information_schema не возвращает нужных схем."""
    return [
        {
            "schema": "dal_data",
            "tables": [
                {"name": "payments_table", "columns": ["id", "amount", "currency", "status", "created_at", "customer_id"]},
                {"name": "customers_table", "columns": ["id", "name", "email", "phone", "region", "created_at"]},
                {"name": "orders_table", "columns": ["id", "order_date", "ship_date", "total", "status", "customer_id"]},
                {"name": "transactions_log", "columns": ["id", "tx_type", "amount", "timestamp", "account_id"]},
            ],
        },
        {
            "schema": "btl_data",
            "tables": [
                {"name": "warehouse_stock", "columns": ["id", "product_code", "quantity", "warehouse_id", "last_update"]},
                {"name": "supply_chain", "columns": ["id", "supplier_id", "delivery_date", "items_count", "status"]},
            ],
        },
        {
            "schema": "qhl_data",
            "tables": [
                {"name": "product_catalog", "columns": ["id", "product_code", "name", "category", "price", "is_active"]},
                {"name": "employee_directory", "columns": ["id", "full_name", "department", "position", "hire_date"]},
            ],
        },
    ]


def _serialize_rule(row: dict) -> dict:
    """Сериализация строки из БД в JSON-совместимый dict."""
    if row is None:
        return None

    result = dict(row)

    # Преобразование timestamp в ISO-строку
    if "update_timestamp" in result and result["update_timestamp"]:
        result["update_timestamp"] = result["update_timestamp"].isoformat()

    if "check_timestamp" in result and result["check_timestamp"]:
        result["check_timestamp"] = result["check_timestamp"].isoformat()

    return result
