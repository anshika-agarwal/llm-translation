import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import DictCursor
import pandas as pd

# Load environment variables
load_dotenv()

# Database credentials
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT", "5432")
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

# Connect to the database
try:
    print("trying to connect")
    conn = get_db_connection()
    print("Connected to the database!")
except Exception as e:
    print(f"Error connecting to the database: {e}")
    exit()

# Query and fetch data
query = "SELECT * FROM conversations LIMIT 100;"
try:
    with conn.cursor(cursor_factory=DictCursor) as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()
        # Convert to DataFrame
        df = pd.DataFrame(rows, columns=[desc[0] for desc in cursor.description])
    print("Data fetched successfully!")
    print(df.head())  # Preview data
except Exception as e:
    print(f"Error executing query: {e}")
finally:
    conn.close()

# Data overview
try:
    print("Data Overview:")
    print(df.describe(include='all'))
except Exception as e:
    print(f"Error describing data: {e}")
