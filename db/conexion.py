# db/conexion.py
import psycopg2

def obtener_conexion():
    return psycopg2.connect(
        host="localhost",
        database="POS",
        user="postgres",
        password="1998"
    )