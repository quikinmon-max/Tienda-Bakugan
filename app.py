import streamlit as st
import pymongo
import base64
import random
import uuid
import urllib.parse
from datetime import datetime, timedelta
from PIL import Image, ImageOps, ImageFile
import io

# --- BLINDAJE PARA FOTOS PESADAS EN STREAMLIT CLOUD ---
ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None

# ---------------- CONFIGURACIÓN DE PÁGINA ----------------
st.set_page_config(
    page_title="Bakugan Market", 
    page_icon="🔥", 
    layout="wide"
)

# ---------------- CONFIGURACIÓN EXACTA DE TIEMPO (QUERÉTARO) ----------------
def hora_qro():
    return datetime.utcnow() - timedelta(hours=6)

# ---------------- INICIALIZAR MEMORIA Y SEMILLA ALEATORIA ----------------
if 'carrito' not in st.session_state:
    st.session_state.carrito = []

if 'rand_seed' not in st.session_state:
    st.session_state.rand_seed = random.randint(1, 999999)

# Variable para la Paginación (Control de velocidad)
if 'limite_items' not in st.session_state:
    st.session_state.limite_items = 12

# ---------------- CONEXIÓN A MONGODB ----------------
@st.cache_resource
def init_connection():
    MONGO_URI = st.secrets["MONGO_URI"] 
    client = pymongo.MongoClient(MONGO_URI)
    return client

client = init_connection()
db = client["bakugan_market"]
col_productos = db["productos"]
col_apartados = db["apartados"]
col_config = db["configuracion"] 
col_ventas = db["ventas"] 
col_carritos = db["carritos_temporales"] 

# ---------------- MIGRACIÓN DE PROMOS E INICIALIZACIÓN ----------------
config_promos = col_config.find_one({"_id": "promociones"})
if not config_promos:
    config_promos = {
        "volumen": [{"id": str(uuid.uuid4())[:8], "categoria": "Carta", "min_piezas": 5, "precio_fijo": 40.0, "activa": True}],
        "monto": [{"id": str(uuid.uuid4())[:8], "min_total": 2000.0, "porcentaje": 10.0, "activa": True}],
        "promo_3x2": False
    }
    col_config.insert_one({"_id": "promociones", **config_promos})
elif "promo_3x2" not in config_promos:
    config_promos["promo_3x2"] = False
    col_config.update_one({"_id": "promociones"}, {"$set": {"promo_3x2": False}})

viejos = col_apartados.find({"fecha_vencimiento": {"$exists": False}})
for v in viejos:
    fv = v.get("fecha_apartado", hora_qro()) + timedelta(days=3)
    col_apartados.update_one({"_id": v["_id"]}, {"$set": {"fecha_vencimiento": fv, "anticipo": 0.0}})

# ---------------- SISTEMA ANTICAÍDAS (CARRITO Y SESIÓN) ----------------
if 'session_id' not in st.session_state:
    if "sesion" in st.query_params:
        st.session_state.session_id = st.query_params["sesion"]
    else:
        st.session_state.session_id = str(uuid.uuid4())[:8] 
        st.query_params["sesion"] = st.session_state.session_id

if 'carrito' not in st.session_state or not st.session_state.carrito:
    carrito_guardado = col_carritos.find_one({"_id": st.session_state.session_id})
    if carrito_guardado:
        st.session_state.carrito = carrito_guardado.get("items", [])
    else:
        st.session_state.carrito = []

def guardar_carrito():
    col_carritos.update_one(
        {"_id": st.session_state.session_id},
        {"$set": {"items": st.session_state.carrito, "fecha": hora_qro()}},
        upsert=True
    )

if 'admin_autenticado' not in st.session_state:
    st.session_state.admin_autenticado = False

def comprimir_imagen(img_file):
    img_bytes = img_file.getvalue()
    img = Image.open(io.BytesIO(img_bytes))
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
    img.thumbnail((800, 800))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=70)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

@st.dialog("🔍 Modo Detalle")
def abrir_zoom(nombre_prod, imagenes_b64):
    st.markdown(f"### {nombre_prod}")
    html_galeria = '<div class="galeria-container">'
    for img_b64 in imagenes_b64:
        html_galeria += f'<img src="data:image/jpeg;base64,{img_b64}" class="galeria-ampliada-img">'
    html_galeria += '</div>'
    st.markdown(html_galeria, unsafe_allow_html=True)
    if len(imagenes_b64) > 1:
        st.markdown("<p style='text-align: center; color: #aaa; font-size: 14px; margin-top: 10px;'>👉 Desliza para ver más</p>", unsafe_allow_html=True)

# ---------------- EL CEREBRO DEL MENÚ 3X2 ----------------
@st.dialog("🎁 Menú de Regalos (Promo 3x2)")
def modal_regalo_3x2(precio_max):
    st.markdown(f"¡Felicidades! Como llevas 2 piezas, tienes derecho a elegir una tercera (valor hasta **${precio_max:,.2f}**) completamente **GRATIS**.")
    st.info("👇 Estas son las piezas que aplican para tu regalo. ¡Elige rápido antes de que te la ganen!")
    
    query = {
        "tipo": {"$nin": ["Carta", "BakuCore", "Extra"]},
        "stock": {"$gt": 0},
        "precio": {"$lte": precio_max}
    }
    regalos = list(col_productos.find(query).sort("precio", -1).limit(50))
    
    if not regalos:
        st.warning("Uy, parece que en este momento no tenemos piezas disponibles en este rango de precio.")
    else:
        for reg in regalos:
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"<span style='font-size:15px;'><b>{reg['nombre']}</b></span><br><span style='color:#2ecc71; font-weight:bold;'>${reg['precio']:,.2f}</span>", unsafe_allow_html=True)
            if c2.button("🎁 Elegir", key=f"btn_regalo_{reg['_id']}", use_container_width=True):
                st.session_state.carrito.append({
                    "_id": reg["_id"], "nombre": reg["nombre"],
                    "precio": reg["precio"], "variante": "normal", "tipo": reg.get("tipo", "Bakugan")
                })
                guardar_carrito()
                if "abrir_modal_3x2" in st.session_state: st.session_state.abrir_modal_3x2 = False
                st.rerun()
                
    st.markdown("---")
    if st.button("Elegir más tarde / Cerrar Menú", use_container_width=True):
        if "abrir_modal_3x2" in st.session_state: st.session_state.abrir_modal_3x2 = False
        st.rerun()

config_data = col_config.find_one({"_id": "sitio_prefs"})
fondo_b64 = config_data.get("fondo_b64") if config_data else None
logo_b64 = config_data.get("logo_b64") if config_data else None

