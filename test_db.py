import os

import mysql.connector
from dotenv import load_dotenv

load_dotenv()


def test_connection():
    connection = None

    try:
        connection = mysql.connector.connect(
            host=os.environ["MYSQL_HOST"],
            port=int(os.getenv("MYSQL_PORT", "3306")),
            database=os.environ["MYSQL_DATABASE"],
            user=os.environ["MYSQL_USER"],
            password=os.environ["MYSQL_PASSWORD"],
            connection_timeout=10,
        )

        print("MySQL connection successful!")

        cursor = connection.cursor()
        cursor.execute("SHOW TABLES")

        print("\nAvailable tables:")
        for (table_name,) in cursor.fetchall():
            print(f"- {table_name}")

        cursor.close()

    except KeyError as error:
        print(f"Missing environment variable: {error}")

    except mysql.connector.Error as error:
        print(f"MySQL connection failed: {error}")

    finally:
        if connection is not None and connection.is_connected():
            connection.close()
            print("\nConnection closed.")


if __name__ == "__main__":
    test_connection()