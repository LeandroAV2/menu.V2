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
    headers = {"Authorization": f"Bearer {MPAT}", "Content-Type": "application/json"}
    try:
        r = http_requests.post("https://api.mercadopago.com/checkout/preferences",
                               json=body, headers=headers, timeout=15)
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
    c.execute("""CREATE TABLE IF NOT EXISTS menu_categorias (
        id SERIAL PRIMARY KEY,
        clave TEXT UNIQUE NOT NULL,
        nombre TEXT NOT NULL,
        emoji TEXT NOT NULL DEFAULT '',
        orden INTEGER NOT NULL DEFAULT 0,
        activo BOOLEAN NOT NULL DEFAULT TRUE
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS menu_subcategorias (
        id SERIAL PRIMARY KEY,
        categoria_clave TEXT NOT NULL,
        clave TEXT NOT NULL,
        nombre TEXT NOT NULL,
        orden INTEGER NOT NULL DEFAULT 0,
        activo BOOLEAN NOT NULL DEFAULT TRUE
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS menu_items (
        id SERIAL PRIMARY KEY,
        subcategoria_id INTEGER NOT NULL,
        nombre TEXT NOT NULL,
        descripcion TEXT NOT NULL DEFAULT '',
        precio INTEGER NOT NULL,
        emoji TEXT NOT NULL DEFAULT '',
        orden INTEGER NOT NULL DEFAULT 0,
        activo BOOLEAN NOT NULL DEFAULT TRUE
    )""")
    # Poblar menu inicial si esta vacio
    c.execute("SELECT COUNT(*) as cnt FROM menu_categorias")
    if c.fetchone()["cnt"] == 0:
        cats = [
            ("comidas", "Comidas", "", 1),
            ("bebidas", "Bebidas", "", 2),
            ("postres", "Postres", "", 3),
        ]
        for cat in cats:
            c.execute("INSERT INTO menu_categorias (clave,nombre,emoji,orden) VALUES (%s,%s,%s,%s)", cat)
        subcats = [
            ("comidas","pastas","Pastas",1),
            ("comidas","carnes","Carnes",2),
            ("comidas","sandwiches","Sandwiches",3),
            ("comidas","ensaladas","Ensaladas",4),
            ("bebidas","cervezas","Cervezas",1),
            ("bebidas","gaseosas","Gaseosas",2),
            ("bebidas","aguas","Aguas",3),
            ("bebidas","vinos","Vinos",4),
            ("postres","helados","Helados",1),
            ("postres","tortas","Tortas",2),
            ("postres","otros","Otros postres",3),
        ]
        for s in subcats:
            c.execute("INSERT INTO menu_subcategorias (categoria_clave,clave,nombre,orden) VALUES (%s,%s,%s,%s)", s)
        items_data = [
            ("pastas","Ñoquis","Salsa de tomate fresco, albahaca y parmesano",2100,"",1),
            ("pastas","Tallarines a la bolognesa","Carne vacuna, zanahoria, vino tinto",2400,"",2),
            ("pastas","Sorrentinos de ricotta","Rellenos de ricotta y espinaca, salsa blanca",2700,"",3),
            ("carnes","Milanesa napolitana","Con jamon, mozzarella y salsa de tomate",3200,"",1),
            ("carnes","Bife de chorizo","A la plancha con papas fritas",4100,"",2),
            ("carnes","Pollo a la plancha","Con ensalada mixta y papas al horno",2900,"",3),
            ("carnes","Asado","Fuente como para 2 personas",3800,"",4),
            ("sandwiches","Lomito completo","Lomito, jamon, queso, lechuga, tomate, huevo",2600,"",1),
            ("sandwiches","Hamburguesa clasica","200g de carne, cheddar, pepino, cebolla",2200,"",2),
            ("sandwiches","Club sandwich","Pollo, panceta, lechuga, tomate, mayonesa",2400,"",3),
            ("ensaladas","Ensalada Cesar","Pollo grillado, lechuga romana, crutones",1900,"",1),
            ("ensaladas","Ensalada mixta","Lechuga, tomate, zanahoria, choclo",1400,"",2),
            ("cervezas","Cerveza Brahma","Cerveza clasica",900,"",1),
            ("cervezas","Cerveza Andes negra 473cc","Aroma y sabor tostado",1000,"",2),
            ("gaseosas","Coca-Cola 500cc","Botella personal bien fria",700,"",1),
            ("gaseosas","Sprite 500cc","Lima limon refrescante",700,"",2),
            ("gaseosas","Fanta naranja 500cc","Sabor naranja",700,"",3),
            ("aguas","Agua sin gas 500cc","Botella individual",500,"",1),
            ("aguas","Agua con gas 500cc","Con burbujas",550,"",2),
            ("aguas","Agua saborizada","Pomelo, Manzana y Pera",650,"",3),
            ("vinos","Malbec copa","Mendoza, 150cc",1200,"",1),
            ("helados","Helado 2 bochas","Dulce de leche, chocolate, vainilla o frutilla",900,"",1),
            ("helados","Helado 3 bochas","A eleccion con salsa o granizado",1200,"",2),
            ("tortas","Torta de chocolate","Con ganache y crema batida",1400,"",1),
            ("tortas","Cheesecake de frutos rojos","Base de galleta, queso crema, coulis",1500,"",2),
            ("otros","Tiramisu","Receta italiana clasica con mascarpone",1300,"",1),
            ("otros","Panqueques con dulce de leche","Con crema y nueces",1100,"",2),
            ("otros","Flan con crema","Casero, con caramelo y crema batida",950,"",3),
        ]
        for it in items_data:
            c.execute("SELECT id FROM menu_subcategorias WHERE clave=%s", (it[0],))
            sub = c.fetchone()
            if sub:
                c.execute("INSERT INTO menu_items (subcategoria_id,nombre,descripcion,precio,emoji,orden) VALUES (%s,%s,%s,%s,%s,%s)",
                          (sub["id"], it[1], it[2], it[3], it[4], it[5]))
    c.execute("""INSERT INTO config (clave, valor) VALUES ('puntos_por_peso', '50')
                 ON CONFLICT (clave) DO NOTHING""")
    beneficios_default = [
        ('15% de descuento en tu proxima visita', '15% off en cualquier pedido', 800, ''),
        ('Cafe con medialunas', '2 medialunas + cafe o te a eleccion', 400, ''),
        ('Hamburguesa con guarnicion y gaseosa', 'Hamburguesa clasica + papas fritas + gaseosa 500cc', 1200, ''),
        ('Postre gratis', 'Cualquier postre de la carta sin cargo', 500, ''),
        ('Bebida gratis', 'Gaseosa, agua o cerveza rubia sin cargo', 300, ''),
        ('Menu del dia gratis', 'El menu completo del dia sin cargo', 1500, ''),
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

def get_menu_db():
    """Construye el MENU desde la base de datos."""
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM menu_categorias WHERE activo=TRUE ORDER BY orden")
    cats = c.fetchall()
    menu = {"menu_del_dia": {
        "nombre": "Milanesa napolitana + guarnicion + postre",
        "descripcion": "Incluye bebida sin alcohol. Disponible hasta las 15:00 hs",
        "precio": 3800, "emoji": ""
    }, "categorias": {}}
    for cat in cats:
        c.execute("SELECT * FROM menu_subcategorias WHERE categoria_clave=%s AND activo=TRUE ORDER BY orden",
                  (cat["clave"],))
        subcats = c.fetchall()
        subcategorias = {}
        for sub in subcats:
            c.execute("SELECT * FROM menu_items WHERE subcategoria_id=%s AND activo=TRUE ORDER BY orden",
                      (sub["id"],))
            items = c.fetchall()
            subcategorias[sub["clave"]] = {
                "nombre": sub["nombre"],
                "items": [{"id": it["id"], "nombre": it["nombre"], "desc": it["descripcion"],
                           "precio": it["precio"], "emoji": it["emoji"]} for it in items]
            }
        menu["categorias"][cat["clave"]] = {
            "nombre": cat["nombre"], "emoji": cat["emoji"],
            "subcategorias": subcategorias
        }
    c.close(); conn.close()
    return menu

def get_beneficios():
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM beneficios WHERE activo=TRUE ORDER BY puntos ASC")
    rows = c.fetchall(); c.close(); conn.close()
    return [dict(r) for r in rows]

def get_puntos_por_peso():
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT valor FROM config WHERE clave='puntos_por_peso'")
    row = c.fetchone(); c.close(); conn.close()
    return int(row["valor"]) if row else 50

# ===== MENÚ =====
MENU = {
    "menu_del_dia": {
        "nombre": "Milanesa napolitana + guarnicion + postre",
        "descripcion": "Incluye bebida sin alcohol. Disponible hasta las 15:00 hs",
        "precio": 3800, "emoji": ""
    },
    "categorias": {
        "comidas": {
            "nombre": "Comidas", "emoji": "",
            "subcategorias": {
                "pastas": {"nombre": "Pastas", "items": [
                    {"id":1,  "nombre":"Ñoquis",                   "desc":"Salsa de tomate fresco, albahaca y parmesano", "precio":2100, "emoji":""},
                    {"id":2,  "nombre":"Tallarines a la bolognesa", "desc":"Carne vacuna, zanahoria, vino tinto",          "precio":2400, "emoji":""},
                    {"id":3,  "nombre":"Sorrentinos de ricotta",    "desc":"Rellenos de ricotta y espinaca, salsa blanca", "precio":2700, "emoji":""}
                ]},
                "carnes": {"nombre": "Carnes", "items": [
                    {"id":10, "nombre":"Milanesa napolitana", "desc":"Con jamon, mozzarella y salsa de tomate",  "precio":3200, "emoji":""},
                    {"id":11, "nombre":"Bife de chorizo",     "desc":"A la plancha con papas fritas",            "precio":4100, "emoji":""},
                    {"id":12, "nombre":"Pollo a la plancha",  "desc":"Con ensalada mixta y papas al horno",      "precio":2900, "emoji":""},
                    {"id":13, "nombre":"Asado",               "desc":"Fuente como para 2 personas",              "precio":3800, "emoji":""}
                ]},
                "sandwiches": {"nombre": "Sandwiches", "items": [
                    {"id":20, "nombre":"Lomito completo",     "desc":"Lomito, jamon, queso, lechuga, tomate, huevo", "precio":2600, "emoji":""},
                    {"id":21, "nombre":"Hamburguesa clasica", "desc":"200g de carne, cheddar, pepino, cebolla",      "precio":2200, "emoji":""},
                    {"id":22, "nombre":"Club sandwich",       "desc":"Pollo, panceta, lechuga, tomate, mayonesa",    "precio":2400, "emoji":""}
                ]},
                "ensaladas": {"nombre": "Ensaladas", "items": [
                    {"id":30, "nombre":"Ensalada Cesar",  "desc":"Pollo grillado, lechuga romana, crutones", "precio":1900, "emoji":""},
                    {"id":31, "nombre":"Ensalada mixta",  "desc":"Lechuga, tomate, zanahoria, choclo",       "precio":1400, "emoji":""}
                ]}
            }
        },
        "bebidas": {
            "nombre": "Bebidas", "emoji": "",
            "subcategorias": {
                "cervezas": {"nombre": "Cervezas", "items": [
                    {"id":40, "nombre":"Cerveza Brahma",             "desc":"Cerveza clasica",       "precio":900,  "emoji":""},
                    {"id":41, "nombre":"Cerveza Andes negra 473cc",  "desc":"Aroma y sabor tostado", "precio":1000, "emoji":""}
                ]},
                "gaseosas": {"nombre": "Gaseosas", "items": [
                    {"id":50, "nombre":"Coca-Cola 500cc",    "desc":"Botella personal bien fria", "precio":700, "emoji":""},
                    {"id":51, "nombre":"Sprite 500cc",       "desc":"Lima limon refrescante",     "precio":700, "emoji":""},
                    {"id":52, "nombre":"Fanta naranja 500cc","desc":"Sabor naranja",              "precio":700, "emoji":""}
                ]},
                "aguas": {"nombre": "Aguas", "items": [
                    {"id":60, "nombre":"Agua sin gas 500cc", "desc":"Botella individual",      "precio":500, "emoji":""},
                    {"id":61, "nombre":"Agua con gas 500cc", "desc":"Con burbujas",            "precio":550, "emoji":""},
                    {"id":62, "nombre":"Agua saborizada",    "desc":"Pomelo, Manzana y Pera",  "precio":650, "emoji":""}
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
                    {"id":81, "nombre":"Helado 3 bochas", "desc":"A eleccion con salsa o granizado",               "precio":1200, "emoji":""}
                ]},
                "tortas": {"nombre": "Tortas", "items": [
                    {"id":90, "nombre":"Torta de chocolate",        "desc":"Con ganache y crema batida",            "precio":1400, "emoji":""},
                    {"id":91, "nombre":"Cheesecake de frutos rojos", "desc":"Base de galleta, queso crema, coulis", "precio":1500, "emoji":""}
                ]},
                "otros": {"nombre": "Otros postres", "items": [
                    {"id":100, "nombre":"Tiramisu",                     "desc":"Receta italiana clasica con mascarpone", "precio":1300, "emoji":""},
                    {"id":101, "nombre":"Panqueques con dulce de leche", "desc":"Con crema y nueces",                   "precio":1100, "emoji":""},
                    {"id":102, "nombre":"Flan con crema",               "desc":"Casero, con caramelo y crema batida",   "precio":950,  "emoji":""}
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
    menu = get_menu_db()
    return render_template("menu.html", menu=menu, usuario=usuario,
                           beneficios=beneficios, puntos_por_peso=puntos_por_peso)

@app.route("/login", methods=["POST"])
def login():
    email    = request.form.get("email","").strip().lower()
    password = request.form.get("password","")
    next_url = request.form.get("next","/")
    if not email or not password:
        return redirect("/?auth_error=Completa+todos+los+campos&tab=login")
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM usuarios WHERE email=%s", (email,))
    u = c.fetchone(); c.close(); conn.close()
    if not u: return redirect("/?auth_error=No+existe+una+cuenta+con+ese+email&tab=login")
    if u["password"] != hashear(password): return redirect("/?auth_error=Contrasena+incorrecta&tab=login")
    session["usuario"] = {"email": email, "nombre": u["nombre"], "puntos": u["puntos"]}
    return redirect(next_url)

@app.route("/registro", methods=["POST"])
def registro():
    nombre   = request.form.get("nombre","").strip()
    email    = request.form.get("email","").strip().lower()
    password = request.form.get("password","")
    next_url = request.form.get("next","/")
    if not nombre or not email or not password:
        return redirect("/?auth_error=Completa+todos+los+campos&tab=registro")
    if "@" not in email or "." not in email:
        return redirect("/?auth_error=Email+invalido&tab=registro")
    if len(password) < 6:
        return redirect("/?auth_error=La+contrasena+debe+tener+al+menos+6+caracteres&tab=registro")
    try:
        conn = get_db(); c = conn.cursor()
        c.execute("INSERT INTO usuarios (nombre,email,password,creado_en,puntos) VALUES (%s,%s,%s,%s,%s)",
                  (nombre, email, hashear(password), datetime.datetime.now().isoformat(), 0))
        conn.commit(); c.close(); conn.close()
    except psycopg.errors.UniqueViolation:
        return redirect("/?auth_error=Ese+email+ya+esta+registrado&tab=login")
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
    if not items: return jsonify({"error":"Carrito vacio"}), 400
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
    if not items: return jsonify({"error":"Carrito vacio"}), 400
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
        mp_items, usuario["email"], back_urls,
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
    payment_id    = request.args.get("payment_id","")
    status        = request.args.get("status","")
    preference_id = request.args.get("preference_id","")
    if status == "approved" and payment_id:
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
                c.execute("SELECT id FROM pedidos WHERE pago=%s AND usuario_email=%s AND total=%s",
                          ("mercadopago", payer_email, total))
                if not c.fetchone():
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
        f"pedido-{pedido_id}", request.host_url+"mp/webhook"
    )
    if status not in (200, 201):
        return jsonify({"error": "Error generando QR"}), 500
    return jsonify({"preference_id": pref["id"], "init_point": pref["init_point"], "qr_data": pref["init_point"]})

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
        return jsonify({"error":"Estado invalido"}), 400
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
        return jsonify({"error":"Datos invalidos"}), 400
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
        return jsonify({"error":"Datos invalidos"}), 400
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


# ===== ADMIN — MENU =====
@app.route("/admin/api/menu")
def admin_get_menu():
    if not admin_logueado(): return jsonify({"error":"no_auth"}), 401
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM menu_categorias ORDER BY orden")
    cats = c.fetchall()
    result = []
    for cat in cats:
        c.execute("SELECT * FROM menu_subcategorias WHERE categoria_clave=%s ORDER BY orden", (cat["clave"],))
        subcats = c.fetchall()
        subs = []
        for sub in subcats:
            c.execute("SELECT * FROM menu_items WHERE subcategoria_id=%s ORDER BY orden", (sub["id"],))
            items = [dict(it) for it in c.fetchall()]
            subs.append({**dict(sub), "items": items})
        result.append({**dict(cat), "subcategorias": subs})
    c.close(); conn.close()
    return jsonify(result)

@app.route("/admin/api/menu/categorias", methods=["POST"])
def admin_crear_categoria():
    if not admin_logueado(): return jsonify({"error":"no_auth"}), 401
    d = request.get_json()
    nombre = d.get("nombre","").strip()
    emoji  = d.get("emoji","").strip()
    if not nombre: return jsonify({"error":"Nombre requerido"}), 400
    clave = nombre.lower().replace(" ","_").replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT COALESCE(MAX(orden),0)+1 as o FROM menu_categorias")
    orden = c.fetchone()["o"]
    c.execute("INSERT INTO menu_categorias (clave,nombre,emoji,orden) VALUES (%s,%s,%s,%s) RETURNING id",
              (clave, nombre, emoji, orden))
    new_id = c.fetchone()["id"]
    conn.commit(); c.close(); conn.close()
    return jsonify({"ok": True, "id": new_id, "clave": clave})

@app.route("/admin/api/menu/categorias/<int:cid>", methods=["PUT"])
def admin_editar_categoria(cid):
    if not admin_logueado(): return jsonify({"error":"no_auth"}), 401
    d = request.get_json()
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE menu_categorias SET nombre=%s,emoji=%s,activo=%s WHERE id=%s",
              (d.get("nombre",""), d.get("emoji",""), d.get("activo",True), cid))
    conn.commit(); c.close(); conn.close()
    return jsonify({"ok": True})

@app.route("/admin/api/menu/categorias/<int:cid>", methods=["DELETE"])
def admin_eliminar_categoria(cid):
    if not admin_logueado(): return jsonify({"error":"no_auth"}), 401
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE menu_categorias SET activo=FALSE WHERE id=%s", (cid,))
    conn.commit(); c.close(); conn.close()
    return jsonify({"ok": True})

@app.route("/admin/api/menu/subcategorias", methods=["POST"])
def admin_crear_subcategoria():
    if not admin_logueado(): return jsonify({"error":"no_auth"}), 401
    d = request.get_json()
    nombre         = d.get("nombre","").strip()
    categoria_clave = d.get("categoria_clave","").strip()
    if not nombre or not categoria_clave: return jsonify({"error":"Datos requeridos"}), 400
    clave = nombre.lower().replace(" ","_").replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT COALESCE(MAX(orden),0)+1 as o FROM menu_subcategorias WHERE categoria_clave=%s", (categoria_clave,))
    orden = c.fetchone()["o"]
    c.execute("INSERT INTO menu_subcategorias (categoria_clave,clave,nombre,orden) VALUES (%s,%s,%s,%s) RETURNING id",
              (categoria_clave, clave, nombre, orden))
    new_id = c.fetchone()["id"]
    conn.commit(); c.close(); conn.close()
    return jsonify({"ok": True, "id": new_id})

@app.route("/admin/api/menu/subcategorias/<int:sid>", methods=["PUT"])
def admin_editar_subcategoria(sid):
    if not admin_logueado(): return jsonify({"error":"no_auth"}), 401
    d = request.get_json()
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE menu_subcategorias SET nombre=%s,activo=%s WHERE id=%s",
              (d.get("nombre",""), d.get("activo",True), sid))
    conn.commit(); c.close(); conn.close()
    return jsonify({"ok": True})

@app.route("/admin/api/menu/subcategorias/<int:sid>", methods=["DELETE"])
def admin_eliminar_subcategoria(sid):
    if not admin_logueado(): return jsonify({"error":"no_auth"}), 401
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE menu_subcategorias SET activo=FALSE WHERE id=%s", (sid,))
    conn.commit(); c.close(); conn.close()
    return jsonify({"ok": True})

@app.route("/admin/api/menu/items", methods=["POST"])
def admin_crear_item():
    if not admin_logueado(): return jsonify({"error":"no_auth"}), 401
    d = request.get_json()
    nombre        = d.get("nombre","").strip()
    descripcion   = d.get("desc","").strip()
    precio        = int(d.get("precio", 0))
    emoji         = d.get("emoji","").strip()
    subcategoria_id = int(d.get("subcategoria_id", 0))
    if not nombre or precio <= 0 or not subcategoria_id:
        return jsonify({"error":"Datos invalidos"}), 400
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT COALESCE(MAX(orden),0)+1 as o FROM menu_items WHERE subcategoria_id=%s", (subcategoria_id,))
    orden = c.fetchone()["o"]
    c.execute("INSERT INTO menu_items (subcategoria_id,nombre,descripcion,precio,emoji,orden) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
              (subcategoria_id, nombre, descripcion, precio, emoji, orden))
    new_id = c.fetchone()["id"]
    conn.commit(); c.close(); conn.close()
    return jsonify({"ok": True, "id": new_id})

@app.route("/admin/api/menu/items/<int:iid>", methods=["PUT"])
def admin_editar_item(iid):
    if not admin_logueado(): return jsonify({"error":"no_auth"}), 401
    d = request.get_json()
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE menu_items SET nombre=%s,descripcion=%s,precio=%s,emoji=%s,activo=%s WHERE id=%s",
              (d.get("nombre",""), d.get("desc",""), int(d.get("precio",0)),
               d.get("emoji",""), d.get("activo",True), iid))
    conn.commit(); c.close(); conn.close()
    return jsonify({"ok": True})

@app.route("/admin/api/menu/items/<int:iid>", methods=["DELETE"])
def admin_eliminar_item(iid):
    if not admin_logueado(): return jsonify({"error":"no_auth"}), 401
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE menu_items SET activo=FALSE WHERE id=%s", (iid,))
    conn.commit(); c.close(); conn.close()
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