# --- EL CSS EXTERMINADOR DEFINITIVO ---
css_global = f"""
<style>
/* 1. Mantenemos el encabezado visible pero transparente para salvar la hamburguesa */
header[data-testid="stHeader"] {{
    background: transparent !important;
    box-shadow: none !important;
    visibility: visible !important;
}}
[data-testid="collapsedControl"] {{ display: flex !important; visibility: visible !important; }}

/* 2. Ocultar Github, Fork, Deploy y Menú de los 3 puntitos */
.stDeployButton {{ display: none !important; }}
#MainMenu {{ display: none !important; }}
[data-testid="stToolbarActions"] {{ display: none !important; }}

/* 3. EXTERMINADOR NUCLEAR DE BADGES (N Morada y Barco Rojo) */
footer {{ visibility: hidden !important; display: none !important; }}
#creatorBadge {{ display: none !important; opacity: 0 !important; }}
div[data-testid="viewerBadge"] {{ display: none !important; opacity: 0 !important; }}
div[class*="viewerBadge"] {{ display: none !important; opacity: 0 !important; }}
div[class*="CreatorBadge"] {{ display: none !important; opacity: 0 !important; }}
a[href*="streamlit.io/cloud"] {{ display: none !important; pointer-events: none !important; }}
/* Bloquea iframes flotantes de badges */
iframe[title*="badge"] {{ display: none !important; opacity: 0 !important; pointer-events: none !important; }}
iframe[src*="badge"] {{ display: none !important; opacity: 0 !important; pointer-events: none !important; }}

.stApp {{
    {'background-image: url("data:image/png;base64,' + fondo_b64 + '");' if fondo_b64 else ''}
    background-size: cover; background-position: center; background-repeat: no-repeat; background-attachment: fixed;
}}
.block-container {{
    background-color: rgba(14, 17, 23, 0.85); 
    padding-top: 2.5rem !important; padding-right: 2rem; padding-bottom: 2rem; padding-left: 2rem;
    margin-top: 1rem; border-radius: 15px;
}}
.tarjeta-cliente {{
    background-color: rgba(255, 255, 255, 0.1); padding: 15px; border-radius: 10px; margin-bottom: 10px; border: 1px solid #444;
}}
.galeria-container {{
    display: flex; overflow-x: auto; scroll-snap-type: x mandatory; gap: 0;
    -ms-overflow-style: none; scrollbar-width: none; border-radius: 8px; margin-bottom: 5px;
}}
.galeria-container::-webkit-scrollbar {{ display: none; }}
.galeria-img {{
    scroll-snap-align: center; flex: 0 0 100%; width: 100%; aspect-ratio: 1 / 1 !important; 
    object-fit: cover !important; border-radius: 8px; background-color: transparent; 
}}
.galeria-ampliada-img {{
    scroll-snap-align: center; flex: 0 0 100%; width: 100%; max-height: 65vh; 
    object-fit: contain !important; border-radius: 8px; background-color: transparent; 
}}
@media (max-width: 768px) {{
    .block-container {{ padding-top: 3.5rem !important; margin-top: 0rem; }}
    .stTextInput input {{ font-size: 16px !important; padding: 0.6rem !important; }}
    .stButton > button {{ font-size: 16px !important; padding: 0.5rem 1rem !important; min-height: 2.8rem !important; }}
    div[data-testid="stPopover"] > button {{ font-size: 16px !important; padding: 0.6rem 1rem !important; min-height: 2.8rem !important; }}
}}
</style>
"""
st.markdown(css_global, unsafe_allow_html=True)

def mantenimiento_base_datos():
    ahora = hora_qro()
    vencidos = col_apartados.find({"fecha_vencimiento": {"$lt": ahora}})
    for doc in vencidos:
        campo = doc.get("campo_stock", "stock")
        col_productos.update_one({"_id": doc["producto_id"]}, {"$inc": {campo: 1}})
        col_apartados.delete_one({"_id": doc["_id"]})
    
    limite_cart = hora_qro() - timedelta(days=1)
    col_carritos.delete_many({"fecha": {"$lt": limite_cart}})

mantenimiento_base_datos()

categorias = ["Todos", "Pyrus 🔥", "Aquos 💧", "Ventus 🍃", "Darkus 🌑", "Haos ✨", "Subterra 🪨"]
materiales = ["Todas", "Metálica", "Cartón"]
simbolos_core = ["Todos", "Fist ✊", "Flaming Fist 🔥✊", "Shield 🛡️", "Magic Shield ✨🛡️", "Helix 🧬"]
tipos_producto = ["Bakugan", "Trampa", "Carta", "BakuCore", "Vehículo", "Armamento", "BakuTech", "Extra", "Set de Batalla", "Deka"]

if logo_b64:
    st.sidebar.markdown(f'<style>.logo-celular {{ width: 100%; border-radius: 8px; margin-bottom: 10px; }} @media (max-width: 768px) {{ .logo-celular {{ width: 45%; margin-left: auto; margin-right: auto; display: block; }} }} </style> <img src="data:image/png;base64,{logo_b64}" class="logo-celular">', unsafe_allow_html=True)
else:
    st.sidebar.markdown("### 🛒 Mi Tienda")

st.sidebar.header("Filtros Avanzados")

# Restablecer el límite de paginación si cambian los filtros
def reset_limite():
    st.session_state.limite_items = 12

tipo_busqueda = st.sidebar.selectbox("¿Qué buscas?", ["Todo el Catálogo 🌍", "Bakugans 🔥", "Trampas 🪤", "Cartas 🃏", "BakuCores 🛑", "Vehículos 🏎️", "Armamentos ⚔️", "BakuTech 🦾", "Extras 🎁", "Sets de Batalla 🏟️", "Deka 🌐", "Piezas / Detalles 🛠️"], on_change=reset_limite)

tipos_con_atributo_ui = ["Bakugans 🔥", "Trampas 🪤", "Vehículos 🏎️", "Armamentos ⚔️", "BakuTech 🦾", "Sets de Batalla 🏟️", "Deka 🌐"]

if tipo_busqueda in tipos_con_atributo_ui: sub_filtro = st.sidebar.selectbox("Filtra por Atributo", categorias, on_change=reset_limite)
elif tipo_busqueda == "Cartas 🃏": sub_filtro = st.sidebar.selectbox("Filtra por Material", materiales, on_change=reset_limite)
elif tipo_busqueda == "BakuCores 🛑": sub_filtro = st.sidebar.selectbox("Filtra por Símbolo", simbolos_core, on_change=reset_limite)
else: sub_filtro = "Todos"

es_admin_url = st.query_params.get("jefe") == "1"
vista_admin = "Catálogo" 

