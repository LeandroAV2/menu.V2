from flask import Flask, render_template, request, redirect, session, jsonify
import hashlib, datetime, os, sqlite3

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "tumenu_secret_2025")

DB_PATH = os.path.join(os.path.dirname(__file__), "tumenu.db")

# ===== BASE DE DATOS =====
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            creado_en TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_email TEXT NOT NULL,
            usuario_nombre TEXT NOT NULL,
            items TEXT NOT NULL,
            total INTEGER NOT NULL,
            hora TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# ===== MENÚ =====
MENU = {
    "menu_del_dia": {
        "nombre": "Milanesa napolitana + guarnición + postre",
        "descripcion": "Incluye bebida sin alcohol. Disponible hasta las 15:00 hs",
        "precio": 3800,
        "emoji": ""
    },
    "categorias": {
        "comidas": {
            "nombre": "Comidas", "emoji": "",
            "subcategorias": {
                "pastas": { "nombre": "Pastas", "items": [
                    {"id":1,"nombre":"Ñoquis al fileto","desc":"Salsa de tomate fresco, albahaca y parmesano","precio":2100,"emoji":""},
                    {"id":2,"nombre":"Tallarines a la bolognesa","desc":"Carne vacuna, zanahoria, vino tinto","precio":2400,"emoji":""},
                    {"id":3,"nombre":"Sorrentinos de ricotta","desc":"Rellenos de ricotta y espinaca, salsa blanca","precio":2700,"emoji":""},
                    {"id":4,"nombre":"Fetuccini al pesto","desc":"Pesto de albahaca casero, nueces, parmesano","precio":2300,"emoji":""}
                ]},
                "carnes": { "nombre": "Carnes", "items": [
                    {"id":10,"nombre":"Milanesa napolitana","desc":"Con jamón, mozzarella y salsa de tomate","precio":3200,"emoji":""},
                    {"id":11,"nombre":"Bife de chorizo","desc":"300g a la plancha con papas fritas","precio":4100,"emoji":""},
                    {"id":12,"nombre":"Pollo a la plancha","desc":"Con ensalada mixta y papas al horno","precio":2900,"emoji":""},
                    {"id":13,"nombre":"Asado de tira","desc":"Corte de res, chimichurri casero","precio":3800,"emoji":""}
                ]},
                "sandwiches": { "nombre": "Sandwiches", "items": [
                    {"id":20,"nombre":"Lomito completo","desc":"Lomito, jamón, queso, lechuga, tomate, huevo","precio":2600,"emoji":""},
                    {"id":21,"nombre":"Hamburguesa clásica","desc":"200g de carne, cheddar, pepino, cebolla","precio":2200,"emoji":""},
                    {"id":22,"nombre":"Club sandwich","desc":"Pollo, panceta, lechuga, tomate, mayonesa","precio":2400,"emoji":""}
                ]},
                "ensaladas": { "nombre": "Ensaladas", "items": [
                    {"id":30,"nombre":"Ensalada César","desc":"Pollo grillado, lechuga romana, crutones","precio":1900,"emoji":""},
                    {"id":31,"nombre":"Ensalada mixta","desc":"Lechuga, tomate, zanahoria, choclo","precio":1400,"emoji":""}
                ]}
            }
        },
        "bebidas": {
            "nombre": "Bebidas", "emoji": "",
            "subcategorias": {
                "cervezas": { "nombre": "Cervezas", "items": [
                    {"id":40,"nombre":"Cerveza rubia 500cc","desc":"Chopp de barril bien frío","precio":900,"emoji":""},
                    {"id":41,"nombre":"Cerveza negra 500cc","desc":"Stout artesanal de la casa","precio":1000,"emoji":""},
                    {"id":42,"nombre":"Craft IPA 330cc","desc":"India Pale Ale, lupulada y aromática","precio":1100,"emoji":""}
                ]},
                "gaseosas": { "nombre": "Gaseosas", "items": [
                    {"id":50,"nombre":"Coca-Cola 500cc","desc":"Botella personal bien fría","precio":700,"emoji":""},
                    {"id":51,"nombre":"Sprite 500cc","desc":"Lima limón refrescante","precio":700,"emoji":""},
                    {"id":52,"nombre":"Fanta naranja 500cc","desc":"Sabor naranja","precio":700,"emoji":""}
                ]},
                "aguas": { "nombre": "Aguas", "items": [
                    {"id":60,"nombre":"Agua sin gas 500cc","desc":"Botella individual","precio":500,"emoji":""},
                    {"id":61,"nombre":"Agua con gas 500cc","desc":"Con burbujas","precio":550,"emoji":""},
                    {"id":62,"nombre":"Agua saborizada","desc":"Durazno o manzana verde","precio":650,"emoji":""}
                ]},
                "vinos": { "nombre": "Vinos", "items": [
                    {"id":70,"nombre":"Malbec copa","desc":"Mendoza, 150cc","precio":1200,"emoji":""},
                    {"id":71,"nombre":"Chardonnay copa","desc":"Vino blanco frío, 150cc","precio":1100,"emoji":""}
                ]}
            }
        },
        "postres": {
            "nombre": "Postres", "emoji": "",
            "subcategorias": {
                "helados": { "nombre": "Helados", "items": [
                    {"id":80,"nombre":"Helado 2 bochas","desc":"Dulce de leche, chocolate, vainilla o frutilla","precio":900,"emoji":""},
                    {"id":81,"nombre":"Helado 3 bochas","desc":"A elección con salsa o granizado","precio":1200,"emoji":""}
                ]},
                "tortas": { "nombre": "Tortas", "items": [
                    {"id":90,"nombre":"Torta de chocolate","desc":"Con ganache y crema batida","precio":1400,"emoji":""},
                    {"id":91,"nombre":"Cheesecake de frutos rojos","desc":"Base de galleta, queso crema, coulis","precio":1500,"emoji":""}
                ]},
                "otros": { "nombre": "Otros postres", "items": [
                    {"id":100,"nombre":"Tiramisú","desc":"Receta italiana clásica con mascarpone","precio":1300,"emoji":""},
                    {"id":101,"nombre":"Panqueques con dulce de leche","desc":"Con crema y nueces","precio":1100,"emoji":""},
                    {"id":102,"nombre":"Flan con crema","desc":"Casero, con caramelo y crema batida","precio":950,"emoji":""}
                ]}
            }
        }
    }
}

