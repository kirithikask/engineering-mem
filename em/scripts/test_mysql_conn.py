import pymysql
import os

passwords_to_try = [
    os.getenv("MYSQL_PASSWORD", ""),
    "root",
    "admin",
    "password",
    "123456",
    "12345678",
    "mysql",
    ""
]

connected = False
for pwd in passwords_to_try:
    try:
        conn = pymysql.connect(
            host="localhost",
            user="root",
            password=pwd,
            port=3306,
            connect_timeout=2
        )
        print(f"SUCCESS: Connected to MySQL with password: '{pwd}'")
        connected = True
        conn.close()
        break
    except Exception as e:
        pass

if not connected:
    print("Could not connect with standard root passwords. Fallback configuration will be enabled.")