if es_admin_url:
    st.sidebar.markdown("---")
    if not st.session_state.admin_autenticado:
        admin_input = st.sidebar.text_input("🔑 Acceso Admin", type="password")
        if admin_input == st.secrets["ADMIN_PASS"]:
            st.session_state.admin_autenticado = True
            st.rerun()
        elif admin_input != "":
            st.sidebar.error("Contraseña incorrecta.")
    
    if st.session_state.admin_autenticado:
        st.sidebar.success("¡Bienvenido, jefe!")
        if st.sidebar.button("🚪 Cerrar Sesión"):
            st.session_state.admin_autenticado = False
            st.rerun()
        vista_admin = st.sidebar.radio("Opciones de Administrador", ["Ver Catálogo", "➕ Agregar Producto", "📋 Ver Apartados", "📊 Finanzas y Ventas", "🎨 Personalizar Página", "🎁 Gestor de Promociones"])

st.sidebar.markdown("<div style='height: 400px;'></div>", unsafe_allow_html=True)

if vista_admin == "🎁 Gestor de Promociones":
    st.title("🎁 Gestor de Promociones")
    st.markdown("Activa, desactiva o crea nuevas reglas para que se apliquen en automático al carrito de tus clientes.")
    
    st.markdown("### ➕ Crear Nueva Promoción")
    with st.container():
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            with st.expander("📦 Descuento por Volumen (Categoría a Precio Fijo)"):
                cat_nueva = st.selectbox("Categoría que recibe el descuento", tipos_producto)
                min_p = st.number_input("Cantidad mínima de piezas para activar", min_value=1, value=5)
                prec_f = st.number_input("Precio especial c/u ($)", min_value=1.0, value=40.0)
                if st.button("Guardar Promo de Volumen"):
                    config_promos["volumen"].append({"id": str(uuid.uuid4())[:8], "categoria": cat_nueva, "min_piezas": min_p, "precio_fijo": prec_f, "activa": True})
                    col_config.update_one({"_id": "promociones"}, {"$set": config_promos})
                    st.success("¡Promoción agregada!")
                    st.rerun()
        with col_t2:
            with st.expander("💰 Descuento por Monto Global (% de Descuento)"):
                min_t = st.number_input("Monto mínimo de compra ($)", min_value=1.0, value=2000.0)
                pct_d = st.number_input("Porcentaje de Descuento (%)", min_value=1, max_value=99, value=10)
                if st.button("Guardar Promo de Monto"):
                    config_promos["monto"].append({"id": str(uuid.uuid4())[:8], "min_total": min_t, "porcentaje": pct_d, "activa": True})
                    col_config.update_one({"_id": "promociones"}, {"$set": config_promos})
                    st.success("¡Promoción agregada!")
                    st.rerun()
                    
    st.markdown("---")
    st.markdown("### 🟢 Promociones Registradas")
    cambios = False
    
    st.markdown("#### 🌟 Promoción Estática 3x2")
    c1_3x2, c2_3x2, _ = st.columns([6, 2, 2])
    c1_3x2.info("Llevas 3, pagas 2 *(Excluye: Cartas, Extras, BakuCores y piezas con Detalle)*")
    activa_3x2 = c2_3x2.toggle("Activada", value=config_promos.get("promo_3x2", False), key="tg_3x2")
    if activa_3x2 != config_promos.get("promo_3x2", False):
        config_promos["promo_3x2"] = activa_3x2
        cambios = True

    if config_promos.get("volumen"):
        st.markdown("#### 📦 Promociones por Volumen Activas/Inactivas")
        for i, promo in enumerate(config_promos["volumen"]):
            c1, c2, c3 = st.columns([6, 2, 2])
            c1.info(f"Si llevan **{promo['min_piezas']} o más {promo['categoria']}s**, cuestan **${promo['precio_fijo']:,.2f} c/u**")
            activa = c2.toggle("Activada", value=promo["activa"], key=f"tg_v_{promo['id']}")
            if activa != promo["activa"]:
                config_promos["volumen"][i]["activa"] = activa
                cambios = True
            if c3.button("🗑️ Eliminar", key=f"dl_v_{promo['id']}"):
                config_promos["volumen"].pop(i)
                cambios = True
                
    if config_promos.get("monto"):
        st.markdown("#### 💰 Promociones por Monto Activas/Inactivas")
        for i, promo in enumerate(config_promos["monto"]):
            c1, c2, c3 = st.columns([6, 2, 2])
            c1.info(f"Si la compra es mayor a **${promo['min_total']:,.2f}**, aplicar **{promo['porcentaje']}% de descuento**")
            activa = c2.toggle("Activada", value=promo["activa"], key=f"tg_m_{promo['id']}")
            if activa != promo["activa"]:
                config_promos["monto"][i]["activa"] = activa
                cambios = True
            if c3.button("🗑️ Eliminar", key=f"dl_m_{promo['id']}"):
                config_promos["monto"].pop(i)
                cambios = True
                
    if cambios:
        col_config.update_one({"_id": "promociones"}, {"$set": config_promos})
        st.rerun()

elif vista_admin == "📊 Finanzas y Ventas":
    st.title("📊 Panel de Analítica Financiera")
    ventas = list(col_ventas.find({}))
    if not ventas:
        st.info("Aún no tienes ventas registradas para analizar.")
    else:
        hoy = hora_qro()
        def filtrar_por_fecha(dias):
            return [v for v in ventas if v["fecha_venta"] >= hoy - timedelta(days=dias)]
        ventas_hoy, ventas_semana, ventas_mes, ventas_anio = filtrar_por_fecha(0), filtrar_por_fecha(7), filtrar_por_fecha(30), filtrar_por_fecha(365)
        
        def calcular_metricas(lista_ventas):
            ingresos = sum(v.get("precio_total", 0) for v in lista_ventas)
            gastos = sum(v.get("gasto_envio", 0) for v in lista_ventas)
            return ingresos, gastos, ingresos - gastos
            
        tab1, tab2, tab3, tab4 = st.tabs(["Hoy", "Últimos 7 Días", "Últimos 30 Días", "Este Año"])
        for tab, datos_rango in [(tab1, ventas_hoy), (tab2, ventas_semana), (tab3, ventas_mes), (tab4, ventas_anio)]:
            with tab:
                ing, gas, gan = calcular_metricas(datos_rango)
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("📦 Vendidas", len(datos_rango))
                col2.metric("💸 Brutos", f"${ing:,.2f}")
                col3.metric("📉 Gastos", f"${gas:,.2f}")
                col4.metric("💰 Neta", f"${gan:,.2f}")
                
        st.markdown("---")
        st.subheader("📝 Historial Detallado de Ventas")
        for v in reversed(ventas):
            neta, cobro_envio, gasto_envio = v.get('precio_total', 0) - v.get('gasto_envio', 0), v.get('ingreso_envio', 0), v.get('gasto_envio', 0)
            fecha_str, obs = v['fecha_venta'].strftime('%d/%m/%Y'), v.get('observaciones', 'Ninguna')
            st.markdown(f'<div class="tarjeta-cliente"><div style="font-size: 14px; margin-bottom: 5px;"><span style="color: #aaa;">📅 {fecha_str}</span> &nbsp;|&nbsp; 👤 <b>{v["cliente"]}</b></div><div style="font-size: 15px; margin-bottom: 5px;">💰 <b>Ganancia Neta: <span style="color: #2ecc71;">${neta:,.2f}</span></b> &nbsp;|&nbsp; 📦 Cobro Envío: <span style="color: #f1c40f;">${cobro_envio:,.2f}</span> &nbsp;|&nbsp; 📉 Costo Guía: <span style="color: #e74c3c;">${gasto_envio:,.2f}</span></div><div style="font-size: 13px; color: #ccc;">📝 <i>Obs: {obs}</i></div></div>', unsafe_allow_html=True)

