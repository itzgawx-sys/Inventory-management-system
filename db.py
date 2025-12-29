import mysql.connector

def admin_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Aruna@vpm32",
        database="admin_db"
    )

def user_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Aruna@vpm32",
        database="user_db"
    )

def inventory_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Aruna@vpm32",
        database="inventory_db"
    )
