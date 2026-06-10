from flask import Flask, render_template, request, redirect, session, jsonify
import hashlib, datetime, os, json
import psycopg
from psycopg.rows import dict_row

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "tumenu_secret_2025")

DATABASE_URL = os.environ.get("DATABASE_URL")

PUNTOS_POR_PESO = 50

BENEFICIOS = [
    {"id": 1, "nombre": "Postre gratis",       "descripcion": "Cualquier postre de la carta sin cargo",      "puntos": 500,  "emoji": ""},
    {"id": 2, "nombre": "Bebida gratis",        "descripcion": "Gaseosa, agua o cerveza rubia sin cargo",    "puntos": 300,  "emoji": ""},
    {"id": 3, "nombre": "10% descuento",        "descripcion": "10% off en tu próximo pedido",               "puntos": 800,  "emoji": ""},
    {"id": 4, "nombre": "Entrada gratis",       "descripcion": "Empanadas (x2) o ensalada mixta sin cargo",  "puntos": 600,  "emoji": ""},
    {"id": 5, "nombre": "Menú del día gratis",  "descripcion": "El menú completo del día sin cargo",         "puntos": 1500, "emoji": ""},
    {"id": 6, "nombre": "Café + postre",        "descripcion": "Café o té con postre de la carta",           "puntos": 400,  "emoji": ""},
]

