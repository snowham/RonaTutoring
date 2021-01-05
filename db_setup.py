import sqlite3

# Open or create if it doesn't exist the ronatutoring database
conn = sqlite3.connect("ronatutoring.sqlite")
cur = conn.cursor()

# NOTE: discordMessage in pending_requests is different; In pending_requests, 
# it excludes "@everyone " at the start while discordMessage in pending_confirmations
# and tutor_student_tracker, it includes "@everyone"

# Create table of raw pending tutor request data and request message
cur.execute("""CREATE TABLE IF NOT EXISTS pending_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            studentFullName VARCHAR(1000), parentFullName VARCHAR(1000), location VARCHAR(1000), age INTEGER,
            grade INTEGER, availability VARCHAR(4000), marketingSource VARCHAR(1000), 
            studentContact VARCHAR(400), parentContact VARCHAR(400), 
            math INTEGER, science INTEGER, english INTEGER, history INTEGER, compsci INTEGER, otherSubj VARCHAR(1000),
            specificClass VARCHAR(4000), additional VARCHAR(4000), 
            discordMessage VARCHAR(25000)
            );""")

# Create confirmation message counter (number of bot-to-tutor confirmation messages per tutor)
cur.execute("""CREATE TABLE IF NOT EXISTS confirmation_message_counters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tutorId INTEGER, confirmationMessageCount INTEGER
            );""")

# Create pending confirmation table
cur.execute("""CREATE TABLE IF NOT EXISTS pending_confirmations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            tutorId INTEGER, confirmationMessageIndex INTEGER, discordMessage VARCHAR(25000)
            );""")

# Create tutor-student tracker table
cur.execute("""CREATE TABLE IF NOT EXISTS tutor_student_tracker (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tutorId INTEGER, confirmationMessageIndex INTEGER, 
            studentFullName VARCHAR(1000), parentFullName VARCHAR(1000), location VARCHAR(1000), age INTEGER,
            grade INTEGER, availability VARCHAR(4000), marketingSource VARCHAR(1000), 
            studentContact VARCHAR(400), parentContact VARCHAR(400), 
            math INTEGER, science INTEGER, english INTEGER, history INTEGER, compsci INTEGER, otherSubj VARCHAR(1000),
            specificClass VARCHAR(4000), additional VARCHAR(4000), 
            discordMessage VARCHAR(25000)
            );""")


# Close database
conn.commit()
conn.close()