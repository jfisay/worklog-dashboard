import mysql.connector
import openai
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def fetch_weekly_logs():
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )
    cursor = conn.cursor()
    start_of_week = datetime.today() - timedelta(days=datetime.today().weekday())  # Monday
    sql = "SELECT entry FROM daily_logs WHERE log_date >= %s"
    cursor.execute(sql, (start_of_week.date(),))
    entries = cursor.fetchall()
    cursor.close()
    conn.close()
    return "\n".join([entry[0] for entry in entries])

def summarize_logs(log_text):
    prompt = (
        "These are daily work logs. Please:\n"
        "1. Generate bullet points for what was done.\n"
        "2. Write a 1-paragraph summary of the overall work and progress.\n\n"
        f"{log_text}"
    )

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a productivity assistant."},
            {"role": "user", "content": prompt}
        ]
    )

    return response['choices'][0]['message']['content']

if __name__ == "__main__":
    logs = fetch_weekly_logs()
    if not logs.strip():
        print("⚠️ No logs found for this week.")
    else:
        summary = summarize_logs(logs)
        print("\n📋 Weekly Summary:\n")
        print(summary)


def save_summary_to_db(summary, start_date, end_date):
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )
    cursor = conn.cursor()
    sql = "INSERT INTO weekly_summaries (week_start, week_end, summary) VALUES (%s, %s, %s)"
    cursor.execute(sql, (start_date, end_date, summary))
    conn.commit()
    cursor.close()
    conn.close()

# Add this at the bottom after printing summary
start_of_week = datetime.today() - timedelta(days=datetime.today().weekday())
end_of_week = start_of_week + timedelta(days=6)

save_summary_to_db(summary, start_of_week.date(), end_of_week.date())
print("💾 Summary saved to database.")