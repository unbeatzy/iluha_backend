import sqlite3

# Подключение к базе данных
conn = sqlite3.connect('vpn_bot.db')
cursor = conn.cursor()

# Создание таблицы для ключей
cursor.execute('''CREATE TABLE IF NOT EXISTS vpn_keys
                 (id INTEGER PRIMARY KEY, key TEXT, duration INTEGER, is_used BOOLEAN)''')
conn.commit()

# Создание таблицы для пользователей
cursor.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, last_name TEXT, subscription_end_date TEXT)''')
conn.commit()

# Создание таблицы для выданных ключей
cursor.execute('''
    CREATE TABLE IF NOT EXISTS issued_keys
    (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, payment_label TEXT, key TEXT, issued BOOLEAN, duration INTEGER)
''')
conn.commit()