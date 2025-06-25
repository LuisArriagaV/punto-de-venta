# db/conexion.py
import psycopg2

def obtener_conexion():
    return psycopg2.connect(
        host="dpg-d1djd2p5pdvs73akf7og-a",
        database="pos_vmmc",
        user="pos_vmmc_user",
        password="cCvE7mmRZcvH5MuyahSkrbWCfGIJaqMO"
    )