def hashear(p): return hashlib.sha256(p.encode()).hexdigest()
def usuario_logueado(): return session.get("usuario")

@app.route("/")
def index():
    return render_template("menu.html", menu=MENU, usuario=usuario_logueado())

@app.route("/login", methods=["POST"])
def login():
    email    = request.form.get("email","").strip().lower()
    password = request.form.get("password","")
    next_url = request.form.get("next","/")
    if not email or not password:
        return redirect("/?auth_error=Completá+todos+los+campos&tab=login")
    conn = get_db()
    u = conn.execute("SELECT * FROM usuarios WHERE email=?", (email,)).fetchone()
    conn.close()
    if not u:
        return redirect("/?auth_error=No+existe+una+cuenta+con+ese+email&tab=login")
    if u["password"] != hashear(password):
        return redirect("/?auth_error=Contraseña+incorrecta&tab=login")
    session["usuario"] = {"email": email, "nombre": u["nombre"]}
    return redirect(next_url)

@app.route("/registro", methods=["POST"])
def registro():
    nombre   = request.form.get("nombre","").strip()
    email    = request.form.get("email","").strip().lower()
    password = request.form.get("password","")
    next_url = request.form.get("next","/")
    if not nombre or not email or not password:
        return redirect("/?auth_error=Completá+todos+los+campos&tab=registro")
    if "@" not in email or "." not in email:
        return redirect("/?auth_error=Email+inválido&tab=registro")
    if len(password) < 6:
        return redirect("/?auth_error=La+contraseña+debe+tener+al+menos+6+caracteres&tab=registro")
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO usuarios (nombre,email,password,creado_en) VALUES (?,?,?,?)",
            (nombre, email, hashear(password), datetime.datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError:
        return redirect("/?auth_error=Ese+email+ya+está+registrado&tab=login")
    session["usuario"] = {"email": email, "nombre": nombre}
    return redirect(next_url)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/pedido", methods=["POST"])
def pedido():
    if not usuario_logueado():
        return jsonify({"error": "no_auth"}), 401
    datos   = request.get_json()
    items   = datos.get("items", [])
    total   = datos.get("total", 0)
    usuario = session["usuario"]
    if not items:
        return jsonify({"error": "Carrito vacío"}), 400
    import json
    conn = get_db()
    conn.execute(
        "INSERT INTO pedidos (usuario_email,usuario_nombre,items,total,hora) VALUES (?,?,?,?,?)",
        (usuario["email"], usuario["nombre"], json.dumps(items), total,
         datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    )
    conn.commit()
    conn.close()
    print(f"\nNUEVO PEDIDO de {usuario['nombre']}")
    for i in items: print(f"  {i['cantidad']}x {i['nombre']} ${i['precio']}")
    print(f"  TOTAL: ${total}\n")
    return jsonify({"ok": True})

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
