import mysql.connector
from datetime import datetime
from dotenv import load_dotenv
import os

# Load .env variables
load_dotenv()

def log_entry(entry_text):
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )
    cursor = conn.cursor()
    sql = "INSERT INTO daily_logs (log_date, entry) VALUES (%s, %s)"
    cursor.execute(sql, (datetime.today().date(), entry_text))
    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Entry successfully logged to AWS RDS!")

if __name__ == "__main__":
    entry = input("📝 What did you work on today?\n")
    log_entry(entry)