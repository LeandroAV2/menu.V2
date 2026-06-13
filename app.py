from flask import Flask, render_template, request, redirect, session, jsonify
import hashlib, datetime, os, json
import psycopg
from psycopg.rows import dict_row
import requests as http_requests

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "tumenu_secret_2025")

DATABASE_URL = os.environ.get("DATABASE_URL")
MPAT = os.environ.get("MPAT", "")
MPPK = os.environ.get("MPPK", "")

def mp_post(endpoint, body):
    """Llama a la API de MP directamente por HTTP."""
    url = f"https://api.mercadopago.com/checkout/preferences"
    if endpoint != "preference":
        url = f"https://api.mercadopago.com/{endpoint}"
    headers = {
        "Authorization": f"Bearer {MPAT}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": datetime.datetime.now().isoformat()
    }
    r = http_requests.post(url, json=body, headers=headers, timeout=10)
    return r.status_code, r.json()

def mp_get(endpoint):
    headers = {"Authorization": f"Bearer {MPAT}"}
    r = http_requests.get(f"https://api.mercadopago.com/{endpoint}", headers=headers, timeout=10)
    return r.status_code, r.json()

def mp_api_preferencia(items_mp, payer_email, back_urls, external_reference, notification_url):
    def to_https(url):
        return url.replace("http://", "https://")

    body = {
        "items": items_mp,
        "payer": {"email": payer_email},
        "back_urls": {
            "success": to_https(back_urls.get("success","")),
            "failure": to_https(back_urls.get("failure","")),
            "pending": to_https(back_urls.get("pending",""))
        },
        "external_reference": external_reference,
        "statement_descriptor": "TuMenu",
    }
    headers = {
        "Authorization": f"Bearer {MPAT}",
        "Content-Type": "application/json",
    }
    try:
        r = http_requests.post(
            "https://api.mercadopago.com/checkout/preferences",
            json=body, headers=headers, timeout=15
        )
        print("MP STATUS:", r.status_code, r.text[:300])
        return r.status_code, r.json()
    except Exception as e:
        print("MP EXCEPTION:", str(e))
        return 500, {"error": str(e)}

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
    c.execute("""CREATE TABLE IF NOT EXISTS beneficios (
        id SERIAL PRIMARY KEY,
        nombre TEXT NOT NULL,
        descripcion TEXT NOT NULL,
        puntos INTEGER NOT NULL,
        emoji TEXT NOT NULL DEFAULT '',
        activo BOOLEAN NOT NULL DEFAULT TRUE
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS pagos_mp (
        id SERIAL PRIMARY KEY,
        pedido_id INTEGER,
        preference_id TEXT,
        payment_id TEXT,
        estado TEXT NOT NULL DEFAULT 'pendiente',
        tipo TEXT NOT NULL DEFAULT 'checkout',
        total INTEGER NOT NULL,
        usuario_email TEXT NOT NULL,
        hora TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS config (
        clave TEXT PRIMARY KEY,
        valor TEXT NOT NULL
    )""")
    c.execute("""INSERT INTO config (clave, valor) VALUES ('puntos_por_peso', '50')
                 ON CONFLICT (clave) DO NOTHING""")
    beneficios_default = [
        ('15% de descuento en tu próxima visita', '15% off en cualquier pedido', 800,
        ('Café con medialunas', '2 medialunas + café o té a elección', 400),
        ('Hamburguesa con guarnición y gaseosa', 'Hamburguesa clásica + papas fritas + gaseosa 500cc', 1200),
        ('Postre gratis', 'Cualquier postre de la carta sin cargo', 500),
        ('Bebida gratis', 'Gaseosa, agua o cerveza rubia sin cargo', 300),
        ('Menú del día gratis', 'El menú completo del día sin cargo', 1500),
    ]
    for b in beneficios_default:
        c.execute("""INSERT INTO beneficios (nombre, descripcion, puntos, emoji)
                     SELECT %s, %s, %s, %s WHERE NOT EXISTS (SELECT 1 FROM beneficios WHERE nombre=%s)""",
                  (b[0], b[1], b[2], b[3], b[0]))
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

def get_beneficios():
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM beneficios WHERE activo=TRUE ORDER BY puntos ASC")
    rows = c.fetchall(); c.close(); conn.close()
    return [dict(r) for r in rows]

def get_puntos_por_peso():
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT valor FROM config WHERE clave='puntos_por_peso'")
    row = c.fetchone(); c.close(); conn.close()
    return int(row["valor"]) if row else 100

# ===== MENÚ =====
MENU = {
    "menu_del_dia": {
        "nombre": "Milanesa napolitana + guarnición + postre",
        "descripcion": "Incluye bebida sin alcohol. Disponible hasta las 15:00 hs",
        "precio": 3800, "emoji": ""
    },
    "categorias": {
        "comidas": {
            "nombre": "Comidas", "emoji": "",
            "subcategorias": {
                "pastas": {"nombre": "Pastas", "items": [
                    {"id":1,  "nombre":"Ñoquis",                  "desc":"Salsa de tomate fresco, albahaca y parmesano",    "precio":2100, "emoji":""},
                    {"id":2,  "nombre":"Tallarines a la bolognesa","desc":"Carne vacuna, zanahoria, vino tinto",              "precio":2400, "emoji":""},
                    {"id":3,  "nombre":"Sorrentinos de ricotta",   "desc":"Rellenos de ricotta y espinaca, salsa blanca",    "precio":2700, "emoji":""}
                ]},
                "carnes": {"nombre": "Carnes", "items": [
                    {"id":10, "nombre":"Milanesa napolitana",      "desc":"Con jamón, mozzarella y salsa de tomate",         "precio":3200, "emoji":""},
                    {"id":11, "nombre":"Bife de chorizo",          "desc":"A la plancha con papas fritas",                   "precio":4100, "emoji":""},
                    {"id":12, "nombre":"Pollo a la plancha",       "desc":"Con ensalada mixta y papas al horno",             "precio":2900, "emoji":""},
                    {"id":13, "nombre":"Asado",                    "desc":"Fuente como para 2 personas",                     "precio":3800, "emoji":""}
                ]},
                "sandwiches": {"nombre": "Sandwiches", "items": [
                    {"id":20, "nombre":"Lomito completo",          "desc":"Lomito, jamón, queso, lechuga, tomate, huevo",    "precio":2600, "emoji":""},
                    {"id":21, "nombre":"Hamburguesa clásica",      "desc":"200g de carne, cheddar, pepino, cebolla",         "precio":2200, "emoji":""},
                    {"id":22, "nombre":"Club sandwich",            "desc":"Pollo, panceta, lechuga, tomate, mayonesa",       "precio":2400, "emoji":""}
                ]},
                "ensaladas": {"nombre": "Ensaladas", "items": [
                    {"id":30, "nombre":"Ensalada César",           "desc":"Pollo grillado, lechuga romana, crutones",        "precio":1900, "emoji":""},
                    {"id":31, "nombre":"Ensalada mixta",           "desc":"Lechuga, tomate, zanahoria, choclo",              "precio":1400, "emoji":""}
                ]}
            }
        },
        "bebidas": {
            "nombre": "Bebidas", "emoji": "",
            "subcategorias": {
                "cervezas": {"nombre": "Cervezas", "items": [
                    {"id":40, "nombre":"Cerveza Brahma",                    "desc":"Cerveza clásica",                    "precio":900,  "emoji":""},
                    {"id":41, "nombre":"Cerveza Andes negra lata 473cc",    "desc":"Aroma y sabor tostado",             "precio":1000, "emoji":""}
                ]},
                "gaseosas": {"nombre": "Gaseosas", "items": [
                    {"id":50, "nombre":"Coca-Cola 500cc",  "desc":"Botella personal bien fría",  "precio":700, "emoji":""},
                    {"id":51, "nombre":"Sprite 500cc",     "desc":"Lima limón refrescante",      "precio":700, "emoji":""},
                    {"id":52, "nombre":"Fanta naranja 500cc","desc":"Sabor naranja",             "precio":700, "emoji":""}
                ]},
                "aguas": {"nombre": "Aguas", "items": [
                    {"id":60, "nombre":"Agua sin gas 500cc", "desc":"Botella individual",               "precio":500, "emoji":""},
                    {"id":61, "nombre":"Agua con gas 500cc", "desc":"Con burbujas",                     "precio":550, "emoji":""},
                    {"id":62, "nombre":"Agua saborizada",    "desc":"Pomelo, Manzana y Pera",           "precio":650, "emoji":""}
                ]},
                "vinos": {"nombre": "Vinos", "items": [
                    {"id":70, "nombre":"Malbec copa", "desc":"Mendoza, 150cc", "precio":1200, "emoji":""}
                ]}
            }
        },
        "postres": {
            "nombre": "Postres", "emoji": "",
            "subcategorias": {
                "helados": {"nombre": "Helados", "items": [
                    {"id":80, "nombre":"Helado 2 bochas", "desc":"Dulce de leche, chocolate, vainilla o frutilla", "precio":900,  "emoji":""},
                    {"id":81, "nombre":"Helado 3 bochas", "desc":"A elección con salsa o granizado",               "precio":1200, "emoji":""}
                ]},
                "tortas": {"nombre": "Tortas", "items": [
                    {"id":90, "nombre":"Torta de chocolate",       "desc":"Con ganache y crema batida",            "precio":1400, "emoji":""},
                    {"id":91, "nombre":"Cheesecake de frutos rojos","desc":"Base de galleta, queso crema, coulis", "precio":1500, "emoji":""}
                ]},
                "otros": {"nombre": "Otros postres", "items": [
                    {"id":100,"nombre":"Tiramisú",                    "desc":"Receta italiana clásica con mascarpone","precio":1300,"emoji":""},
                    {"id":101,"nombre":"Panqueques con dulce de leche","desc":"Con crema y nueces",                 "precio":1100,"emoji":""},
                    {"id":102,"nombre":"Flan con crema",              "desc":"Casero, con caramelo y crema batida", "precio":950, "emoji":""}
                ]}
            }
        }
    }
}

def hashear(p): return hashlib.sha256(p.encode()).hexdigest()
def usuario_logueado(): return session.get("usuario")
def admin_logueado(): return session.get("admin")

def get_puntos(email):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT puntos FROM usuarios WHERE email=%s", (email,))
    row = c.fetchone(); c.close(); conn.close()
    return row["puntos"] if row else 0

# ===== RUTAS CLIENTE =====
@app.route("/")
def index():
    usuario = usuario_logueado()
    if usuario:
        usuario["puntos"] = get_puntos(usuario["email"])
        session["usuario"] = usuario
    beneficios = get_beneficios()
    puntos_por_peso = get_puntos_por_peso()
    return render_template("menu.html", menu=MENU, usuario=usuario,
                           beneficios=beneficios, puntos_por_peso=puntos_por_peso)

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
    puntos_ganados = total // get_puntos_por_peso()
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
    conn2 = get_db(); c2 = conn2.cursor()
    c2.execute("SELECT * FROM beneficios WHERE id=%s AND activo=TRUE", (beneficio_id,))
    beneficio = c2.fetchone(); c2.close(); conn2.close()
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


# ===== MERCADO PAGO =====

@app.route("/mp/crear-preferencia", methods=["POST"])
def mp_crear_preferencia():
    if not usuario_logueado(): return jsonify({"error":"no_auth"}), 401
    datos   = request.get_json()
    items   = datos.get("items", [])
    total   = datos.get("total", 0)
    tipo    = datos.get("tipo", "local")
    usuario = session["usuario"]
    if not items: return jsonify({"error":"Carrito vacío"}), 400

    base_url = request.host_url.rstrip("/")
    mp_items = [{"title": i["nombre"], "quantity": i["cantidad"],
                 "unit_price": float(i["precio"]), "currency_id": "ARS"}
                for i in items]
    back_urls = {
        "success": base_url + "/mp/exito",
        "failure": base_url + "/mp/fallo",
        "pending": base_url + "/mp/pendiente"
    }
    status, pref = mp_api_preferencia(
        mp_items, usuario["email"],
        back_urls,
        usuario["email"]+"|"+tipo+"|"+datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
        base_url+"/mp/webhook"
    )
    if status not in (200, 201):
        print("MP ERROR:", status, pref)
        return jsonify({"error": "Error creando preferencia MP", "detalle": pref}), 500
    conn = get_db(); c = conn.cursor()
    c.execute("""INSERT INTO pagos_mp (preference_id, estado, tipo, total, usuario_email, hora)
                 VALUES (%s, %s, %s, %s, %s, %s)""",
              (pref["id"], "pendiente", "checkout", total, usuario["email"],
               datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")))
    conn.commit(); c.close(); conn.close()

    return jsonify({"init_point": pref["init_point"], "preference_id": pref["id"]})


@app.route("/mp/exito")
def mp_exito():
    payment_id       = request.args.get("payment_id","")
    status           = request.args.get("status","")
    preference_id    = request.args.get("preference_id","")
    external_ref     = request.args.get("external_reference","")

    if status == "approved" and payment_id:
        # Registrar pago aprobado
        conn = get_db(); c = conn.cursor()
        c.execute("UPDATE pagos_mp SET estado=%s, payment_id=%s WHERE preference_id=%s",
                  ("aprobado", payment_id, preference_id))
        conn.commit(); c.close(); conn.close()

    return redirect("/?pago=exito&payment_id=" + payment_id)


@app.route("/mp/fallo")
def mp_fallo():
    return redirect("/?pago=fallo")


@app.route("/mp/pendiente")
def mp_pendiente():
    return redirect("/?pago=pendiente")


@app.route("/mp/webhook", methods=["POST"])
def mp_webhook():
    data = request.get_json(silent=True) or {}
    topic = data.get("type") or request.args.get("topic","")
    resource_id = data.get("data",{}).get("id") or request.args.get("id","")

    if topic == "payment" and resource_id:
        status, payment = mp_get(f"v1/payments/{resource_id}")
        if status == 200:
            estado_mp   = payment.get("status","")
            pref_id     = payment.get("preference_id","")
            total       = int(payment.get("transaction_amount", 0))
            payer_email = payment.get("payer",{}).get("email","")
            ext_ref     = payment.get("external_reference","") or ""

            conn = get_db(); c = conn.cursor()
            c.execute("UPDATE pagos_mp SET estado=%s, payment_id=%s WHERE preference_id=%s",
                      (estado_mp, str(resource_id), pref_id))

            if estado_mp == "approved":
                c.execute(
                    "SELECT id FROM pedidos WHERE pago=%s AND usuario_email=%s AND total=%s",
                    ("mercadopago", payer_email, total)
                )
                existe = c.fetchone()
                if not existe:
                    tipo = "local"
                    if ext_ref and "|" in ext_ref:
                        partes = ext_ref.split("|")
                        if len(partes) >= 2:
                            tipo = partes[1]
                    items_json = json.dumps([{"nombre":"Pago Mercado Pago","cantidad":1,"precio":total}])
                    puntos_ganados = total // get_puntos_por_peso()
                    hora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    c.execute(
                        "INSERT INTO pedidos (usuario_email,usuario_nombre,items,total,puntos_ganados,tipo,pago,estado,hora) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (payer_email, payer_email, items_json, total, puntos_ganados, tipo, "mercadopago", "pendiente", hora)
                    )
                    c.execute("UPDATE usuarios SET puntos = puntos + %s WHERE email = %s",
                              (puntos_ganados, payer_email))

            conn.commit(); c.close(); conn.close()

    return jsonify({"ok": True}), 200


@app.route("/mp/qr/<int:pedido_id>")
def mp_qr(pedido_id):
    """Genera un QR de pago presencial para un pedido específico."""
    if not admin_logueado(): return jsonify({"error":"no_auth"}), 401
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM pedidos WHERE id=%s", (pedido_id,))
    ped = c.fetchone(); c.close(); conn.close()
    if not ped: return jsonify({"error":"Pedido no encontrado"}), 404

    items = json.loads(ped["items"])
    mp_items = [{"title": i["nombre"], "quantity": i["cantidad"],
                 "unit_price": float(i["precio"]), "currency_id": "ARS"}
                for i in items]
    status, pref = mp_api_preferencia(
        mp_items, "cliente@tumenu.com",
        {"success": request.host_url+"mp/exito",
         "failure": request.host_url+"mp/fallo",
         "pending": request.host_url+"mp/pendiente"},
        f"pedido-{pedido_id}",
        request.host_url+"mp/webhook"
    )
    if status not in (200, 201):
        return jsonify({"error": "Error generando QR"}), 500
    return jsonify({
        "preference_id": pref["id"],
        "init_point": pref["init_point"],
        "qr_data": pref["init_point"]  # el link que se convierte en QR en el frontend
    })

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
            "id":             r["id"],
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

@app.route("/admin/api/beneficios")
def admin_get_beneficios():
    if not admin_logueado(): return jsonify({"error":"no_auth"}), 401
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM beneficios ORDER BY puntos ASC")
    rows = c.fetchall(); c.close(); conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/admin/api/beneficios", methods=["POST"])
def admin_crear_beneficio():
    if not admin_logueado(): return jsonify({"error":"no_auth"}), 401
    d = request.get_json()
    nombre = d.get("nombre","").strip()
    descripcion = d.get("descripcion","").strip()
    puntos = int(d.get("puntos", 0))
    emoji = d.get("emoji","").strip()
    if not nombre or not descripcion or puntos <= 0:
        return jsonify({"error":"Datos inválidos"}), 400
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO beneficios (nombre,descripcion,puntos,emoji) VALUES (%s,%s,%s,%s) RETURNING id",
              (nombre, descripcion, puntos, emoji))
    new_id = c.fetchone()["id"]
    conn.commit(); c.close(); conn.close()
    return jsonify({"ok": True, "id": new_id})

@app.route("/admin/api/beneficios/<int:bid>", methods=["PUT"])
def admin_editar_beneficio(bid):
    if not admin_logueado(): return jsonify({"error":"no_auth"}), 401
    d = request.get_json()
    nombre = d.get("nombre","").strip()
    descripcion = d.get("descripcion","").strip()
    puntos = int(d.get("puntos", 0))
    emoji = d.get("emoji","").strip()
    activo = d.get("activo", True)
    if not nombre or not descripcion or puntos <= 0:
        return jsonify({"error":"Datos inválidos"}), 400
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE beneficios SET nombre=%s,descripcion=%s,puntos=%s,emoji=%s,activo=%s WHERE id=%s",
              (nombre, descripcion, puntos, emoji, activo, bid))
    conn.commit(); c.close(); conn.close()
    return jsonify({"ok": True})

@app.route("/admin/api/beneficios/<int:bid>", methods=["DELETE"])
def admin_eliminar_beneficio(bid):
    if not admin_logueado(): return jsonify({"error":"no_auth"}), 401
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE beneficios SET activo=FALSE WHERE id=%s", (bid,))
    conn.commit(); c.close(); conn.close()
    return jsonify({"ok": True})

@app.route("/admin/api/config", methods=["GET"])
def admin_get_config():
    if not admin_logueado(): return jsonify({"error":"no_auth"}), 401
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM config")
    rows = c.fetchall(); c.close(); conn.close()
    return jsonify({r["clave"]: r["valor"] for r in rows})

@app.route("/admin/api/config", methods=["POST"])
def admin_set_config():
    if not admin_logueado(): return jsonify({"error":"no_auth"}), 401
    d = request.get_json()
    conn = get_db(); c = conn.cursor()
    for clave, valor in d.items():
        c.execute("INSERT INTO config (clave,valor) VALUES (%s,%s) ON CONFLICT (clave) DO UPDATE SET valor=%s",
                  (clave, str(valor), str(valor)))
    conn.commit(); c.close(); conn.close()
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