# ===== DB =====
def get_db():
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        nombre TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        creado_en TEXT NOT NULL,
        puntos INTEGER NOT NULL DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS admins (
        id SERIAL PRIMARY KEY,
        nombre TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        creado_en TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS pedidos (
        id SERIAL PRIMARY KEY,
        usuario_email TEXT NOT NULL,
        usuario_nombre TEXT NOT NULL,
        items TEXT NOT NULL,
        total INTEGER NOT NULL,
        puntos_ganados INTEGER NOT NULL DEFAULT 0,
        tipo TEXT NOT NULL DEFAULT 'local',
        pago TEXT NOT NULL DEFAULT 'efectivo',
        estado TEXT NOT NULL DEFAULT 'pendiente',
        hora TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS canjes (
        id SERIAL PRIMARY KEY,
        usuario_email TEXT NOT NULL,
        beneficio_id INTEGER NOT NULL,
        beneficio_nombre TEXT NOT NULL,
        puntos_usados INTEGER NOT NULL,
        hora TEXT NOT NULL
    )""")
    # Admin por defecto
    c.execute("""INSERT INTO admins (nombre, email, password, creado_en)
                 VALUES (%s, %s, %s, %s)
                 ON CONFLICT (email) DO NOTHING""",
              ("Admin", "admin@tumenu.com",
               hashlib.sha256("admin123".encode()).hexdigest(),
               datetime.datetime.now().isoformat()))
    conn.commit()
    c.close()
    conn.close()

init_db()

# ===== MENÚ =====
MENU = {
    "menu_del_dia": {"nombre":"Milanesa napolitana + guarnición + postre",
                     "descripcion":"Incluye bebida sin alcohol. Disponible hasta las 15:00 hs",
                     "precio":3800,"emoji":""},
    "categorias": {
        "comidas": {"nombre":"Comidas","emoji":"","subcategorias":{
            "pastas":{"nombre":"Pastas","items":[
                {"id":1,"nombre":"Ñoquis","desc":"Salsa de tomate fresco, albahaca y parmesano","precio":2100,"emoji":""},
                {"id":2,"nombre":"Tallarines a la bolognesa","desc":"Carne vacuna, zanahoria, vino tinto","precio":2400,"emoji":""},
                {"id":3,"nombre":"Sorrentinos de ricotta","desc":"Rellenos de ricotta y espinaca, salsa blanca","precio":2700,"emoji":""}]}}}}},
            "carnes":{"nombre":"Carnes","items":[
                {"id":10,"nombre":"Milanesa napolitana","desc":"Con jamón, mozzarella y salsa de tomate","precio":3200,"emoji":""},
                {"id":11,"nombre":"Bife de chorizo","desc":"A la plancha con papas fritas","precio":4100,"emoji":""},
                {"id":12,"nombre":"Pollo a la plancha","desc":"Con ensalada mixta y papas al horno","precio":2900,"emoji":""},
                {"id":13,"nombre":"Asado","desc":"Fuente como para 2 personas","precio":3800,"emoji":""}]}}}}}},      
            "sandwiches":{"nombre":"Sandwiches","items":[
                {"id":20,"nombre":"Lomito completo","desc":"Lomito, jamón, queso, lechuga, tomate, huevo","precio":2600,"emoji":""},
                {"id":21,"nombre":"Hamburguesa clásica","desc":"200g de carne, cheddar, pepino, cebolla","precio":2200,"emoji":""},
                {"id":22,"nombre":"Club sandwich","desc":"Pollo, panceta, lechuga, tomate, mayonesa","precio":2400,"emoji":""}]}}},
            "ensaladas":{"nombre":"Ensaladas","items":[
                {"id":30,"nombre":"Ensalada César","desc":"Pollo grillado, lechuga romana, crutones","precio":1900,"emoji":""},
                {"id":31,"nombre":"Ensalada mixta","desc":"Lechuga, tomate, zanahoria, choclo","precio":1400,"emoji":""}]}}},
        "bebidas":{"nombre":"Bebidas","emoji":"","subcategorias":{
            "cervezas":{"nombre":"Cervezas","items":[
                {"id":40,"nombre":"Cerveza Brahma","desc":"Cerveza clasica","precio":900,"emoji":""},
                {"id":41,"nombre":"Cerveza Andes negra, en LATA 473cc","desc":"Aroma y sabor tostado","precio":1000,"emoji":""}]}}},
            "gaseosas":{"nombre":"Gaseosas","items":[
                {"id":50,"nombre":"Coca-Cola 500cc","desc":"Botella personal bien fría","precio":700,"emoji":""},
                {"id":51,"nombre":"Sprite 500cc","desc":"Lima limón refrescante","precio":700,"emoji":""},
                {"id":52,"nombre":"Fanta naranja 500cc","desc":"Sabor naranja","precio":700,"emoji":""}]}},
            "aguas":{"nombre":"Aguas","items":[
                {"id":60,"nombre":"Agua sin gas 500cc","desc":"Botella individual","precio":500,"emoji":""},
                {"id":61,"nombre":"Agua con gas 500cc","desc":"Con burbujas","precio":550,"emoji":""},
                {"id":62,"nombre":"Agua saborizada","desc":"Pomelo, Manzana y Pera","precio":650,"emoji":""}]},
            "vinos":{"nombre":"Vinos","items":[
                {"id":70,"nombre":"Malbec copa","desc":"Mendoza, 150cc","precio":1200,"emoji":""}]},
        "postres":{"nombre":"Postres","emoji":"","subcategorias":{
            "helados":{"nombre":"Helados","items":[
                {"id":80,"nombre":"Helado 2 bochas","desc":"Dulce de leche, chocolate, vainilla o frutilla","precio":900,"emoji":""},
                {"id":81,"nombre":"Helado 3 bochas","desc":"A elección con salsa o granizado","precio":1200,"emoji":""}]}}}},
            "tortas":{"nombre":"Tortas","items":[
                {"id":90,"nombre":"Torta de chocolate","desc":"Con ganache y crema batida","precio":1400,"emoji":""},
                {"id":91,"nombre":"Cheesecake de frutos rojos","desc":"Base de galleta, queso crema, coulis","precio":1500,"emoji":""}]},
            "otros":{"nombre":"Otros postres","items":[
                {"id":100,"nombre":"Tiramisú","desc":"Receta italiana clásica con mascarpone","precio":1300,"emoji":""},
                {"id":101,"nombre":"Panqueques con dulce de leche","desc":"Con crema y nueces","precio":1100,"emoji":""},
                {"id":102,"nombre":"Flan con crema","desc":"Casero, con caramelo y crema batida","precio":950,"emoji":""}]}}}
    }
}

def hashear(p): return hashlib.sha256(p.encode()).hexdigest()
def usuario_logueado(): return session.get("usuario")
def admin_logueado(): return session.get("admin")

def get_puntos(email):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT puntos FROM usuarios WHERE email=%s", (email,))
    row = c.fetchone()
    c.close(); conn.close()
    return row["puntos"] if row else 0

# ===== RUTAS CLIENTE =====
@app.route("/")
def index():
    usuario = usuario_logueado()
    if usuario:
        usuario["puntos"] = get_puntos(usuario["email"])
        session["usuario"] = usuario
    return render_template("menu.html", menu=MENU, usuario=usuario,
                           beneficios=BENEFICIOS, puntos_por_peso=PUNTOS_POR_PESO)

@app.route("/login", methods=["POST"])
def login():
    email    = request.form.get("email","").strip().lower()
    password = request.form.get("password","")
    next_url = request.form.get("next","/")
    if not email or not password:
        return redirect("/?auth_error=Completá+todos+los+campos&tab=login")
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM usuarios WHERE email=%s", (email,))
    u = c.fetchone(); c.close(); conn.close()
    if not u: return redirect("/?auth_error=No+existe+una+cuenta+con+ese+email&tab=login")
    if u["password"] != hashear(password): return redirect("/?auth_error=Contraseña+incorrecta&tab=login")
    session["usuario"] = {"email": email, "nombre": u["nombre"], "puntos": u["puntos"]}
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
        conn = get_db(); c = conn.cursor()
        c.execute("INSERT INTO usuarios (nombre,email,password,creado_en,puntos) VALUES (%s,%s,%s,%s,%s)",
                  (nombre, email, hashear(password), datetime.datetime.now().isoformat(), 0))
        conn.commit(); c.close(); conn.close()
    except psycopg.errors.UniqueViolation:
        return redirect("/?auth_error=Ese+email+ya+está+registrado&tab=login")
    session["usuario"] = {"email": email, "nombre": nombre, "puntos": 0}
    return redirect(next_url)

@app.route("/logout")
def logout():
    session.pop("usuario", None)
    return redirect("/")

@app.route("/pedido", methods=["POST"])
def pedido():
    if not usuario_logueado(): return jsonify({"error":"no_auth"}), 401
    datos   = request.get_json()
    items   = datos.get("items", [])
    total   = datos.get("total", 0)
    tipo    = datos.get("tipo", "local")
    pago    = datos.get("pago", "efectivo")
    usuario = session["usuario"]
    if not items: return jsonify({"error":"Carrito vacío"}), 400

    puntos_ganados = total // PUNTOS_POR_PESO
    conn = get_db(); c = conn.cursor()
    c.execute("""INSERT INTO pedidos
                 (usuario_email,usuario_nombre,items,total,puntos_ganados,tipo,pago,estado,hora)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
              (usuario["email"], usuario["nombre"], json.dumps(items), total,
               puntos_ganados, tipo, pago, "pendiente",
               datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")))
    c.execute("UPDATE usuarios SET puntos = puntos + %s WHERE email = %s",
              (puntos_ganados, usuario["email"]))
    conn.commit()
    c.execute("SELECT puntos FROM usuarios WHERE email=%s", (usuario["email"],))
    nuevos_puntos = c.fetchone()["puntos"]
    c.close(); conn.close()
    usuario["puntos"] = nuevos_puntos
    session["usuario"] = usuario
    return jsonify({"ok": True, "puntos_ganados": puntos_ganados, "puntos_total": nuevos_puntos})

@app.route("/canjear", methods=["POST"])
def canjear():
    if not usuario_logueado(): return jsonify({"error":"no_auth"}), 401
    datos = request.get_json()
    beneficio_id = datos.get("beneficio_id")
    usuario = session["usuario"]
    beneficio = next((b for b in BENEFICIOS if b["id"] == beneficio_id), None)
    if not beneficio: return jsonify({"error":"Beneficio no encontrado"}), 404
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT puntos FROM usuarios WHERE email=%s", (usuario["email"],))
    puntos_actuales = c.fetchone()["puntos"]
    if puntos_actuales < beneficio["puntos"]:
        c.close(); conn.close()
        return jsonify({"error":"Puntos insuficientes"}), 400
    c.execute("UPDATE usuarios SET puntos = puntos - %s WHERE email = %s",
              (beneficio["puntos"], usuario["email"]))
    c.execute("""INSERT INTO canjes (usuario_email,beneficio_id,beneficio_nombre,puntos_usados,hora)
                 VALUES (%s,%s,%s,%s,%s)""",
              (usuario["email"], beneficio_id, beneficio["nombre"], beneficio["puntos"],
               datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")))
    conn.commit()
    c.execute("SELECT puntos FROM usuarios WHERE email=%s", (usuario["email"],))
    nuevos_puntos = c.fetchone()["puntos"]
    c.close(); conn.close()
    usuario["puntos"] = nuevos_puntos
    session["usuario"] = usuario
    return jsonify({"ok": True, "puntos_restantes": nuevos_puntos, "beneficio": beneficio["nombre"]})

# ===== RUTAS ADMIN =====
@app.route("/admin")
def admin_redirect():
    return redirect("/admin/login")

@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if admin_logueado(): return redirect("/admin/panel")
    error = None
    if request.method == "POST":
        email    = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        conn = get_db(); c = conn.cursor()
        c.execute("SELECT * FROM admins WHERE email=%s", (email,))
        a = c.fetchone(); c.close(); conn.close()
        if not a or a["password"] != hashear(password):
            error = "Credenciales incorrectas"
        else:
            session["admin"] = {"email": email, "nombre": a["nombre"]}
            return redirect("/admin/panel")
    return render_template("admin_login.html", error=error)

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/admin/login")

@app.route("/admin/panel")
def admin_panel():
    if not admin_logueado(): return redirect("/admin/login")
    return render_template("admin_panel.html", admin=admin_logueado())

@app.route("/admin/api/pedidos")
def admin_api_pedidos():
    if not admin_logueado(): return jsonify({"error":"no_auth"}), 401
    estado = request.args.get("estado","todos")
    conn = get_db(); c = conn.cursor()
    if estado == "todos":
        c.execute("SELECT * FROM pedidos ORDER BY id DESC LIMIT 100")
    else:
        c.execute("SELECT * FROM pedidos WHERE estado=%s ORDER BY id DESC LIMIT 100", (estado,))
    rows = c.fetchall(); c.close(); conn.close()
    pedidos = []
    for r in rows:
        pedidos.append({
            "id": r["id"],
            "usuario_nombre": r["usuario_nombre"],
            "usuario_email":  r["usuario_email"],
            "items":          json.loads(r["items"]),
            "total":          r["total"],
            "puntos_ganados": r["puntos_ganados"],
            "tipo":           r["tipo"],
            "pago":           r["pago"],
            "estado":         r["estado"],
            "hora":           r["hora"],
        })
    return jsonify(pedidos)

@app.route("/admin/api/pedidos/<int:pid>/estado", methods=["POST"])
def admin_cambiar_estado(pid):
    if not admin_logueado(): return jsonify({"error":"no_auth"}), 401
    datos = request.get_json()
    nuevo_estado = datos.get("estado")
    if nuevo_estado not in ("pendiente","en_preparacion","listo","entregado"):
        return jsonify({"error":"Estado inválido"}), 400
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE pedidos SET estado=%s WHERE id=%s", (nuevo_estado, pid))
    conn.commit(); c.close(); conn.close()
    return jsonify({"ok": True})

@app.route("/admin/api/stats")
def admin_stats():
    if not admin_logueado(): return jsonify({"error":"no_auth"}), 401
    conn = get_db(); c = conn.cursor()
    hoy = datetime.datetime.now().strftime("%d/%m/%Y")
    c.execute("SELECT COALESCE(SUM(total),0) as t FROM pedidos WHERE hora LIKE %s", (hoy+"%",))
    total_hoy = c.fetchone()["t"]
    c.execute("SELECT COUNT(*) as cnt FROM pedidos WHERE hora LIKE %s", (hoy+"%",))
    cant_hoy = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) as cnt FROM pedidos WHERE estado='pendiente'")
    pendientes = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) as cnt FROM pedidos WHERE estado='en_preparacion'")
    en_prep = c.fetchone()["cnt"]
    c.close(); conn.close()
    return jsonify({"total_hoy": total_hoy, "cant_hoy": cant_hoy,
                    "pendientes": pendientes, "en_preparacion": en_prep})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
