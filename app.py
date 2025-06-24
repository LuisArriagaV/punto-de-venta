from flask import Flask
from routes.auth import auth_bp
from routes.ventas import ventas_bp
from routes.inventario import inventario_bp

app = Flask(__name__)
app.secret_key = 'clave-secreta'  # Cambia esto por una clave segura

# Registrar los blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(ventas_bp)
app.register_blueprint(inventario_bp)

if __name__ == "__main__":
    app.run(debug=True)