elif vista_admin == "🎨 Personalizar Página":
    st.title("🎨 Personaliza el Diseño de tu Tienda")
    with st.form("form_personalizacion"):
        nuevo_fondo = st.file_uploader("Fondo de Pantalla HD", type=["png", "jpg", "jpeg"])
        nuevo_logo = st.file_uploader("Logo del Menú Lateral", type=["png", "jpg", "jpeg"])
        if st.form_submit_button("Guardar Diseño"):
            update_data = {}
            if nuevo_fondo: update_data["fondo_b64"] = base64.b64encode(nuevo_fondo.getvalue()).decode("utf-8")
            if nuevo_logo: update_data["logo_b64"] = base64.b64encode(nuevo_logo.getvalue()).decode("utf-8")
            if update_data:
                col_config.update_one({"_id": "sitio_prefs"}, {"$set": update_data}, upsert=True)
                st.success("¡Diseño actualizado! Recarga la página.")
                st.rerun()

elif vista_admin == "➕ Agregar Producto":
    st.title("🛠️ Agregar nuevo producto")
    tipo_prod = st.selectbox("Tipo de Producto", tipos_producto)
    nombre = st.text_input("Nombre / Descripción principal")
    
    col1, col2, col3 = st.columns(3)
    tipos_con_atributo = ["Bakugan", "Trampa", "Vehículo", "Armamento", "BakuTech", "Set de Batalla", "Deka"]
    
    with col1: atributo_form = st.selectbox("Atributo", categorias[1:], disabled=(tipo_prod not in tipos_con_atributo)) 
    with col2: material_form = st.selectbox("Material", materiales[1:], disabled=(tipo_prod != "Carta"))
    with col3: simbolo_form = st.selectbox("Símbolo", simbolos_core[1:], disabled=(tipo_prod != "BakuCore"))
    
    st.markdown("### 🟢 Piezas Normales (Perfectas)")
    c_pn, c_sn = st.columns(2)
    with c_pn: precio = st.number_input("Precio Normal ($)", min_value=0.0, step=10.0)
    with c_sn: stock = st.number_input("Stock Normal", min_value=0, step=1, value=1)
    imagenes_subidas = st.file_uploader("📸 Sube fotos de la pieza NORMAL", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    
    st.markdown("### 🟠 Piezas con Detalles (Desperfectos)")
    con_detalle = st.checkbox("Activar versión con detalles / desperfectos")
    imagenes_detalle_subidas = []
    
    if con_detalle:
        c_pd, c_sd = st.columns(2)
        with c_pd: precio_detalle = st.number_input("Precio con Detalle ($)", min_value=0.0, step=10.0)
        with c_sd: stock_detalle = st.number_input("Stock con Detalle", min_value=0, step=1, value=1)
        detalle_prod = st.text_input("⚠️ Describe el desperfecto")
        imagenes_detalle_subidas = st.file_uploader("📸 Sube fotos SOLO mostrando el DETALLE", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    else:
        precio_detalle, stock_detalle, detalle_prod = 0.0, 0, ""
    
    if st.button("Subir Producto al Catálogo"):
        if nombre and (imagenes_subidas or imagenes_detalle_subidas) and (precio > 0 or precio_detalle > 0):
            lista_imagenes_b64 = [comprimir_imagen(img) for img in imagenes_subidas[:6]] if imagenes_subidas else []
            lista_imagenes_detalle_b64 = [comprimir_imagen(img) for img in imagenes_detalle_subidas[:6]] if imagenes_detalle_subidas else []
            if con_detalle and not lista_imagenes_detalle_b64: lista_imagenes_detalle_b64 = lista_imagenes_b64
                
            nuevo_prod = {
                "tipo": tipo_prod, "nombre": nombre, "precio": precio, "stock": stock,
                "precio_detalle": precio_detalle, "stock_detalle": stock_detalle, "detalle": detalle_prod,
                "imagenes_b64": lista_imagenes_b64, "imagenes_detalle_b64": lista_imagenes_detalle_b64
            }
            if tipo_prod in tipos_con_atributo: nuevo_prod["atributo"] = atributo_form
            elif tipo_prod == "Carta": nuevo_prod["material"] = material_form
            elif tipo_prod == "BakuCore": nuevo_prod["simbolo"] = simbolo_form
                
            col_productos.insert_one(nuevo_prod)
            st.success(f"¡{nombre} subido con éxito!")
            st.rerun() 
        else:
            st.error("Falta el nombre, subir foto o asignar precio.")

elif vista_admin == "📋 Ver Apartados":
    st.title("📋 Registro de Clientes y Apartados")
    st.markdown("---")
    todos_los_apartados = list(col_apartados.find({}))
    if not todos_los_apartados:
        st.info("No hay apartados activos.")
    else:
        clientes_dict = {}
        for ap in todos_los_apartados:
            tel = ap.get("comprador_telefono", "Sin número")
            if tel not in clientes_dict: clientes_dict[tel] = []
            clientes_dict[tel].append(ap)
        
        for tel, items in clientes_dict.items():
            nombre_cliente = items[0].get("comprador_nombre", "Desconocido")
            st.markdown(f'<div class="tarjeta-cliente"><h4>👤 {nombre_cliente} | 📞 WA: {tel}</h4>', unsafe_allow_html=True)
            
            total_cliente, total_anticipo = 0, 0
            fechas_venc, nombres_items = [], []
            
            for item in items:
                fecha_str = item["fecha_apartado"].strftime("%d/%m")
                precio_item = item.get("precio", 0.0)
                total_cliente += precio_item
                total_anticipo += item.get("anticipo", 0.0)
                fechas_venc.append(item.get("fecha_vencimiento", hora_qro()))
                nombres_items.append(item['nombre_producto'])
                st.write(f"- **{item['nombre_producto']}** (${precio_item:,.2f}) _[Apt: {fecha_str}]_")
            
            fecha_max_venc = max(fechas_venc).strftime("%d/%m %H:%M")
            restante = total_cliente - total_anticipo
            
            st.markdown(f"**⏳ Vence el:** {fecha_max_venc}")
            st.markdown(f"**💰 Total pedido:** ${total_cliente:,.2f}")
            if total_anticipo > 0:
                st.markdown(f"**💸 Anticipo dado:** <span style='color:#f39c12;'>${total_anticipo:,.2f}</span>", unsafe_allow_html=True)
                st.markdown(f"**⚠️ Restante a cobrar:** <span style='color:#e74c3c; font-size:1.2em; font-weight:bold;'>${restante:,.2f}</span>", unsafe_allow_html=True)
            else:
                st.markdown(f"**⚠️ Total a cobrar:** <span style='color:#2ecc71; font-size:1.2em; font-weight:bold;'>${total_cliente:,.2f}</span>", unsafe_allow_html=True)
            
            col_conf, col_pro, col_canc, col_notif = st.columns(4)
            with col_conf:
                with st.expander("✅ Vender"):
                    cobro_envio = st.number_input("Cobro Envío $", min_value=0.0, step=10.0, key=f"cobro_{tel}")
                    gastos = st.number_input("Costo Guía $", min_value=0.0, step=10.0, key=f"gasto_{tel}")
                    obs = st.text_input("Obs", key=f"obs_{tel}")
                    if st.button("Confirmar", key=f"btn_venta_{tel}"):
                        col_ventas.insert_one({
                            "cliente": nombre_cliente, "telefono": tel, "productos": nombres_items,
                            "precio_productos": total_cliente, "ingreso_envio": cobro_envio,
                            "anticipo_previo": total_anticipo,
                            "precio_total": total_cliente + cobro_envio, "gasto_envio": gastos,
                            "observaciones": obs, "fecha_venta": hora_qro()
                        })
                        for item in items: col_apartados.delete_one({"_id": item["_id"]})
                        st.success("¡Venta registrada!")
                        st.rerun()
                        
            with col_pro:
                with st.expander("⏳ Prórroga"):
                    nuevo_anticipo = st.number_input("Abonar $", min_value=0.0, step=50.0, key=f"ant_{tel}")
                    dias_pro = st.number_input("Días Extra", min_value=0, step=1, value=1, key=f"dias_{tel}")
                    if st.button("Aplicar", key=f"btn_pro_{tel}"):
                        ids_items = [item["_id"] for item in items]
                        if nuevo_anticipo > 0: col_apartados.update_one({"_id": ids_items[0]}, {"$inc": {"anticipo": nuevo_anticipo}})
                        if dias_pro > 0:
                            nueva_fecha = max(fechas_venc) + timedelta(days=dias_pro)
                            col_apartados.update_many({"_id": {"$in": ids_items}}, {"$set": {"fecha_vencimiento": nueva_fecha}})
                        st.success("¡Prórroga aplicada!")
                        st.rerun()
                        
            with col_canc:
                with st.expander("🚫 Cancelar"):
                    if st.button("Confirmar", key=f"btn_cancel_{tel}"):
                        for doc in items:
                            campo = doc.get("campo_stock", "stock")
                            col_productos.update_one({"_id": doc["producto_id"]}, {"$inc": {campo: 1}})
                            col_apartados.delete_one({"_id": doc["_id"]})
                        st.success("¡Cancelado!")
                        st.rerun()

            with col_notif:
                with st.expander("📱 Notificar"):
                    texto_expiracion = f"Hola {nombre_cliente}, te escribo de Baku-Market. Te recuerdo que tu apartado de {len(items)} piezas (Restante: ${restante:,.2f}) vence el {fecha_max_venc}. ¿Gusta que revisemos un abono/prórroga o procesamos tu envío?"
                    texto_cancelacion = f"Hola {nombre_cliente}. Te notificamos que el tiempo de tu apartado concluyó en Baku-Market y tu pedido de {len(items)} piezas ha sido cancelado, liberando el stock. ¡Gracias por tu comprensión!"
                    link_exp = f"https://wa.me/{tel.replace(' ', '')}?text={urllib.parse.quote(texto_expiracion)}"
                    link_canc = f"https://wa.me/{tel.replace(' ', '')}?text={urllib.parse.quote(texto_cancelacion)}"
                    st.markdown(f"[⚠️ Aviso Expiración]({link_exp})", unsafe_allow_html=True)
                    st.markdown(f"<br>[🚫 Aviso Cancelación]({link_canc})", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

else:
    es_modo_admin_catalogo = st.session_state.admin_autenticado and vista_admin == "Ver Catálogo"
    
    if es_modo_admin_catalogo:
        st.title("🛠️ Administrar Catálogo e Inventario")
        todos_para_conteo = list(col_productos.find({}, {"stock": 1, "stock_detalle": 1, "precio": 1, "precio_detalle": 1}))
        total_publicaciones = len(todos_para_conteo)
        total_piezas_fisicas = sum(p.get("stock", 0) + p.get("stock_detalle", 0) for p in todos_para_conteo)
        
        valor_estimado_total = sum(
            (p.get("stock", 0) * p.get("precio", 0.0)) + 
            (p.get("stock_detalle", 0) * p.get("precio_detalle", 0.0)) 
            for p in todos_para_conteo
        )
        
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("📦 Publicaciones (Modelos)", total_publicaciones)
        col_m2.metric("🔢 Piezas Físicas (Stock)", total_piezas_fisicas)
        col_m3.metric("💰 Valor Total Inventario", f"${valor_estimado_total:,.2f}")
        st.markdown("---")
        
        busqueda_texto = st.text_input("🔍 Buscar pieza por nombre...")
    else:
        col_tit, col_busc, col_cart = st.columns([1.5, 2, 1.5])
        with col_tit: st.markdown("### 🔥 Baku-Market") 
        with col_busc: busqueda_texto = st.text_input("Buscar", placeholder="🔍 Buscar...", label_visibility="collapsed")
        
        # ---------------- EVALUAR PROMOS Y BANNER 3x2 INTERACTIVO ----------------
        if config_promos.get("promo_3x2", False):
            elegibles_3x2 = [i for i in st.session_state.carrito if i.get("tipo") not in ["Carta", "BakuCore", "Extra"] and i.get("variante") != "detalle"]
            
            if len(elegibles_3x2) > 0 and len(elegibles_3x2) % 3 == 2:
                precios_ordenados = sorted([i['precio'] for i in elegibles_3x2], reverse=True)
                precio_maximo_regalo = min(precios_ordenados[-2:])
                
                # --- AUTO-ABRIR MODAL ---
                if st.session_state.get("abrir_modal_3x2", False):
                    modal_regalo_3x2(precio_maximo_regalo)
                    
                st.markdown(f"""
                <div style="background: linear-gradient(90deg, #f1c40f, #f39c12); padding: 15px; border-radius: 8px; text-align: center; color: white; margin-bottom: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.2);">
                    <h3 style="margin: 0; color: white;">🎁 ¡Tienes un 3x2 Activo!</h3>
                    <p style="margin: 0; font-size: 16px;">Llevas 2 piezas elegibles, te regalamos la 3ra (hasta <b>${precio_maximo_regalo:,.2f}</b>)</p>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button("👉 ABRIR MENÚ PARA ELEGIR MI REGALO 👈", type="primary", use_container_width=True):
                    st.session_state.abrir_modal_3x2 = True
                    st.rerun()

        # --- CARRITO INTELIGENTE ---
        with col_cart:
            cantidad_carrito = len(st.session_state.carrito)
            items_procesados = []
            for item in st.session_state.carrito:
                items_procesados.append({"item": item, "precio_efec": item['precio'], "es_promo_vol": False, "es_promo_3x2": False, "msg_wa": ""})
            
            conteo_categorias = {}
            for ip in items_procesados:
                t = ip["item"].get("tipo", "Bakugan")
                conteo_categorias[t] = conteo_categorias.get(t, 0) + 1
                
            promos_volumen_aplicables = {}
            textos_promos_activas = []
            
            for p_vol in config_promos.get("volumen", []):
                if p_vol["activa"] and conteo_categorias.get(p_vol["categoria"], 0) >= p_vol["min_piezas"]:
                    promos_volumen_aplicables[p_vol["categoria"]] = p_vol["precio_fijo"]
                    textos_promos_activas.append(f"🎉 ¡Promo: {p_vol['min_piezas']}+ {p_vol['categoria']}s a ${p_vol['precio_fijo']:,.2f} c/u!")
                    
            for ip in items_procesados:
                t = ip["item"].get("tipo", "Bakugan")
                if t in promos_volumen_aplicables and ip['item']['precio'] > promos_volumen_aplicables[t]:
                    ip["precio_efec"] = promos_volumen_aplicables[t]
                    ip["es_promo_vol"] = True
                    
            if config_promos.get("promo_3x2", False):
                elegibles_cart_3x2 = []
                for ip in items_procesados:
                    t = ip["item"].get("tipo", "Bakugan")
                    v = ip["item"].get("variante", "normal")
                    if t not in ["Carta", "BakuCore", "Extra"] and v != "detalle":
                        elegibles_cart_3x2.append(ip)
                        
                elegibles_cart_3x2.sort(key=lambda x: x["precio_efec"], reverse=True)
                
                piezas_regaladas = 0
                for idx, ip in enumerate(elegibles_cart_3x2):
                    if (idx + 1) % 3 == 0:
                        ip["precio_efec"] = 0.0
                        ip["es_promo_3x2"] = True
                        piezas_regaladas += 1
                        
                if piezas_regaladas > 0:
                    textos_promos_activas.append(f"🌟 ¡Promo 3x2 Aplicada! ({piezas_regaladas} pieza(s) gratis)")
            
            subtotal_previo = sum(ip["precio_efec"] for ip in items_procesados)
            mejor_promo_monto = None
            mejor_pct = 0
            for p_mon in config_promos.get("monto", []):
                if p_mon["activa"] and subtotal_previo >= p_mon["min_total"]:
                    if p_mon["porcentaje"] > mejor_pct:
                        mejor_pct = p_mon["porcentaje"]
                        mejor_promo_monto = p_mon
                        
            if mejor_promo_monto:
                textos_promos_activas.append(f"🤑 ¡{mejor_promo_monto['porcentaje']}% OFF en tu carrito mayor a ${mejor_promo_monto['min_total']:,.2f}!")
                
            total_carrito = 0
            for ip in items_procesados:
                if ip["es_promo_3x2"]:
                    ip["precio_final"] = 0.0
                    ip["msg_wa"] = " (¡Gratis 3x2!)"
                elif ip["es_promo_vol"]:
                    ip["precio_final"] = ip["precio_efec"]
                    ip["msg_wa"] = f" (Promo ${ip['precio_efec']})"
                elif mejor_promo_monto:
                    ip["precio_final"] = ip["precio_efec"] * (1 - (mejor_promo_monto["porcentaje"] / 100.0))
                    ip["msg_wa"] = f" (-{mejor_promo_monto['porcentaje']}%)"
                else:
                    ip["precio_final"] = ip["precio_efec"]
                    ip["msg_wa"] = ""
                    
                total_carrito += ip["precio_final"]
            
            with st.popover(f"🛒 Carrito ({cantidad_carrito}) - ${total_carrito:,.2f}", use_container_width=True):
                if 'wa_link' in st.session_state:
                    st.success("✅ ¡Piezas apartadas!")
                    st.markdown(f"[**📲 HAZ CLIC AQUÍ PARA AVISARME POR WHATSAPP**]({st.session_state.wa_link})")
                    if st.button("Cerrar Aviso", use_container_width=True):
                        del st.session_state['wa_link']
                        st.rerun()
                
                st.markdown("#### Resumen:")
                if cantidad_carrito > 0:
                    for txt in textos_promos_activas: st.success(txt)
                        
                    for i, ip in enumerate(items_procesados):
                        c1, c2 = st.columns([4, 1])
                        item = ip["item"]
                        if ip["precio_final"] < item['precio']:
                            texto_precio = f"~~${item['precio']}~~ **${ip['precio_final']:,.2f}**"
                            if ip["precio_final"] == 0.0: texto_precio = f"~~${item['precio']}~~ **¡GRATIS!**"
                        else:
                            texto_precio = f"**${ip['precio_final']:,.2f}**"
                            
                        c1.markdown(f"<span style='font-size:0.9em;'>{item['nombre']} - {texto_precio}</span>", unsafe_allow_html=True)
                        if c2.button("❌", key=f"del_cart_{i}_{item['_id']}"):
                            st.session_state.carrito.pop(i)
                            guardar_carrito() 
                            st.rerun()
                            
                    st.markdown("---")
                    st.markdown(f"**Total a pagar: ${total_carrito:,.2f}**")
                    nom = st.text_input("Tu Nombre", key="checkout_nom")
                    tel = st.text_input("Tu WhatsApp", key="checkout_tel")
                    
                    if st.button("Confirmar Apartado", use_container_width=True, type="primary"):
                        if nom and tel:
                            for ip in items_procesados:
                                item_bd = ip["item"]
                                db_prod = col_productos.find_one({"_id": item_bd["_id"]})
                                campo_stock = "stock_detalle" if item_bd.get("variante") == "detalle" and "stock_detalle" in db_prod else "stock"
                                    
                                col_apartados.insert_one({
                                    "producto_id": item_bd["_id"], "nombre_producto": item_bd["nombre"],
                                    "precio": ip["precio_final"], "comprador_nombre": nom, "comprador_telefono": tel,
                                    "fecha_apartado": hora_qro(), "fecha_vencimiento": hora_qro() + timedelta(days=3), 
                                    "campo_stock": campo_stock, "anticipo": 0.0
                                })
                                col_productos.update_one({"_id": item_bd["_id"]}, {"$inc": {campo_stock: -1}})
                            
                            texto_crudo = f"Hola, soy {nom}. Acabo de apartar {cantidad_carrito} piezas por un total de ${total_carrito:,.2f}.\n\nMis piezas son:\n"
                            for ip in items_procesados:
                                texto_crudo += f"👉 {ip['item']['nombre']} (${ip['precio_final']:,.2f}){ip['msg_wa']}\n"
                            
                            if mejor_promo_monto:
                                texto_crudo += f"\n*Nota: Estoy consciente de que el descuento del {mejor_promo_monto['porcentaje']}% aplicado no cubre gastos de envío.*"
                            
                            texto_url = urllib.parse.quote(texto_crudo)
                            st.session_state.wa_link = f"https://wa.me/4462879839?text={texto_url}"
                            
                            st.session_state.carrito = [] 
                            guardar_carrito()
                            st.rerun()
                        else: st.warning("⚠️ Faltan datos.")
                else: st.info("Carrito vacío.")

        # ---------------- BANNER INFORMATIVO (Si no se está usando el 3x2 interactivo) ----------------
        if not es_modo_admin_catalogo:
            banner_frases = []
            if config_promos.get("promo_3x2", False): 
                elegibles_3x2_banner = [i for i in st.session_state.carrito if i.get("tipo") not in ["Carta", "BakuCore", "Extra"] and i.get("variante") != "detalle"]
                if not (len(elegibles_3x2_banner) > 0 and len(elegibles_3x2_banner) % 3 == 2):
                    banner_frases.append("🌟 <b>¡SÚPER 3x2! Llevas 3, Pagas 2</b>")
                    
            for p in config_promos.get("volumen", []):
                if p["activa"]: banner_frases.append(f"📦 <b>{p['min_piezas']}+ {p['categoria']}s a ${p['precio_fijo']:,.2f} c/u</b>")
            for p in config_promos.get("monto", []):
                if p["activa"]: banner_frases.append(f"🤑 <b>{p['porcentaje']}% OFF</b> en compras > ${p['min_total']:,.2f}")
                    
            if banner_frases:
                texto_banner = " &nbsp;|&nbsp; ".join(banner_frases)
                st.markdown(f"""
                <div style="background: linear-gradient(90deg, #ff416c, #ff4b2b); padding: 12px; border-radius: 8px; text-align: center; color: white; font-size: 15px; margin-bottom: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.2);">
                    ✨ <b>¡PROMOS ACTIVAS!</b> ✨ <br class="mobile-break">
                    {texto_banner}
                </div>
                <style>
                    @media (min-width: 768px) {{ .mobile-break {{ display: none; }} }}
                </style>
                """, unsafe_allow_html=True)
            
    st.markdown("---")

    query_base = {}
    if busqueda_texto: query_base["nombre"] = {"$regex": busqueda_texto, "$options": "i"}

    # --- LÓGICA DE BÚSQUEDA ---
    if tipo_busqueda in tipos_con_atributo_ui:
        if tipo_busqueda == "Bakugans 🔥": query_base["$or"] = [{"tipo": "Bakugan"}, {"tipo": {"$exists": False}}]
        elif tipo_busqueda == "Trampas 🪤": query_base["tipo"] = "Trampa"
        elif tipo_busqueda == "Vehículos 🏎️": query_base["tipo"] = "Vehículo"
        elif tipo_busqueda == "Armamentos ⚔️": query_base["tipo"] = "Armamento"
        elif tipo_busqueda == "BakuTech 🦾": query_base["tipo"] = "BakuTech"
        elif tipo_busqueda == "Sets de Batalla 🏟️": query_base["tipo"] = "Set de Batalla"
        elif tipo_busqueda == "Deka 🌐": query_base["tipo"] = "Deka"
        if sub_filtro != "Todos": query_base["atributo"] = sub_filtro
    elif tipo_busqueda == "Cartas 🃏":
        query_base["tipo"] = "Carta"
        if sub_filtro != "Todas": query_base["material"] = sub_filtro
    elif tipo_busqueda == "BakuCores 🛑": 
        query_base["tipo"] = "BakuCore"
        if sub_filtro != "Todos": query_base["simbolo"] = sub_filtro
    elif tipo_busqueda == "Extras 🎁": 
        query_base["tipo"] = "Extra"

    productos_crudos = list(col_productos.find(query_base))
    productos_filtrados = []

    for prod in productos_crudos:
        stock_normal = prod.get('stock', 0)
        stock_detalle = prod.get('stock_detalle', 0)
        texto_detalle = prod.get('detalle', "")
        
        if texto_detalle and 'stock_detalle' not in prod:
            stock_detalle = stock_normal
            stock_normal = 0
            
        if es_modo_admin_catalogo:
            if tipo_busqueda == "Piezas / Detalles 🛠️" and not texto_detalle: continue
            if tipo_busqueda != "Piezas / Detalles 🛠️" and tipo_busqueda != "Todo el Catálogo 🌍" and texto_detalle and stock_normal == 0 and stock_detalle > 0: continue
            productos_filtrados.append(prod)
        else:
            if tipo_busqueda == "Piezas / Detalles 🛠️":
                if texto_detalle and stock_detalle > 0: productos_filtrados.append(prod)
            elif tipo_busqueda == "Todo el Catálogo 🌍":
                if stock_normal > 0 or stock_detalle > 0: productos_filtrados.append(prod)
            else:
                if stock_normal > 0: productos_filtrados.append(prod)

    rng = random.Random(st.session_state.rand_seed)
    rng.shuffle(productos_filtrados)

    # ---------------- RENDERIZADO CON PAGINACIÓN ----------------
    productos_a_mostrar = productos_filtrados[:st.session_state.limite_items]

    if not productos_filtrados:
        st.info("No encontramos piezas en esta categoría.")
    else:
        cols = st.columns(3)
        for index, prod in enumerate(productos_a_mostrar):
            with cols[index % 3]:
                st.markdown(f"### {prod['nombre']}")
                
                if tipo_busqueda == "Piezas / Detalles 🛠️":
                    imagenes_del_producto = prod.get("imagenes_detalle_b64", prod.get("imagenes_b64", []))
                else:
                    imagenes_del_producto = prod.get("imagenes_b64", [])
                    if not imagenes_del_producto:
                        imagenes_del_producto = prod.get("imagenes_detalle_b64", [])
                        
                if not imagenes_del_producto and "imagen_b64" in prod: 
                    imagenes_del_producto = [prod["imagen_b64"]]
                
                if imagenes_del_producto:
                    html_galeria = '<div class="galeria-container">'
                    for b64_img in imagenes_del_producto: html_galeria += f'<img src="data:image/jpeg;base64,{b64_img}" class="galeria-img">'
                    html_galeria += '</div>'
                    st.markdown(html_galeria, unsafe_allow_html=True)
                    if len(imagenes_del_producto) > 1: st.markdown("<p style='text-align: center; color: #aaa; font-size: 13px; margin-top: -5px; margin-bottom: 5px;'>👉 Desliza la foto</p>", unsafe_allow_html=True)
                    if st.button("🔍 Ampliar foto", key=f"zoom_{prod['_id']}", use_container_width=True): abrir_zoom(prod['nombre'], imagenes_del_producto)
                
                stock_normal = prod.get('stock', 0)
                precio_normal = prod.get('precio', 0.0)
                stock_detalle = prod.get('stock_detalle', 0)
                precio_detalle = prod.get('precio_detalle', 0.0)
                texto_detalle = prod.get('detalle', "")

                if texto_detalle and 'stock_detalle' not in prod:
                    stock_detalle = stock_normal
                    precio_detalle = precio_normal
                    stock_normal = 0
                    precio_normal = 0.0
                
                # --- AJUSTE QUIROPRÁCTICO DE MÁRGENES (Reduciendo espacios) ---
                tipo_real = prod.get("tipo", "Bakugan")
                if tipo_real == "Bakugan" or "atributo" in prod: st.markdown(f"<div style='margin-top: 5px; margin-bottom: -10px;'><b>Atributo:</b> {prod.get('atributo', 'N/A')}</div>", unsafe_allow_html=True)
                elif tipo_real == "Carta": st.markdown(f"<div style='margin-top: 5px; margin-bottom: -10px;'><b>Material:</b> {prod.get('material', 'N/A')}</div>", unsafe_allow_html=True)
                elif tipo_real == "BakuCore": st.markdown(f"<div style='margin-top: 5px; margin-bottom: -10px;'><b>Símbolo:</b> {prod.get('simbolo', 'N/A')}</div>", unsafe_allow_html=True)
                
                if not es_modo_admin_catalogo:
                    en_carrito_normal = sum(1 for item in st.session_state.carrito if item["_id"] == prod["_id"] and item.get("variante") == "normal")
                    en_carrito_detalle = sum(1 for item in st.session_state.carrito if item["_id"] == prod["_id"] and item.get("variante") == "detalle")
                    
                    if stock_normal == 0 and stock_detalle == 0:
                        st.markdown("🚨 **AGOTADO**", unsafe_allow_html=True)
                    else:
                        if stock_normal > 0:
                            cu_norm = " c/u" if stock_normal > 1 else ""
                            st.write(f"🟢 **Perfecta:** ${precio_normal:,.2f}{cu_norm} (Disp: {stock_normal})")
                            
                            if (stock_normal - en_carrito_normal) > 0:
                                if st.button("🛒 Añadir", key=f"add_n_{prod['_id']}", use_container_width=True):
                                    st.session_state.carrito.append({"_id": prod["_id"], "nombre": f"{prod['nombre']}", "precio": precio_normal, "variante": "normal", "tipo": tipo_real})
                                    guardar_carrito() 
                                    
                                    # --- DETECCIÓN AUTOMÁTICA DEL 3x2 ---
                                    if config_promos.get("promo_3x2", False) and tipo_real not in ["Carta", "BakuCore", "Extra"]:
                                        eleg = [i for i in st.session_state.carrito if i.get("tipo") not in ["Carta", "BakuCore", "Extra"] and i.get("variante") != "detalle"]
                                        if len(eleg) % 3 == 2:
                                            st.session_state.abrir_modal_3x2 = True
                                            
                                    st.rerun()
                            else: st.button("✅ En carrito (Máx)", disabled=True, key=f"max_n_{prod['_id']}", use_container_width=True)
                            
                        if stock_detalle > 0:
                            st.markdown(f"<span style='color:#f39c12; font-size: 0.9em;'>⚠️ **Detalle:** {texto_detalle}</span>", unsafe_allow_html=True)
                            cu_det = " c/u" if stock_detalle > 1 else ""
                            st.write(f"🟠 **C/Detalle:** ${precio_detalle:,.2f}{cu_det} (Disp: {stock_detalle})")
                            
                            if (stock_detalle - en_carrito_detalle) > 0:
                                if st.button("🛒 Añadir", key=f"add_d_{prod['_id']}", use_container_width=True):
                                    st.session_state.carrito.append({"_id": prod["_id"], "nombre": f"{prod['nombre']} (Detalle)", "precio": precio_detalle, "variante": "detalle", "tipo": tipo_real})
                                    guardar_carrito() 
                                    st.rerun()
                            else: st.button("✅ Detalle en carrito", disabled=True, key=f"max_d_{prod['_id']}", use_container_width=True)

                if es_modo_admin_catalogo:
                    # --- NUEVA LÍNEA DIVISORIA COMPACTA ---
                    st.markdown('<hr style="margin: 10px 0px; border: none; border-top: 1px solid rgba(255,255,255,0.2);">', unsafe_allow_html=True)
                    
                    with st.expander("✏️ Editar"):
                        tipo_actual = prod.get("tipo", "Bakugan")
                        idx_tipo = tipos_producto.index(tipo_actual) if tipo_actual in tipos_producto else 0
                        nuevo_tipo = st.selectbox("Categoría / Tipo", tipos_producto, index=idx_tipo, key=f"etipo_{prod['_id']}")

                        np = st.number_input("Precio N.", value=float(precio_normal), step=10.0, key=f"epn_{prod['_id']}")
                        ns = st.number_input("Stock N.", value=int(stock_normal), step=1, key=f"esn_{prod['_id']}")
                        ndp = st.number_input("Precio D.", value=float(precio_detalle), step=10.0, key=f"epd_{prod['_id']}")
                        nds = st.number_input("Stock D.", value=int(stock_detalle), step=1, key=f"esd_{prod['_id']}")
                        ndtxt = st.text_input("Detalle", value=texto_detalle, key=f"etxt_{prod['_id']}")
                        
                        if st.button("💾 Guardar", key=f"save_{prod['_id']}", use_container_width=True):
                            col_productos.update_one({"_id": prod["_id"]}, {"$set": {
                                "tipo": nuevo_tipo,
                                "precio": np, "stock": ns, "precio_detalle": ndp, "stock_detalle": nds, "detalle": ndtxt
                            }})
                            st.rerun()
                            
                    if st.button("🗑️ Eliminar", key=f"del_{prod['_id']}", use_container_width=True):
                        col_productos.delete_one({"_id": prod["_id"]})
                        st.rerun()
                        
        # Botón para cargar más piezas
        if len(productos_filtrados) > st.session_state.limite_items:
            st.markdown("---")
            if st.button("⬇️ Cargar más piezas", use_container_width=True, type="primary"):
                st.session_state.limite_items += 12
                st.rerun()