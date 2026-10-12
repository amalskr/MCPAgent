from datetime import datetime

import pandas as pd

from app.db import get_connection


KPI_SQL = """
SELECT
    (SELECT COUNT(*) FROM orders) AS total_orders,
    (SELECT COUNT(*) FROM products) AS total_products,
    (SELECT COUNT(*) FROM orders
        WHERE UPPER(order_status) = 'PENDING') AS pending_orders,
    (SELECT COUNT(*) FROM orders
        WHERE UPPER(order_status) IN ('CANCELED', 'CANCELLED')) AS canceled_orders
"""

ORDER_STATUS_SQL = """
SELECT
    COALESCE(order_status, 'UNKNOWN') AS order_status,
    COUNT(*) AS orders,
    SUM(CAST(full_amount AS DECIMAL(12, 2))) AS order_value
FROM orders
GROUP BY order_status
ORDER BY orders DESC
"""

TOP_PRODUCTS_SQL = """
SELECT name, category, price_lkr AS price, quantity
FROM products
WHERE price_lkr IS NOT NULL
ORDER BY price_lkr DESC
LIMIT 5
"""


def load_dashboard_data():
    """Run all dashboard queries on one connection."""
    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute(KPI_SQL)
        kpis = {key: int(value or 0) for key, value in cursor.fetchone().items()}

        cursor.execute(ORDER_STATUS_SQL)
        order_status = pd.DataFrame(
            cursor.fetchall(),
            columns=["order_status", "orders", "order_value"],
        )

        cursor.execute(TOP_PRODUCTS_SQL)
        top_products = pd.DataFrame(
            cursor.fetchall(),
            columns=["name", "category", "price", "quantity"],
        )
    finally:
        connection.close()

    # MySQL returns DECIMAL values; convert them for charting.
    order_status["order_value"] = pd.to_numeric(order_status["order_value"])
    top_products["price"] = pd.to_numeric(top_products["price"])

    return {
        "kpis": kpis,
        "order_status": order_status,
        "top_products": top_products,
        "loaded_at": datetime.now(),
    }
